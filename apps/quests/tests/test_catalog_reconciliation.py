"""Explicit catalog identity reconciliation preserves accepted promises."""
from copy import deepcopy
from datetime import timedelta
from importlib import import_module
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.quests.controls import control_context, retry_challenge, retry_state
from apps.quests.goals import _occurrence, ingest_activity, list_goals
from apps.quests.models import (
    ChallengeGoal, ChallengeOccurrence, ChallengePin, Quest, QuestDefinition,
    QuestParticipant, QuestRewardItem, QuestSkillTag,
)
from apps.quests.queries import active_system_definitions
from apps.quests.services import QuestService
from apps.rpg.content.errors import ContentAuthorPermissionDenied, ContentObjectNotFound
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.models import ContentPackEntry, ContentPackPublication, ItemDefinition, RPGContentOverride
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class CatalogReconciliationTests(TestCase):
    def setUp(self):
        own = make_family("Reconciliation authors", parents=[{"username": "alias-author", "is_staff": True}],
                          children=[{"username": "alias-child"}, {"username": "alias-sibling"}])
        other = make_family("Other household", parents=[{"username": "other-author", "is_staff": True}],
                            children=[{"username": "other-child"}])
        self.actor, self.child, self.other = own.parents[0], own.children[0], other.parents[0]
        self.sibling = own.children[1]
        self.at = timezone.now()
        self.values = dict(name="Explicit duplicate", description="The same saved promise", quest_type="collection",
                           target_value=3, duration_days=7, is_system=True, coin_reward=5,
                           trigger_filter={"allowed_triggers": ["habit_log"]})
        self.source = QuestDefinition.objects.create(**self.values, created_by=self.actor)
        self.canonical = QuestDefinition.objects.create(**self.values)

    @property
    def service(self):
        return import_module("apps.quests.reconciliation")

    def preview(self, **changes):
        return self.service.preview_reconciliation(self.actor, self.source.pk, self.canonical.pk,
                                                    changes.pop("request_id", uuid4()), **changes)

    def publish(self, preview=None, **changes):
        preview = preview or self.preview()
        return self.service.publish_reconciliation(self.actor, preview["preview_id"],
                                                    preview["content_digest"], **changes)

    def saved(self, definition=None, *, repeat_days=0, paid=False):
        definition = definition or self.source
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=definition, is_catalog=True,
            name="Frozen name", description="Frozen description", metric="count", target=3, unit="actions",
            trigger_filter=definition.trigger_filter, timezone_name="America/Phoenix",
            starts_at=self.at - timedelta(days=8), ends_at=self.at - timedelta(days=1), repeat_days=repeat_days,
            coin_reward=5,
        )
        occurrence = ChallengeOccurrence.objects.create(
            goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
            status="completed" if paid else "active", completed_at=self.at if paid else None,
            awarded_at=self.at if paid else None,
            snapshot={"name": goal.name, "description": goal.description, "metric": "count", "target": "3",
                      "unit": "actions", "filter": goal.trigger_filter, "coins": 5, "xp": 0,
                      "skill_tags": [], "items": [], "catalog_name": definition.name, "catalog_type": "collection"},
        )
        return goal, occurrence

    def test_preview_is_nonmutating_publish_restores_one_offer_and_retains_provenance(self):
        source_before = QuestDefinition.objects.filter(pk=self.source.pk).values().get()
        self.assertFalse(active_system_definitions().exists())
        preview = self.preview()
        self.assertFalse(ChallengeGoal.objects.exists())
        self.source.refresh_from_db()
        self.assertIsNone(self.source.superseded_by_id)
        self.assertEqual(preview["source_definition"]["creator_provenance"], "same_family_parent")
        result = self.publish(preview)
        self.assertIsNotNone(result["published_at"])
        self.assertEqual(list(active_system_definitions().values_list("pk", flat=True)), [self.canonical.pk])
        self.assertEqual(QuestDefinition.objects.filter(pk=self.source.pk).values().get(),
                         {**source_before, "superseded_by_id": self.canonical.pk})
        self.assertFalse(CoinLedger.objects.exists())

    def test_solo_alias_goal_keeps_identity_anchor_pin_and_every_saved_field(self):
        for definition in (self.source, self.canonical):
            QuestDefinition.objects.filter(pk=definition.pk).update(is_repeatable=True)
        goal, occurrence = self.saved(repeat_days=7)
        pin = ChallengePin.objects.create(user=self.child, occurrence=occurrence)
        before = ChallengeGoal.objects.filter(pk=goal.pk).values().get()
        saved_window = ChallengeOccurrence.objects.filter(pk=occurrence.pk).values().get()
        preview = self.preview()
        # Ordinary saved progress is not part of the identity binding.
        ChallengeOccurrence.objects.filter(pk=occurrence.pk).update(progress=1)
        self.publish(preview)
        self.assertEqual(ChallengeGoal.objects.filter(pk=goal.pk).values().get(),
                         {**before, "catalog_definition_id": self.canonical.pk})
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=occurrence.pk).values().get(),
                         {**saved_window, "progress": 1})
        pin.refresh_from_db()
        self.assertEqual(pin.occurrence_id, occurrence.pk)
        goal.refresh_from_db()
        self.assertIsNotNone(_occurrence(goal, self.at))
        self.assertEqual(goal.repeat_days, 7)

    def test_overlap_keeps_current_promises_but_only_canonical_opens_future_repeat(self):
        QuestDefinition.objects.filter(pk__in=[self.source.pk, self.canonical.pk]).update(is_repeatable=True)
        alias_goal, old = self.saved(repeat_days=7)
        canonical_goal, _ = self.saved(self.canonical, repeat_days=7)
        before = list(ChallengeGoal.objects.order_by("pk").values())
        windows = list(ChallengeOccurrence.objects.order_by("pk").values())
        self.publish()
        self.assertEqual(list(ChallengeGoal.objects.order_by("pk").values()), before)
        self.assertEqual(list(ChallengeOccurrence.objects.order_by("pk").values()), windows)
        self.assertIsNone(_occurrence(alias_goal, self.at))
        self.assertIsNotNone(_occurrence(canonical_goal, self.at))
        self.assertEqual(_occurrence(alias_goal, old.starts_at).pk, old.pk)

    def test_preview_and_published_replays_are_original_projections_after_catalog_edits(self):
        request_id = uuid4()
        preview = self.preview(request_id=request_id)
        published = self.publish(preview)
        QuestDefinition.objects.filter(pk=self.canonical.pk).update(description="Later display edit")
        self.assertEqual(self.preview(request_id=request_id), preview)
        self.assertEqual(self.service.get_reconciliation(self.actor, preview["preview_id"]), published)
        self.assertEqual(self.publish(preview), published)
        self.assertEqual(ContentPackPublication.objects.count(), 1)

    def test_immutable_replays_do_not_reapply_affected_population_limit(self):
        request_id = uuid4()
        self.saved()
        preview = self.preview(request_id=request_id)
        published = self.publish(preview)
        # Equivalent to population growth beyond an operational cap: no new
        # identity operation is needed to recover a committed response.
        with patch.object(self.service, "MAX_MEMBERS", 1):
            self.assertEqual(self.preview(request_id=request_id), preview)
            self.assertEqual(self.publish(preview), published)
            self.assertEqual(self.service.get_reconciliation(self.actor, preview["preview_id"]), published)

    def test_cooperative_exception_requires_publish_ack_and_keeps_personal_promise(self):
        QuestDefinition.objects.filter(pk=self.canonical.pk).update(is_cooperative=True)
        goal, occurrence = self.saved()
        before = deepcopy(occurrence.snapshot)
        preview = self.preview()
        self.assertTrue(preview["requires_cooperative_acknowledgement"])
        with self.assertRaises(ContentPackError):
            self.publish(preview)
        result = self.publish(preview, acknowledge_cooperative_transition=True)
        self.assertTrue(result["acknowledged_cooperative_transition"])
        with self.assertRaises(ContentPackError):
            self.publish(preview)  # Replays must repeat the reviewed acknowledgement.
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, before)
        self.assertEqual(retry_state(occurrence, control_context(self.child))["reason"], "cooperative")
        with self.assertRaisesMessage(ValueError, "accepted individual version"):
            QuestService.start_co_op_quest(self.canonical.pk, [self.child, self.sibling])
        goal.refresh_from_db()
        self.assertEqual(goal.catalog_definition_id, self.canonical.pk)

    def unopened(self, definition=None):
        # Enrolled before its start (e.g. by a non-matching activity), so its
        # only one-time window has not been saved yet.
        definition = definition or self.source
        return ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=definition, is_catalog=True,
            name="Frozen name", description="Frozen description", metric="count", target=1, unit="actions",
            trigger_filter=definition.trigger_filter, timezone_name="America/Phoenix",
            starts_at=self.at - timedelta(hours=1), ends_at=self.at + timedelta(days=6), coin_reward=5,
        )

    def coins(self):
        return list(CoinLedger.objects.filter(user=self.child).order_by("pk").values_list("amount", flat=True))

    def test_cooperative_exception_keeps_an_unopened_personal_window_payable(self):
        QuestDefinition.objects.filter(pk=self.canonical.pk).update(is_cooperative=True)
        goal = self.unopened()
        self.publish(acknowledge_cooperative_transition=True)
        goal.refresh_from_db()
        self.assertEqual(goal.catalog_definition_id, self.canonical.pk)
        window = goal.occurrences.get()
        self.assertEqual((window.starts_at, window.ends_at), (goal.starts_at, goal.ends_at))
        ingest_activity(self.child, "habit", "h-1", "habit_log")
        self.assertEqual(self.coins(), [5])
        with self.assertRaisesMessage(ValueError, "accepted individual version"):
            QuestService.start_co_op_quest(self.canonical.pk, [self.child, self.sibling])

    def test_overlap_keeps_an_unopened_alias_window_payable(self):
        self.saved(self.canonical)
        goal = self.unopened()
        self.publish()
        goal.refresh_from_db()
        self.assertEqual(goal.catalog_definition_id, self.source.pk)
        self.assertEqual(goal.occurrences.count(), 1)
        ingest_activity(self.child, "habit", "h-1", "habit_log")
        self.assertEqual(self.coins(), [5])

    def test_cooperative_transition_cannot_cancel_a_standing_personal_repeat_rule(self):
        QuestDefinition.objects.filter(pk__in=[self.source.pk, self.canonical.pk]).update(is_repeatable=True)
        QuestDefinition.objects.filter(pk=self.canonical.pk).update(is_cooperative=True)
        goal, occurrence = self.saved(repeat_days=7)
        before = ChallengeGoal.objects.filter(pk=goal.pk).values().get()
        with self.assertRaises(ContentPackError):
            self.preview()
        self.assertEqual(ChallengeGoal.objects.filter(pk=goal.pk).values().get(), before)
        self.assertFalse(ContentPackPublication.objects.exists())
        self.assertTrue(ChallengeOccurrence.objects.filter(pk=occurrence.pk).exists())

    def test_all_other_authored_differences_fail_closed(self):
        for field, value in (("target_value", 99), ("duration_days", 8), ("coin_reward", 6),
                             ("xp_reward", 7), ("is_repeatable", True), ("description", "Changed"),
                             ("trigger_filter", {"allowed_triggers": ["chore_complete"]})):
            with self.subTest(field=field):
                QuestDefinition.objects.filter(pk=self.canonical.pk).update(**{field: value})
                with self.assertRaises(ContentPackError):
                    self.preview()
                QuestDefinition.objects.filter(pk=self.canonical.pk).update(**{field: self.values.get(field, False)})
        self.assertFalse(ContentPackPublication.objects.exists())
        self.assertFalse(QuestDefinition.objects.filter(superseded_by__isnull=False).exists())

    def test_reward_links_must_match_exact_ids_quantities_and_skill_weights(self):
        from apps.achievements.models import Skill, SkillCategory
        category = SkillCategory.objects.create(name="Reconcile tags")
        skill = Skill.objects.create(category=category, name="Skill")
        item = ItemDefinition.objects.create(name="Plain item", slug="reconcile-item", item_type="food")
        for definition in (self.source, self.canonical):
            QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=1)
            QuestSkillTag.objects.create(quest_definition=definition, skill=skill, xp_weight=2)
        self.preview()
        QuestRewardItem.objects.filter(quest_definition=self.canonical).update(quantity=2)
        with self.assertRaises(ContentPackError):
            self.preview()
        QuestRewardItem.objects.filter(quest_definition=self.canonical).update(quantity=1)
        QuestSkillTag.objects.filter(quest_definition=self.canonical).update(xp_weight=3)
        with self.assertRaises(ContentPackError):
            self.preview()

    def test_missing_foreign_and_revoked_authority_are_safe_and_nonmutating(self):
        with self.assertRaises(ContentAuthorPermissionDenied):
            self.service.preview_reconciliation(self.other, self.source.pk, self.canonical.pk, uuid4())
        with self.assertRaises(ContentObjectNotFound):
            self.service.preview_reconciliation(self.actor, 9999999, self.canonical.pk, uuid4())
        preview = self.preview()
        get_user_model().objects.filter(pk=self.actor.pk).update(is_staff=False)
        for action in (lambda: self.preview(), lambda: self.publish(preview),
                       lambda: self.service.get_reconciliation(self.actor, preview["preview_id"])):
            with self.assertRaises(ContentAuthorPermissionDenied):
                action()
        self.source.refresh_from_db()
        self.assertIsNone(self.source.superseded_by_id)

    def test_private_claimed_dependent_or_extra_root_selections_are_rejected(self):
        checks = (
            lambda: QuestDefinition.objects.filter(pk=self.source.pk).update(is_system=False),
            lambda: ContentPackEntry.objects.create(pack="owned", family=self.actor.family, kind="questdefinition",
                key="source", model_label="quests.questdefinition", object_id=self.source.pk),
            lambda: QuestDefinition.objects.create(**{**self.values, "name": "Dependent"}, prerequisite_quest=self.source),
            lambda: QuestDefinition.objects.create(**self.values),
            lambda: RPGContentOverride.objects.create(model_label="quests.questdefinition", object_id=self.canonical.pk,
                family=self.other.family, source_lookup={"name": self.source.name}, values={}),
        )
        for index, setup in enumerate(checks):
            with self.subTest(index=index):
                # An isolated savepoint restores each deliberately invalid candidate.
                from django.db import transaction
                with transaction.atomic():
                    setup()
                    with self.assertRaises(ContentPackError):
                        self.preview()
                    transaction.set_rollback(True)
        self.assertFalse(ContentPackPublication.objects.exists())

    def test_state_expiry_uuid_and_receipt_ownership_conflicts(self):
        preview = self.preview()
        conflict = self.service.ReconciliationConflict
        with self.assertRaises(ContentObjectNotFound):
            self.service.get_reconciliation(self.other, preview["preview_id"])
        with self.assertRaises(conflict):
            self.service.preview_reconciliation(self.actor, self.canonical.pk, self.source.pk, preview["preview_id"])
        with self.assertRaises(conflict):
            self.service.publish_reconciliation(self.actor, preview["preview_id"], "0" * 64)
        ContentPackPublication.objects.filter(pk=preview["preview_id"]).update(expires_at=self.at-timedelta(seconds=1))
        with self.assertRaises(conflict):
            self.publish(preview)
        preview = self.preview()
        self.saved()
        with self.assertRaises(conflict):
            self.publish(preview)

    def test_legacy_paid_alias_blocks_new_one_time_reward_without_rewriting_history(self):
        legacy = Quest.objects.create(definition=self.source, status="completed", start_date=self.at,
                                      end_date=self.at+timedelta(days=7))
        QuestParticipant.objects.create(quest=legacy, user=self.child)
        old = Quest.objects.filter(pk=legacy.pk).values().get()
        self.publish()
        list_goals(self.child)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())
        with self.assertRaisesMessage(ValueError, "already completed"):
            QuestService.start_quest(self.child, self.canonical.pk)
        self.assertEqual(Quest.objects.filter(pk=legacy.pk).values().get(), old)
        self.assertFalse(CoinLedger.objects.exists())

    def test_saved_paid_identity_cannot_retry_after_linking(self):
        goal, occurrence = self.saved(paid=True)
        before = ChallengeOccurrence.objects.filter(pk=occurrence.pk).values().get()
        self.publish()
        self.assertEqual(retry_state(occurrence, control_context(self.child))["reason"], "already_awarded")
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=occurrence.pk).values().get(), before)
        self.assertFalse(CoinLedger.objects.exists())

    def test_existing_retry_successor_pin_and_late_lifetime_completion_survive_link(self):
        self.canonical.delete()  # The owner root was offerable before the bundled duplicate existed.
        goal, original = self.saved()
        ChallengePin.objects.create(user=self.child, occurrence=original)
        successor, created = retry_challenge(self.child, original.pk)
        self.assertTrue(created)
        before = ChallengeOccurrence.objects.filter(pk=successor.pk).values().get()
        self.canonical = QuestDefinition.objects.create(**self.values)
        self.publish()
        replay, created = retry_challenge(self.child, original.pk)
        self.assertFalse(created)
        self.assertEqual(replay.pk, successor.pk)
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=successor.pk).values().get(), before)
        self.assertEqual(ChallengePin.objects.get(user=self.child).occurrence_id, successor.pk)
        for number in range(3):
            ingest_activity(self.child, "habit_log", f"late-original-{number}", "habit_log",
                            occurred_at=original.starts_at + timedelta(hours=1))
        original.refresh_from_db()
        successor.refresh_from_db()
        self.assertEqual((original.status, successor.status), ("completed", "closed"))
        self.assertIsNone(successor.awarded_at)
        self.assertEqual(successor.reward_receipt, {})
        self.assertEqual(list(CoinLedger.objects.values_list("amount", flat=True)), [5])
        self.assertEqual(retry_challenge(self.child, original.pk)[0].pk, successor.pk)

    def test_nullable_trigger_list_cannot_create_an_unreturnable_global_preview(self):
        QuestDefinition.objects.filter(pk__in=[self.source.pk, self.canonical.pk]).update(
            trigger_filter={"allowed_triggers": None})
        with self.assertRaises(ContentPackError):
            self.preview()
        self.assertFalse(ContentPackPublication.objects.exists())

    def test_reward_only_legacy_offer_is_not_rejected_as_unsupported_automatic_activity(self):
        QuestDefinition.objects.filter(pk__in=[self.source.pk, self.canonical.pk]).update(
            trigger_filter={"allowed_triggers": ["perfect_day"]})
        self.publish()
        quest = QuestService.start_quest(self.child, self.canonical.pk)
        self.assertEqual(quest.definition_id, self.canonical.pk)

    def test_bundled_reload_targets_only_canonical_and_retains_old_owned_row(self):
        self.publish()
        before = QuestDefinition.objects.filter(pk=self.source.pk).values().get()
        loader = ContentPack(".", namespace="", parsed_content={"quests": {"quests": [self.values]}})
        loader.load()
        self.assertEqual(QuestDefinition.objects.count(), 2)
        self.assertEqual(QuestDefinition.objects.filter(pk=self.source.pk).values().get(), before)

    def test_public_or_persisted_receipt_never_contains_private_goal_bindings(self):
        self.saved()
        preview = self.preview()
        self.publish(preview)
        receipt = ContentPackPublication.objects.get(pk=preview["preview_id"])
        forbidden = {"family_id", "user_id", "goal_id", "goal_ids", "affected_users", "affected_goals", "count"}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
        check(receipt.stats)
        check(receipt.changes)
