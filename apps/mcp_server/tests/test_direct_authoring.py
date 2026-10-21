"""Direct MCP authoring shares validation, durable identities and web workflows."""
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event
from unittest import skipUnless
from uuid import uuid4

from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError

from apps.achievements.models import Badge, Skill, SkillCategory, SkillPrerequisite, Subject
from apps.chores.models import Chore
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    AddSkillPrerequisiteIn, CreateBadgeIn, CreateChoreIn, CreateQuestDefinitionIn, CreateSkillIn,
    UpdateBadgeIn, UpdateCategoryIn, UpdateChoreIn, UpdateRewardIn, UpdateSkillIn, UpdateSubjectIn,
)
from apps.mcp_server.tools import achievements, chores, quests, rewards
from apps.notifications.models import Notification, NotificationType
from apps.quests.models import Quest, QuestDefinition
from apps.rewards.models import Reward, RewardWishlist
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.validation import validate_badge_criteria, validate_content
from apps.rpg.models import ContentPackEntry, RPGContentOverride
from config.tests.factories import make_family
from apps.accounts.models import User


class DirectAuthoringTests(TestCase):
    def setUp(self):
        own = make_family("Author", parents=[{"username": "author", "is_staff": True}], children=[{"username": "author-child"}])
        foreign = make_family("Other author", parents=[{"username": "other-author", "is_staff": True}], children=[{"username": "other-child"}])
        self.parent, self.child = own.parents[0], own.children[0]
        self.foreign_child, self.foreign_family = foreign.children[0], foreign.family
        self.a = SkillCategory.objects.create(name="Author category A", color="#112233")
        self.b = SkillCategory.objects.create(name="Author category B")
        self.subject = Subject.objects.create(category=self.a, name="Author subject")

    def test_malformed_badge_create_is_rejected_before_persistence(self):
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.create_badge(CreateBadgeIn(name="Invalid badge", description="Invalid", criteria_type="projects_completed", criteria_value={"count": "invalid"}))
        self.assertFalse(Badge.objects.exists())

    def test_badge_update_validates_merged_rule_before_saving(self):
        badge = Badge.objects.create(name="Original badge", description="Rule", criteria_type="projects_completed", criteria_value={"count": 2})
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.update_badge(UpdateBadgeIn(badge_id=badge.pk, criteria_value={"count": "invalid"}))
        badge.refresh_from_db()
        self.assertEqual(badge.criteria_value, {"count": 2})

    def test_numeric_strings_booleans_and_nonfinite_badge_values_are_rejected(self):
        for value in ("2", True, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValidationError):
                    validate_badge_criteria("projects_completed", {"count": value})
                with override_user(self.parent), self.assertRaises(MCPValidationError):
                    achievements.create_badge(CreateBadgeIn(name="Invalid numeric", description="Rule", criteria_type="projects_completed", criteria_value={"count": value}))
                with self.assertRaises(ContentPackError):
                    validate_content({"badges": {"badges": [{"name": "Invalid pack rule", "criteria_type": "projects_completed", "criteria_value": {"count": value}}]}})
        self.assertFalse(Badge.objects.exists())

    def test_numeric_string_merged_and_type_only_badge_edits_leave_original_untouched(self):
        badge = Badge.objects.create(name="Valid rule", description="Rule", criteria_type="projects_completed", criteria_value={"count": 2})
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.update_badge(UpdateBadgeIn(badge_id=badge.pk, criteria_value={"count": "2"}, name="Must roll back"))
        badge.refresh_from_db()
        self.assertEqual((badge.name, badge.criteria_value), ("Valid rule", {"count": 2}))
        badge.criteria_type, badge.criteria_value = "first_project", {"count": "2"}
        badge.save()
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.update_badge(UpdateBadgeIn(badge_id=badge.pk, criteria_type="projects_completed"))
        badge.refresh_from_db()
        self.assertEqual(badge.criteria_type, "first_project")

    def test_full_runtime_badge_vocabulary_and_award_coins_are_authorable(self):
        with override_user(self.parent):
            for kind in Badge.CriteriaType.values:
                result = achievements.create_badge(CreateBadgeIn(name=f"Runtime {kind}", description="Rule", criteria_type=kind, award_coins=False))
                self.assertFalse(Badge.objects.get(pk=result["id"]).award_coins)
        self.assertEqual(Badge.objects.count(), len(Badge.CriteriaType.values))

    def test_create_skill_rejects_subject_from_another_category(self):
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.create_skill(CreateSkillIn(name="Hidden skill", category_id=self.b.pk, subject_id=self.subject.pk))
        self.assertFalse(Skill.objects.exists())

    def test_skill_category_edit_checks_retained_subject(self):
        skill = Skill.objects.create(name="Retained subject", category=self.a, subject=self.subject)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.update_skill(UpdateSkillIn(skill_id=skill.pk, category_id=self.b.pk))
        skill.refresh_from_db()
        self.assertEqual(skill.category_id, self.a.pk)

    def test_subject_move_cannot_leave_inconsistent_child_skills(self):
        Skill.objects.create(name="Attached skill", category=self.a, subject=self.subject)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.update_subject(UpdateSubjectIn(subject_id=self.subject.pk, category_id=self.b.pk))
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.category_id, self.a.pk)

    def test_two_edge_prerequisite_cycle_is_rejected_atomically(self):
        a = Skill.objects.create(name="A", category=self.a, is_locked_by_default=True)
        b = Skill.objects.create(name="B", category=self.a, is_locked_by_default=True)
        SkillPrerequisite.objects.create(skill=a, required_skill=b, required_level=1)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.add_skill_prerequisite(AddSkillPrerequisiteIn(skill_id=b.pk, required_skill_id=a.pk, required_level=1))
        self.assertEqual(SkillPrerequisite.objects.count(), 1)

    def test_cycle_validation_uses_edges_beyond_the_catalog_audit_page_bound(self):
        skills = Skill.objects.bulk_create([Skill(name=f"Long dependency {n}", category=self.a) for n in range(5002)])
        SkillPrerequisite.objects.bulk_create([SkillPrerequisite(skill=left, required_skill=right, required_level=1) for left, right in zip(skills, skills[1:])])
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            achievements.add_skill_prerequisite(AddSkillPrerequisiteIn(skill_id=skills[-1].pk, required_skill_id=skills[0].pk, required_level=1))
        self.assertEqual(SkillPrerequisite.objects.count(), 5001)

    def test_existing_baseline_category_edit_survives_real_loader_reload(self):
        with override_user(self.parent):
            achievements.update_category(UpdateCategoryIn(category_id=self.a.pk, color="#abcdef"))
        ContentPack("content/rpg/initial", parsed_content={"skill_tree": {"categories": [{"name": self.a.name, "color": "#112233"}]}}).load(stdout=io.StringIO())
        self.a.refresh_from_db()
        self.assertEqual(self.a.color, "#abcdef")

    def test_foreign_owned_catalog_entry_cannot_be_overwritten_directly(self):
        ContentPackEntry.objects.create(pack="other-owned-pack", family=self.foreign_family, kind="skillcategory", key="other-category", model_label="achievements.skillcategory", object_id=self.a.pk)
        with override_user(self.parent), self.assertRaises(MCPPermissionDenied):
            achievements.update_category(UpdateCategoryIn(category_id=self.a.pk, color="#abcdef"))
        self.a.refresh_from_db()
        self.assertEqual(self.a.color, "#112233")

    def test_direct_authoring_rechecks_stale_actor_permissions_under_locks(self):
        for change in ({"is_active": False}, {"is_staff": False}, {"role": "child"}, {"family_id": self.foreign_family.pk}):
            with self.subTest(change=change):
                User.objects.filter(pk=self.parent.pk).update(**change)
                with override_user(self.parent), self.assertRaises(MCPPermissionDenied):
                    achievements.update_category(UpdateCategoryIn(category_id=self.a.pk, color="#abcdef"))
                User.objects.filter(pk=self.parent.pk).update(is_active=True, is_staff=True, role="parent", family_id=self.child.family_id)
        self.a.refresh_from_db()
        self.assertEqual(self.a.color, "#112233")
        self.assertFalse(RPGContentOverride.objects.exists())

    def test_renamed_taxonomy_keeps_original_identity_and_prerequisites_on_reload(self):
        parsed = {"skill_tree": {
            "categories": [{"name": "Loaded category", "color": "#112233"}],
            "subjects": [{"name": "Loaded subject", "category": "Loaded category"}],
            "skills": [
                {"name": "Loaded base", "category": "Loaded category", "subject": "Loaded subject"},
                {"name": "Loaded advanced", "category": "Loaded category", "subject": "Loaded subject", "prereqs": [{"skill": "Loaded base", "level": 1}]},
            ],
        }, "badges": {"badges": [{"name": "Loaded badge", "description": "Rule", "criteria_type": "projects_completed", "criteria_value": {"count": 2}}]}}
        ContentPack("content/rpg/initial", parsed_content=parsed).load(stdout=io.StringIO())
        category = SkillCategory.objects.get(name="Loaded category")
        subject = Subject.objects.get(name="Loaded subject")
        base, advanced = Skill.objects.get(name="Loaded base"), Skill.objects.get(name="Loaded advanced")
        badge = Badge.objects.get(name="Loaded badge")
        with override_user(self.parent):
            achievements.update_category(UpdateCategoryIn(category_id=category.pk, name="Renamed category"))
            achievements.update_subject(UpdateSubjectIn(subject_id=subject.pk, name="Renamed subject"))
            achievements.update_skill(UpdateSkillIn(skill_id=advanced.pk, name="Renamed advanced", description="Preserved edit"))
            achievements.add_skill_prerequisite(AddSkillPrerequisiteIn(skill_id=advanced.pk, required_skill_id=base.pk, required_level=3))
            achievements.update_badge(UpdateBadgeIn(badge_id=badge.pk, name="Renamed badge", award_coins=False))
        ContentPack("content/rpg/initial", parsed_content=parsed).load(stdout=io.StringIO())
        advanced.refresh_from_db()
        badge.refresh_from_db()
        self.assertEqual(SkillCategory.objects.get(pk=category.pk).name, "Renamed category")
        self.assertEqual(Subject.objects.get(pk=subject.pk).name, "Renamed subject")
        self.assertEqual((advanced.name, advanced.description), ("Renamed advanced", "Preserved edit"))
        self.assertEqual(SkillPrerequisite.objects.get(skill=advanced).required_level, 3)
        self.assertEqual((badge.name, badge.award_coins), ("Renamed badge", False))
        self.assertFalse(Skill.objects.filter(name="Loaded advanced").exists())
        self.assertFalse(Badge.objects.filter(name="Loaded badge").exists())
        override = RPGContentOverride.objects.get(model_label="achievements.skill", object_id=advanced.pk)
        self.assertEqual(override.source_lookup, {"name": "Loaded advanced", "category_id": category.pk})
        self.assertEqual(override.values["_authoring"]["version"], 1)

    def test_own_pack_entry_keeps_claimed_identity_after_direct_rename(self):
        parsed = {"skill_tree": {
            "categories": [{"name": "Owned pack category"}],
            "subjects": [{"name": "Owned pack subject", "category": "Owned pack category"}],
            "skills": [{"name": "Owned pack skill", "category": "Owned pack category", "subject": "Owned pack subject", "levels": {"1": "First"}}],
        }}
        options = {"pack_key": "owned-direct-test", "family": self.parent.family, "parsed_content": parsed}
        ContentPack("content/rpg/initial", **options).load(stdout=io.StringIO())
        skill = Skill.objects.get(name="Owned pack skill")
        with override_user(self.parent):
            achievements.update_skill(UpdateSkillIn(skill_id=skill.pk, name="Renamed owned skill"))
        ContentPack("content/rpg/initial", **options).load(stdout=io.StringIO())
        skill.refresh_from_db()
        self.assertEqual(skill.name, "Renamed owned skill")
        self.assertEqual(ContentPackEntry.objects.get(model_label="achievements.skill", object_id=skill.pk).pack, "owned-direct-test")
        self.assertFalse(Skill.objects.filter(name="Owned pack skill").exists())

    def test_renamed_source_identity_cannot_be_reused_by_a_second_direct_row(self):
        with override_user(self.parent):
            achievements.update_category(UpdateCategoryIn(category_id=self.a.pk, name="Renamed source"))
            with self.assertRaises(MCPValidationError):
                from apps.mcp_server.schemas import CreateCategoryIn
                achievements.create_category(CreateCategoryIn(name="Author category A"))
        self.assertEqual(SkillCategory.objects.filter(name="Author category A").count(), 0)

    def test_chore_create_preserves_explicit_deadline_and_xp(self):
        with override_user(self.parent):
            result = chores.create_chore(CreateChoreIn(title="Deadline chore", recurrence="one_time", due_date=date(2026, 11, 1), xp_reward=35))
        chore = Chore.objects.get(pk=result["id"])
        self.assertEqual(chore.due_date, date(2026, 11, 1))
        self.assertEqual(chore.xp_reward, 35)

    def test_recurring_chore_rejects_deadline(self):
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            chores.create_chore(CreateChoreIn(title="Invalid schedule", recurrence="daily", due_date=date(2026, 11, 1)))
        self.assertFalse(Chore.objects.exists())

    def test_chore_recurrence_edit_clears_previous_deadline(self):
        chore = Chore.objects.create(family=self.parent.family, created_by=self.parent, title="Former deadline", recurrence="one_time", due_date=date(2026, 11, 1))
        with override_user(self.parent):
            chores.update_chore(UpdateChoreIn(chore_id=chore.pk, recurrence="daily"))
        chore.refresh_from_db()
        self.assertIsNone(chore.due_date)

    def test_chore_omission_retains_deadline_and_explicit_null_clears_it(self):
        chore = Chore.objects.create(family=self.parent.family, created_by=self.parent, title="Keep deadline", recurrence="one_time", due_date=date(2026, 11, 1))
        with override_user(self.parent):
            chores.update_chore(UpdateChoreIn(chore_id=chore.pk, description="Metadata", xp_reward=0))
            chore.refresh_from_db()
            self.assertEqual(chore.due_date, date(2026, 11, 1))
            self.assertEqual(chore.xp_reward, 0)
            chores.update_chore(UpdateChoreIn(chore_id=chore.pk, due_date=None))
        chore.refresh_from_db()
        self.assertIsNone(chore.due_date)

    def test_invalid_merged_chore_edit_keeps_every_original_field(self):
        chore = Chore.objects.create(family=self.parent.family, created_by=self.parent, title="Original chore", recurrence="one_time", due_date=date(2026, 11, 1))
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            chores.update_chore(UpdateChoreIn(chore_id=chore.pk, title="Must roll back", recurrence="daily", due_date=date(2026, 12, 1)))
        chore.refresh_from_db()
        self.assertEqual((chore.title, chore.recurrence, chore.due_date), ("Original chore", "one_time", date(2026, 11, 1)))

    def test_failed_quest_assignment_does_not_leave_definition(self):
        params = CreateQuestDefinitionIn(name="Failed assignment", description="Rule", quest_type="collection", target_value=2, assigned_to_id=self.foreign_child.pk)
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            quests.create_quest_definition(params)
        self.assertFalse(QuestDefinition.objects.filter(name=params.name).exists())

    def test_uuid_quest_retry_returns_original_creation(self):
        params = CreateQuestDefinitionIn(request_id=uuid4(), name="One definition", description="Rule", quest_type="collection", target_value=2)
        with override_user(self.parent):
            first = quests.create_quest_definition(params)
            self.assertEqual(quests.create_quest_definition(params), first)
        self.assertEqual(QuestDefinition.objects.filter(name=params.name).count(), 1)

    def test_same_family_badge_gate_failure_rolls_back_definition_and_retry_receipt(self):
        badge = Badge.objects.create(name="Unmet gate", description="Rule", criteria_type="first_clock_in")
        params = CreateQuestDefinitionIn(request_id=uuid4(), name="Gated creation", description="Rule", quest_type="collection", target_value=2, required_badge_id=badge.pk, assigned_to_id=self.child.pk)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            quests.create_quest_definition(params)
        self.assertFalse(QuestDefinition.objects.filter(name=params.name).exists())
        self.assertFalse(Quest.objects.exists())

    def test_same_family_active_campaign_failure_rolls_back_new_definition(self):
        with override_user(self.parent):
            quests.create_quest_definition(CreateQuestDefinitionIn(name="Already active", description="Rule", quest_type="collection", target_value=2, assigned_to_id=self.child.pk))
            with self.assertRaises(MCPValidationError):
                quests.create_quest_definition(CreateQuestDefinitionIn(name="Must not persist", description="Rule", quest_type="collection", target_value=2, assigned_to_id=self.child.pk))
        self.assertFalse(QuestDefinition.objects.filter(name="Must not persist").exists())
        self.assertEqual(Quest.objects.count(), 1)

    def test_assigned_quest_uuid_reuses_result_and_honors_deletion_tombstone(self):
        params = CreateQuestDefinitionIn(request_id=uuid4(), name="One assigned run", description="Rule", quest_type="collection", target_value=2, assigned_to_id=self.child.pk)
        with override_user(self.parent):
            first = quests.create_quest_definition(params)
            self.assertEqual(quests.create_quest_definition(params), first)
            Quest.objects.get(pk=first["quest"]["id"]).delete()
            with self.assertRaises(MCPNotFoundError):
                quests.create_quest_definition(params)
        self.assertEqual(QuestDefinition.objects.filter(name=params.name).count(), 1)
        self.assertFalse(Quest.objects.exists())

    def test_mcp_restock_notifies_and_clears_wishlist_once(self):
        reward = Reward.objects.create(family=self.parent.family, name="Restock", cost_coins=10, stock=0)
        RewardWishlist.objects.create(user=self.child, reward=reward)
        with override_user(self.parent):
            rewards.update_reward(UpdateRewardIn(reward_id=reward.pk, stock=1))
            rewards.update_reward(UpdateRewardIn(reward_id=reward.pk, description="Metadata only"))
        self.assertFalse(RewardWishlist.objects.filter(reward=reward).exists())
        self.assertEqual(Notification.objects.filter(user=self.child, notification_type=NotificationType.REWARD_RESTOCKED).count(), 1)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL catalog locks")
class DirectAuthoringConcurrencyTests(TransactionTestCase):
    def setUp(self):
        own = make_family("Concurrent author", parents=[{"username": "race-author", "is_staff": True}])
        other = make_family("Concurrent other", parents=[{"username": "race-other", "is_staff": True}])
        self.parent, self.other = own.parents[0], other.parents[0]
        self.category = SkillCategory.objects.create(name="Concurrent category")
        self.left = Skill.objects.create(name="Concurrent left", category=self.category)
        self.right = Skill.objects.create(name="Concurrent right", category=self.category)

    def race(self, operations):
        ready = Barrier(2)

        def invoke(actor_id, operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '20s'")
                actor = User.objects.get(pk=actor_id)
                ready.wait(timeout=5)
                with override_user(actor):
                    try:
                        operation()
                        return "saved"
                    except (MCPPermissionDenied, MCPValidationError):
                        return "rejected"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(invoke, actor.pk, operation) for actor, operation in operations]
            return sorted(future.result(timeout=30) for future in futures)

    def test_opposite_concurrent_prerequisites_cannot_commit_a_cycle(self):
        result = self.race([
            (self.parent, lambda: achievements.add_skill_prerequisite(AddSkillPrerequisiteIn(skill_id=self.left.pk, required_skill_id=self.right.pk, required_level=1))),
            (self.parent, lambda: achievements.add_skill_prerequisite(AddSkillPrerequisiteIn(skill_id=self.right.pk, required_skill_id=self.left.pk, required_level=1))),
        ])
        self.assertEqual(result, ["rejected", "saved"])
        self.assertEqual(SkillPrerequisite.objects.count(), 1)

    def test_competing_families_cannot_overwrite_the_first_authoring_claim(self):
        result = self.race([
            (self.parent, lambda: achievements.update_category(UpdateCategoryIn(category_id=self.category.pk, color="#112233"))),
            (self.other, lambda: achievements.update_category(UpdateCategoryIn(category_id=self.category.pk, color="#abcdef"))),
        ])
        self.assertEqual(result, ["rejected", "saved"])
        self.assertEqual(RPGContentOverride.objects.filter(model_label="achievements.skillcategory", object_id=self.category.pk).count(), 1)

    def test_cross_family_source_reuse_sees_the_committed_catalog_claim(self):
        from unittest.mock import patch
        from apps.mcp_server.context import get_current_user
        from apps.rpg.content import authoring

        other_category = SkillCategory.objects.create(name="Other concurrent source")
        first_ready, second_at_lock, release_first = Event(), Event(), Event()
        catalog_lock = authoring._catalog_lock

        def observe_catalog_lock():
            if get_current_user().pk == self.other.pk:
                second_at_lock.set()
            catalog_lock()

        def invoke(actor_id, category_id, name, *, hold=False):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '20s'")
                actor = User.objects.get(pk=actor_id)
                with override_user(actor):
                    try:
                        with transaction.atomic():
                            achievements.update_category(UpdateCategoryIn(category_id=category_id, name=name))
                            if hold:
                                first_ready.set()
                                if not release_first.wait(timeout=10):
                                    raise AssertionError("The second author did not reach the catalog fence")
                        return "saved"
                    except (MCPPermissionDenied, MCPValidationError):
                        return "rejected"
            finally:
                connection.close()

        with patch.object(authoring, "_catalog_lock", side_effect=observe_catalog_lock):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(invoke, self.parent.pk, self.category.pk, "Renamed concurrent source", hold=True)
                try:
                    self.assertTrue(first_ready.wait(timeout=5))
                    second = pool.submit(invoke, self.other.pk, other_category.pk, self.category.name)
                    self.assertTrue(second_at_lock.wait(timeout=5))
                finally:
                    release_first.set()
                self.assertEqual(first.result(timeout=30), "saved")
                self.assertEqual(second.result(timeout=30), "rejected")
        self.category.refresh_from_db()
        other_category.refresh_from_db()
        self.assertEqual(self.category.name, "Renamed concurrent source")
        self.assertEqual(other_category.name, "Other concurrent source")
        self.assertFalse(RPGContentOverride.objects.filter(
            model_label="achievements.skillcategory", object_id=other_category.pk,
        ).exists())
