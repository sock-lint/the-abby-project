"""Lifecycle endpoints exercise real cascades; only external/failure seams mock."""
import logging
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.file_cleanup import process_pending_file_deletions
from apps.accounts.models import PendingFileDeletion
from apps.achievements.models import ProjectSkillTag, Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.chores.models import Chore, ChoreCompletion
from apps.chronicle.models import ChronicleEntry
from apps.families.models import Family
from apps.google_integration.models import CalendarEventMapping, GoogleAccount
from apps.habits.models import Habit, HabitLog
from apps.homework.models import (
    HomeworkAISettings, HomeworkAssignment, HomeworkProof, HomeworkSubmission, HomeworkTemplate,
)
from apps.ingestion.models import ProjectIngestionJob
from apps.payments.models import PaymentLedger
from apps.portfolio.models import ProjectPhoto
from apps.printing.models import PrinterProfile
from apps.projects.models import Project, ProjectCompletionRewardReceipt, ProjectTemplate
from apps.rewards.models import CoinLedger, Reward
from apps.rpg.models import CharacterProfile, SpriteAsset
from config.tests.factories import make_family, make_oauth_token


BASE = "/api/account/lifecycle/"
User = get_user_model()


class LifecycleSetup:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.household = make_family(
            "Lifecycle Family",
            parents=[{"username": "departing"}, {"username": "successor"}],
            children=[{"username": "child"}, {"username": "sibling"}],
        )
        self.family = self.household.family
        self.parent, self.successor = self.household.parents
        self.child, self.sibling = self.household.children
        self.other = make_family("Other Family", parents=[{"username": "other-parent"}], children=[{"username": "other-child"}])
        self.client = APIClient()
        self.sign_in(self.parent)

    def sign_in(self, user):
        self.token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def delete(self, **overrides):
        data = {"password": "pw", "confirm_username": self.parent.username, "successor_id": self.successor.pk}
        return self.client.post(BASE + "delete/", {**data, **overrides}, format="json")

    def close(self, **overrides):
        version = getattr(self.client.get(BASE), "data", {}).get("family_version", "0" * 64)
        return self.client.post(BASE + "close-family/", {"password": "pw", "confirm_family_slug": self.family.slug, "family_version": version, **overrides}, format="json")

    def journal(self, user, title="Secret memory"):
        return ChronicleEntry.objects.create(
            user=user, kind="journal", occurred_on=timezone.localdate(), chapter_year=2026,
            title=title, summary="Private body must not transfer or appear in lifecycle responses", is_private=True,
        )

    def save_file(self, instance, field, name):
        value = getattr(instance, field)
        value.save(name, ContentFile(b"synthetic private file"), save=True)
        return value.name

    def deactivate_successor(self):
        self.successor.is_active = False
        self.successor.save(update_fields=["is_active"])


class AccountLifecycleTests(LifecycleSetup, TestCase):
    def test_preview_is_family_scoped_counts_inactive_members_and_never_exposes_private_content(self):
        self.journal(self.child)
        Project.objects.create(title="Shared", created_by=self.parent, assigned_to=self.child)
        self.sibling.is_active = False
        self.sibling.save(update_fields=["is_active"])
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(hasattr(response, "data"), "Lifecycle preview must return an API response, not the SPA HTML fallback")
        self.assertRegex(response.data["family_version"], r"^[0-9a-f]{64}$")
        self.assertEqual(response.data, {
            "user": {"id": self.parent.pk, "username": "departing"},
            "family": {"id": self.family.pk, "name": self.family.name, "slug": self.family.slug, "primary_parent_id": self.parent.pk},
            "family_members": {"parents": 2, "children": 2},
            "family_version": response.data["family_version"],
            "successors": [{"id": self.successor.pk, "display_name": "successor"}],
            "shared_work": {"projects": 1, "project_templates": 0, "homework_assignments": 0, "homework_templates": 0, "chores": 0, "habits": 0},
            "can_delete_account": True,
            "can_close_family": False,
        })
        for private in ("Secret memory", "Private body", self.token.key, "other-parent"):
            self.assertNotIn(private, str(response.data))

    def test_anonymous_lifecycle_requests_require_authentication(self):
        self.client.credentials()
        self.assertEqual(self.client.get(BASE).status_code, 401)
        for endpoint in ("transfer/", "delete/", "close-family/"):
            self.assertEqual(self.client.post(BASE + endpoint, {}, format="json").status_code, 401)

    def test_transfer_only_changes_contact_pointer_and_keeps_equal_parent_permissions(self):
        shared = Project.objects.create(title="Shared", created_by=self.parent, assigned_to=self.child)
        self.sign_in(self.successor)  # A co-parent has the same handoff authority.
        response = self.client.post(BASE + "transfer/", {"password": "pw", "successor_id": self.parent.pk}, format="json")
        self.assertEqual(response.status_code, 204)
        self.family.refresh_from_db()
        self.assertEqual(self.family.primary_parent_id, self.parent.pk)
        self.sign_in(self.parent)
        response = self.client.post(BASE + "transfer/", {"password": "pw", "successor_id": self.successor.pk}, format="json")
        self.assertEqual(response.status_code, 204)
        self.family.refresh_from_db()
        shared.refresh_from_db()
        self.assertEqual(self.family.primary_parent_id, self.successor.pk)
        self.assertEqual(shared.created_by_id, self.parent.pk)
        self.assertTrue(Token.objects.filter(pk=self.token.pk).exists())

    def test_successor_validation_rejects_self_child_foreign_missing_and_inactive_without_leaking_existence(self):
        self.deactivate_successor()
        responses = []
        for successor_id in (self.parent.pk, self.child.pk, self.other.parents[0].pk, 9999999, self.successor.pk):
            response = self.client.post(BASE + "transfer/", {"password": "pw", "successor_id": successor_id}, format="json")
            self.assertEqual(response.status_code, 400)
            responses.append(response.data)
        self.assertTrue(all(data == responses[0] for data in responses))
        self.family.refresh_from_db()
        self.assertEqual(self.family.primary_parent_id, self.parent.pk)

    def test_wrong_password_confirmation_and_unusable_password_leave_account_and_signin_intact(self):
        for data in ({"password": "wrong"}, {"confirm_username": "Departing"}, {"confirm_username": " departing"}):
            self.assertEqual(self.delete(**data).status_code, 400)
        self.parent.set_unusable_password()
        self.parent.save(update_fields=["password"])
        self.assertEqual(self.delete().status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.parent.pk).exists())
        self.assertTrue(Token.objects.filter(pk=self.token.pk).exists())

    def test_parent_cannot_leave_without_an_active_successor(self):
        self.assertEqual(self.delete(successor_id=None).status_code, 400)
        self.deactivate_successor()
        self.assertEqual(self.delete().status_code, 400)
        preview = self.client.get(BASE).data
        self.assertFalse(preview["can_delete_account"])
        self.assertTrue(preview["can_close_family"])
        self.assertEqual(preview["successors"], [])
        self.assertTrue(User.objects.filter(pk=self.parent.pk).exists())

    def test_parent_departure_preserves_shared_work_and_child_private_journals_but_deletes_personal_records(self):
        shared = Project.objects.create(title="Child project", created_by=self.parent, assigned_to=self.child)
        open_project = Project.objects.create(title="Family project", created_by=self.parent)
        own_project = Project.objects.create(title="Personal project", created_by=self.successor, assigned_to=self.parent)
        template = ProjectTemplate.objects.create(title="Shared template", family=self.family, created_by=self.parent)
        homework = HomeworkAssignment.objects.create(
            title="Child homework", subject="math", due_date=timezone.localdate(), created_by=self.parent, assigned_to=self.child,
        )
        submission = HomeworkSubmission.objects.create(assignment=homework, user=self.child, timeliness="on_time")
        proof = HomeworkProof.objects.create(submission=submission)
        template_hw = HomeworkTemplate.objects.create(title="Shared homework template", subject="math", created_by=self.parent)
        chore = Chore.objects.create(title="Shared chore", created_by=self.parent, family=self.family)
        completion = ChoreCompletion.objects.create(chore=chore, user=self.child, completed_date=timezone.localdate(), reward_amount_snapshot=0, coin_reward_snapshot=0)
        habit = Habit.objects.create(name="Child habit", created_by=self.parent, user=self.child)
        habit_log = HabitLog.objects.create(habit=habit, user=self.child, direction=1)
        child_journal, parent_journal = self.journal(self.child), self.journal(self.parent)
        actor_photo = ProjectPhoto.objects.create(project=shared, user=self.parent)
        child_photo = ProjectPhoto.objects.create(project=shared, user=self.child)
        imported = ProjectIngestionJob.objects.create(created_by=self.parent, source_type="pdf")
        queued = [
            self.save_file(self.parent, "avatar", "parent.png"),
            self.save_file(own_project, "cover_photo", "personal.png"),
            self.save_file(actor_photo, "image", "parent-photo.png"),
            self.save_file(imported, "source_file", "parent.pdf"),
        ]
        retained = [
            self.save_file(shared, "cover_photo", "child-cover.png"),
            self.save_file(proof, "image", "child-proof.png"),
            self.save_file(child_photo, "image", "child-photo.png"),
        ]
        GoogleAccount.objects.create(user=self.parent, google_id="parent-google", google_email="parent@example.test", encrypted_credentials=b"synthetic")
        child_google = GoogleAccount.objects.create(user=self.child, google_id="child-google", google_email="child@example.test", encrypted_credentials=b"synthetic", linked_by=self.parent)
        calendar = CalendarEventMapping.objects.create(user=self.parent, content_type="project_due", object_id=shared.pk, google_event_id="synthetic")
        access, _ = make_oauth_token(self.parent)
        sprite = SpriteAsset.objects.create(slug="global", image="global.png", created_by=self.parent, frame_width_px=1, frame_height_px=1)
        ledger = PaymentLedger.objects.create(user=self.child, amount=5, entry_type="adjustment", created_by=self.parent, description="Shared retained family record")
        self.assertEqual(self.delete().status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.parent.pk).exists())
        self.assertFalse(ChronicleEntry.objects.filter(pk=parent_journal.pk).exists())
        child_journal.refresh_from_db()
        self.assertEqual(child_journal.user_id, self.child.pk)
        self.assertTrue(child_journal.is_private)
        for row in (shared, open_project, template, homework, template_hw, chore, habit):
            row.refresh_from_db()
            self.assertEqual(row.created_by_id, self.successor.pk)
        self.assertTrue(HomeworkSubmission.objects.filter(pk=submission.pk).exists())
        self.assertTrue(ChoreCompletion.objects.filter(pk=completion.pk).exists())
        self.assertTrue(HabitLog.objects.filter(pk=habit_log.pk).exists())
        self.assertFalse(Project.objects.filter(pk=own_project.pk).exists())
        self.assertCountEqual(PendingFileDeletion.objects.values_list("storage_key", flat=True), queued)
        self.assertTrue(all(default_storage.exists(name) for name in queued + retained))
        self.assertFalse(AccessToken.objects.filter(pk=access.pk).exists())
        self.assertFalse(CalendarEventMapping.objects.filter(pk=calendar.pk).exists())
        self.assertFalse(GoogleAccount.objects.filter(user_id=self.parent.pk).exists())
        child_google.refresh_from_db()
        self.assertIsNone(child_google.linked_by_id)
        sprite.refresh_from_db()
        self.assertIsNone(sprite.created_by_id)
        self.assertEqual(sprite.image.name, "global.png")
        ledger.refresh_from_db()
        self.assertIsNone(ledger.created_by_id)
        self.family.refresh_from_db()
        self.assertEqual(self.family.primary_parent_id, self.successor.pk)
        self.assertEqual(self.client.get(BASE).status_code, 401)

    def test_non_primary_parent_departure_preserves_existing_primary(self):
        self.sign_in(self.successor)
        response = self.client.post(BASE + "delete/", {"password": "pw", "confirm_username": self.successor.username, "successor_id": self.parent.pk}, format="json")
        self.assertEqual(response.status_code, 204)
        self.family.refresh_from_db()
        self.assertEqual(self.family.primary_parent_id, self.parent.pk)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_shared_completed_project_keeps_its_receipt_and_earned_rewards_without_replaying_after_handoff(self, game_loop):
        project = Project.objects.create(
            title="Completed child work", created_by=self.parent, assigned_to=self.child,
            status="in_review", difficulty=2, bonus_amount=12,
        )
        skill = Skill.objects.create(name="Building", category=SkillCategory.objects.create(name="Project practice"))
        ProjectSkillTag.objects.create(project=project, skill=skill, xp_weight=1)
        project.status = "completed"
        project.save()
        receipt = ProjectCompletionRewardReceipt.objects.get(project=project)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=skill).xp_points, 100)
        self.assertEqual(CoinLedger.objects.get(user=self.child).amount, 20)
        self.assertEqual(PaymentLedger.objects.get(user=self.child).amount, 12)

        def earned_state():
            return (
                list(SkillProgress.objects.filter(user=self.child).order_by("pk").values()),
                list(CoinLedger.objects.filter(user=self.child).order_by("pk").values("id", "amount", "reason", "user_id")),
                list(PaymentLedger.objects.filter(user=self.child).order_by("pk").values("id", "amount", "entry_type", "user_id", "project_id")),
                CharacterProfile.objects.get(user=self.child).level,
            )

        before = earned_state()
        self.assertEqual(self.delete().status_code, 204)
        receipt.refresh_from_db()
        self.assertEqual(receipt.user_id, self.child.pk)
        self.assertEqual(earned_state(), before)
        self.assertEqual(ProjectCompletionRewardReceipt.objects.get(project=project).pk, receipt.pk)
        project.refresh_from_db()
        self.assertEqual(project.created_by_id, self.successor.pk)
        self.assertEqual(project.status, "completed")
        # The server-owned once-only receipt must also survive a later review
        # cycle under the successor; ownership transfer cannot create rewards.
        project.status = "in_review"
        project.save()
        project.status = "completed"
        project.save()
        self.assertEqual(earned_state(), before)
        self.assertEqual(game_loop.call_count, 1)

    def test_child_can_delete_self_but_cannot_transfer_or_close_family(self):
        private = self.journal(self.child)
        sibling_journal = self.journal(self.sibling)
        personal = Project.objects.create(title="Child work", assigned_to=self.child, created_by=self.parent)
        self.sign_in(self.child)
        preview = self.client.get(BASE).data
        self.assertTrue(preview["can_delete_account"])
        self.assertFalse(preview["can_close_family"])
        self.assertEqual(preview["successors"], [])
        self.assertEqual(self.client.post(BASE + "transfer/", {"password": "pw", "successor_id": self.parent.pk}, format="json").status_code, 403)
        self.assertEqual(self.close().status_code, 403)
        response = self.client.post(BASE + "delete/", {"password": "pw", "confirm_username": self.child.username, "user_id": self.sibling.pk}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.child.pk).exists())
        self.assertFalse(ChronicleEntry.objects.filter(pk=private.pk).exists())
        self.assertFalse(Project.objects.filter(pk=personal.pk).exists())
        self.assertTrue(ChronicleEntry.objects.filter(pk=sibling_journal.pk, is_private=True).exists())
        self.assertTrue(User.objects.filter(pk=self.parent.pk).exists())

    def test_closure_rechecks_other_active_parents_even_for_current_primary(self):
        self.assertEqual(self.close().status_code, 400)
        self.assertTrue(Family.objects.filter(pk=self.family.pk).exists())

    def test_last_parent_can_close_family(self):
        self.deactivate_successor()
        self.assertEqual(self.close().status_code, 204)
        self.assertFalse(Family.objects.filter(pk=self.family.pk).exists())

    def test_closure_requires_exact_family_slug_and_current_password(self):
        self.deactivate_successor()
        for fields in ({"password": "wrong"}, {"confirm_family_slug": "wrong-family"}):
            self.assertEqual(self.close(**fields).status_code, 400)
        self.assertTrue(Family.objects.filter(pk=self.family.pk).exists())

    def test_closure_requires_new_review_when_membership_changes(self):
        self.deactivate_successor()
        preview = self.client.get(BASE).data
        added = User.objects.create_user(username="new-child", role="child", family=self.family, password="pw")
        response = self.close(family_version=preview["family_version"])
        self.assertEqual(response.status_code, 409)
        self.assertIn("Reload and review", str(response.data))
        self.assertTrue(User.objects.filter(pk=added.pk).exists())
        self.assertEqual(self.close().status_code, 204)

    def test_delete_failure_rolls_back_shared_author_contact_activity_and_file_queue_then_retry_succeeds(self):
        project = Project.objects.create(title="Shared", created_by=self.parent, assigned_to=self.child)
        name = self.save_file(self.parent, "avatar", "parent.png")
        event = ActivityEvent.objects.create(actor=self.parent, subject=self.child, category="system", event_type="synthetic", summary="Retained on failure")
        real_delete = User.delete

        def delete_then_fail(instance, *args, **kwargs):
            real_delete(instance, *args, **kwargs)
            raise DatabaseError("synthetic transaction failure")

        with patch.object(User, "delete", delete_then_fail), self.assertRaises(DatabaseError):
            self.delete()
        project.refresh_from_db()
        self.family.refresh_from_db()
        self.assertEqual(project.created_by_id, self.parent.pk)
        self.assertEqual(self.family.primary_parent_id, self.parent.pk)
        self.assertTrue(ActivityEvent.objects.filter(pk=event.pk).exists())
        self.assertTrue(default_storage.exists(name))
        self.assertFalse(PendingFileDeletion.objects.exists())
        self.assertTrue(Token.objects.filter(pk=self.token.pk).exists())
        self.assertEqual(self.delete().status_code, 204)

    def test_closure_failure_rolls_back_all_members_activity_and_cleanup_jobs(self):
        self.deactivate_successor()
        name = self.save_file(self.child, "avatar", "child.png")
        event = ActivityEvent.objects.create(actor=self.parent, subject=self.child, category="system", event_type="synthetic", summary="Retained on failure")
        real_delete = Family.delete

        def delete_then_fail(instance, *args, **kwargs):
            real_delete(instance, *args, **kwargs)
            raise DatabaseError("synthetic transaction failure")

        with patch.object(Family, "delete", delete_then_fail), self.assertRaises(DatabaseError):
            self.close()
        self.assertEqual(User.objects.filter(family=self.family).count(), 4)
        self.assertTrue(ActivityEvent.objects.filter(pk=event.pk).exists())
        self.assertFalse(PendingFileDeletion.objects.exists())
        self.assertTrue(default_storage.exists(name))
        self.assertEqual(self.close().status_code, 204)

    def test_malformed_creator_assignee_links_block_deletion_and_closure_without_cross_family_cascade(self):
        foreign_project = Project.objects.create(title="Private foreign project", created_by=self.parent, assigned_to=self.other.children[0])
        self.assertEqual(self.delete().status_code, 409)
        self.deactivate_successor()
        response = self.close()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("Private foreign project", str(response.data))
        self.assertTrue(Project.objects.filter(pk=foreign_project.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.other.children[0].pk).exists())
        self.assertTrue(User.objects.filter(pk=self.parent.pk).exists())

    def test_fast_delete_and_nullable_cross_family_edges_fail_closed(self):
        personal = Project.objects.create(title="Personal", assigned_to=self.parent, created_by=self.parent)
        # This nullable update would mutate a different family's ledger row.
        entry = PaymentLedger.objects.create(user=self.other.children[0], amount=5, entry_type="adjustment", project=personal)
        self.assertEqual(self.delete().status_code, 409)
        entry.refresh_from_db()
        self.assertEqual(entry.project_id, personal.pk)
        entry.delete()
        photo = ProjectPhoto.objects.create(project=personal, user=self.other.children[0])
        self.assertEqual(self.delete().status_code, 409)
        self.assertTrue(ProjectPhoto.objects.filter(pk=photo.pk).exists())

    def test_shared_oauth_client_with_other_family_grants_holds_deletion(self):
        application = Application.objects.create(name="Cross-family OAuth client", user=self.parent, client_type="public", authorization_grant_type="authorization-code")
        access, _ = make_oauth_token(self.other.parents[0], application=application)
        self.assertEqual(self.delete().status_code, 409)
        self.assertTrue(Application.objects.filter(pk=application.pk).exists())
        self.assertTrue(AccessToken.objects.filter(pk=access.pk).exists())

    def test_departing_users_grant_to_another_familys_oauth_client_does_not_delete_or_block_client(self):
        application = Application.objects.create(name="Shared client", user=self.other.parents[0], client_type="public", authorization_grant_type="authorization-code")
        access, _ = make_oauth_token(self.parent, application=application)
        self.assertEqual(self.delete().status_code, 204)
        self.assertTrue(Application.objects.filter(pk=application.pk).exists())
        self.assertFalse(AccessToken.objects.filter(pk=access.pk).exists())

    def test_activity_scrubs_attributed_and_deleted_generic_targets_and_preserves_unrelated_activity(self):
        private = self.journal(self.parent)
        deleted = ActivityEvent.objects.create(actor=self.parent, subject=self.child, category="system", event_type="synthetic", summary="Departing name", context={"secret": "private"})
        target_only = ActivityEvent.objects.create(target=private, category="system", event_type="synthetic", summary="Anonymous target with private text")
        keep = ActivityEvent.objects.create(actor=self.successor, subject=self.child, category="system", event_type="synthetic", summary="Unrelated family activity")
        foreign = ActivityEvent.objects.create(actor=self.other.parents[0], category="system", event_type="synthetic", summary="Other family activity")
        orphan = ActivityEvent.objects.create(category="system", event_type="synthetic", summary="Historically unattributed text cannot be identified by name")
        self.assertEqual(self.delete().status_code, 204)
        self.assertFalse(ActivityEvent.objects.filter(pk__in=[deleted.pk, target_only.pk]).exists())
        self.assertCountEqual(ActivityEvent.objects.values_list("pk", flat=True), [keep.pk, foreign.pk, orphan.pk])

    def test_mixed_family_activity_preserves_foreign_attribution_and_redacts_departing_data(self):
        private = self.journal(self.parent)
        event = ActivityEvent.objects.create(subject=self.other.children[0], target=private, category="system", event_type="synthetic", summary="Inconsistent cross-family activity", context={"private": "departing body"}, coins_delta=5)
        attributed = ActivityEvent.objects.create(actor=self.parent, subject=self.other.children[0], category="system", event_type="synthetic", summary="Departing name")
        response = self.delete()
        self.assertEqual(response.status_code, 204)
        for row in (event, attributed):
            row.refresh_from_db()
            self.assertEqual(row.subject_id, self.other.children[0].pk)
            self.assertIsNone(row.actor_id)
            self.assertIsNone(row.target_id)
            self.assertIsNone(row.target_ct_id)
            self.assertIsNone(row.coins_delta)
            self.assertEqual(row.summary, "Account activity removed")
            self.assertEqual(row.context, {})
        self.assertFalse(ChronicleEntry.objects.filter(pk=private.pk).exists())

    def test_reauthentication_is_throttled_per_account(self):
        for _ in range(10):
            self.assertEqual(self.delete(password="wrong").status_code, 400)
        self.assertEqual(self.delete(password="wrong").status_code, 429)
        self.assertEqual(self.client.get(BASE).status_code, 200)

    def test_closure_queries_do_not_grow_per_ledger_entry(self):
        self.deactivate_successor()
        self.addCleanup(ContentType.objects.clear_cache)
        counts = []
        user_reads = []
        batch_queries = []
        for history_size in (2000, 4000):
            previous_size = CoinLedger.objects.filter(user=self.child).count()
            CoinLedger.objects.bulk_create([
                CoinLedger(user=self.child, reason="adjustment", amount=1)
                for _ in range(history_size - previous_size)
            ])
            # Reuse the same household after each real successful closure,
            # keeping fixture setup out of the query comparison.
            # A closure can create ContentTypes for auto-created through
            # models. Its rollback must not leave stale cached row IDs, and
            # both measurements should start with the same cold cache.
            ContentType.objects.clear_cache()
            with transaction.atomic():
                with CaptureQueriesContext(connection) as queries:
                    response = self.close()
                self.assertEqual(response.status_code, 204)
                counts.append(len(queries))
                user_reads.append(sum(
                    query["sql"].lstrip().upper().startswith("SELECT")
                    and 'FROM "projects_user"' in query["sql"]
                    for query in queries
                ))
                # Django chunks ledger DELETEs and the reverse nullable
                # PrintRequest receipt lookups according to DB parameter
                # limits. Those batches may grow; ownership reads must not.
                batch_queries.append(sum(
                    (query["sql"].lstrip().upper().startswith("DELETE") and 'FROM "rewards_coinledger"' in query["sql"])
                    or (query["sql"].lstrip().upper().startswith("SELECT") and 'FROM "printing_printrequest"' in query["sql"])
                    for query in queries
                ))
                transaction.set_rollback(True)
        fixed_queries = [count - batches for count, batches in zip(counts, batch_queries)]
        summary = f"Closure queries for 2000/4000 ledger entries: total={counts}, user_selects={user_reads}, orm_batches={batch_queries}, fixed={fixed_queries}"
        logging.getLogger(__name__).info(summary)
        self.assertLessEqual(user_reads[1], 10, summary)
        self.assertLessEqual(user_reads[1], user_reads[0] + 2, summary)
        self.assertLessEqual(fixed_queries[1], fixed_queries[0] + 2, summary)
        self.assertLessEqual(counts[1], counts[0] + 50, summary)

    def test_closure_does_not_create_generic_activity_content_types(self):
        self.deactivate_successor()
        through_model = User.groups.through._meta
        ContentType.objects.filter(app_label=through_model.app_label, model=through_model.model_name).delete()
        ContentType.objects.clear_cache()
        self.addCleanup(ContentType.objects.clear_cache)
        before = set(ContentType.objects.values_list("app_label", "model"))
        self.assertEqual(self.close().status_code, 204)
        self.assertEqual(set(ContentType.objects.values_list("app_label", "model")), before)


class FamilyClosureCleanupTests(LifecycleSetup, TransactionTestCase):
    def test_last_parent_closure_removes_family_credentials_and_records_with_durable_retry_and_global_boundaries(self):
        self.deactivate_successor()
        private = self.journal(self.child)
        child_name = self.save_file(self.child, "avatar", "child.png")
        reward = Reward.objects.create(family=self.family, name="Family reward", cost_coins=1)
        reward_name = self.save_file(reward, "image", "reward.png")
        other_name = self.save_file(self.other.children[0], "avatar", "other.png")
        planner = HomeworkAISettings.objects.create(family=self.family, provider="openai", model="synthetic", encrypted_api_key=b"synthetic")
        printer = PrinterProfile.objects.create(family=self.family, name="Private printer", serial="synthetic", encrypted_secret=b"synthetic", created_by=self.parent)
        google = GoogleAccount.objects.create(user=self.child, google_id="synthetic", google_email="child@example.test", encrypted_credentials=b"synthetic")
        access, _ = make_oauth_token(self.child)
        sprite = SpriteAsset.objects.create(slug="global", image="global.png", created_by=self.parent, frame_width_px=1, frame_height_px=1)
        event = ActivityEvent.objects.create(target=private, category="system", event_type="synthetic", summary="Private target")
        orphan = ActivityEvent.objects.create(category="system", event_type="synthetic", summary="Unattributed historic record")
        self.assertEqual(self.close().status_code, 204)
        for model, pk in ((Family, self.family.pk), (ChronicleEntry, private.pk), (Reward, reward.pk), (HomeworkAISettings, planner.pk), (PrinterProfile, printer.pk), (GoogleAccount, google.pk), (AccessToken, access.pk), (ActivityEvent, event.pk)):
            self.assertFalse(model.objects.filter(pk=pk).exists())
        self.assertFalse(User.objects.filter(family_id=self.family.pk).exists())
        self.assertTrue(ActivityEvent.objects.filter(pk=orphan.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.other.children[0].pk).exists())
        self.assertTrue(default_storage.exists(other_name))
        sprite.refresh_from_db()
        self.assertIsNone(sprite.created_by_id)
        self.assertCountEqual(PendingFileDeletion.objects.values_list("storage_key", flat=True), [child_name, reward_name])
        with patch("apps.accounts.file_cleanup.default_storage.delete", side_effect=OSError("synthetic storage interruption")):
            self.assertEqual(process_pending_file_deletions(), {"deleted": 0, "failed": 2, "referenced": 0})
        self.assertEqual(PendingFileDeletion.objects.count(), 2)
        retry_at = max(PendingFileDeletion.objects.values_list("retry_at", flat=True))
        self.assertEqual(process_pending_file_deletions(now=retry_at), {"deleted": 2, "failed": 0, "referenced": 0})
        self.assertFalse(default_storage.exists(child_name))
        self.assertFalse(default_storage.exists(reward_name))
        self.assertTrue(default_storage.exists(other_name))
