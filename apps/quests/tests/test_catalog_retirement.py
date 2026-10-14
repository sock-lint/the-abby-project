"""Catalog maintenance detaches templates without deleting reward promises."""
from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from apps.achievements.criteria import _boss_quests_completed, _collection_quests_completed, _quest_completed
from apps.achievements.models import Badge, UserBadge
from apps.homework.services import HomeworkService
from apps.quests.goals import _occurrence, create_goal, ingest_activity, list_goals, lock_user, set_pin
from apps.quests.models import ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.rewards.models import CoinLedger
from apps.rpg.management.commands.cleanup_rpg_catalog import cleanup
from config.tests.factories import make_family


class CatalogRetirementTests(TestCase):
    def setUp(self):
        family = make_family("Catalog retirement", parents=[{"username": "retireparent"}],
                             children=[{"username": "retirechild"}])
        self.parent, self.child = family.parents[0], family.children[0]
        ChallengeEnrollment.objects.create(user=self.child, starts_at=timezone.now() - timedelta(days=1))
        self.definition = QuestDefinition.objects.create(
            name="Chore Champion", description="Retired catalog quest", is_system=True,
            quest_type="collection", target_value=2, duration_days=7, coin_reward=40,
            trigger_filter={"allowed_triggers": ["chore_complete"]}, is_repeatable=True,
        )
        list_goals(self.child)

    def test_documented_cleanup_keeps_saved_occurrence_and_removes_template(self):
        original = ChallengeOccurrence.objects.get()
        original_snapshot = original.snapshot
        result = cleanup()
        self.assertEqual(result["retired_quests"], 1)
        self.assertFalse(QuestDefinition.objects.filter(pk=self.definition.pk).exists())
        original.refresh_from_db()
        self.assertEqual(original.status, "active")
        self.assertEqual(original.snapshot["coins"], 40)
        self.assertEqual(original.snapshot, original_snapshot)
        self.assertEqual((original.goal.is_catalog, original.goal.catalog_definition_id), (True, None))
        self.assertEqual((original.snapshot["catalog_name"], original.snapshot["catalog_type"]),
                         ("Chore Champion", "collection"))
        self.assertEqual(ChallengeGoal.objects.count(), 1)

    def fact(self, identity, *, at=None, occurred_on=None):
        return ingest_activity(self.child, "chore_complete", identity, "chore_complete",
                               occurred_at=at or timezone.now(), occurred_on=occurred_on)

    def test_unpaid_retired_window_finishes_original_promise_and_badge(self):
        badge = Badge.objects.create(name="Retired quest complete", criteria_type="quest_completed",
                                     criteria_value={"quest_name": self.definition.name}, award_coins=False)
        original = ChallengeOccurrence.objects.get()
        self.fact("first")
        cleanup()
        # An identically named parent goal still cannot earn the named badge.
        parent = create_goal(self.parent, self.child, {
            "name": "Chore Champion", "trigger_type": "chore_complete", "metric": "count",
            "target": 1, "unit": "actions", "period": "this_week", "coin_reward": 7, "xp_reward": 0,
        })
        self.assertEqual((parent.status, parent.reward_receipt["coins"]), ("completed", 7))
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        self.fact("second")
        original.refresh_from_db()
        self.assertEqual((original.progress, original.status, original.reward_receipt["coins"]), (2, "completed", 40))
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        self.assertTrue(_quest_completed(self.child, {"quest_name": "Chore Champion"}))
        self.assertTrue(_quest_completed(self.child, {"quest_names": [], "count": 1}))
        self.assertFalse(_quest_completed(self.child, {"quest_names": [], "count": 2}))
        self.assertTrue(_collection_quests_completed(self.child, {"count": 1}))
        self.assertFalse(_collection_quests_completed(self.child, {"count": 2}))
        self.assertFalse(_boss_quests_completed(self.child, {"count": 1}))

    def test_paid_retired_history_and_pin_survive_without_new_cycles(self):
        original = ChallengeOccurrence.objects.get()
        set_pin(self.child, f"goal:{original.pk}")
        self.fact("first")
        self.fact("second")
        original.refresh_from_db()
        snapshot, receipt, awarded_at = original.snapshot, original.reward_receipt, original.awarded_at
        cleanup()
        with patch("django.utils.timezone.now", return_value=original.ends_at + timedelta(hours=1)):
            payload = list_goals(self.child)
            self.fact("next-period")
            list_goals(self.child)
        original.refresh_from_db()
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertEqual((original.snapshot, original.reward_receipt, original.awarded_at), (snapshot, receipt, awarded_at))
        self.assertEqual(payload["pin"], f"goal:{original.pk}")
        self.assertEqual(payload["results"][0]["reward_receipt"]["coins_awarded"], 40)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="adjustment").count(), 1)

    def test_retired_unpaid_goal_expires_without_new_recurrence_or_reward(self):
        original = ChallengeOccurrence.objects.get()
        self.fact("first")
        cleanup()
        with patch("django.utils.timezone.now", return_value=original.ends_at + timedelta(hours=1)):
            self.fact("too-late")
            payload = list_goals(self.child)
        original.refresh_from_db()
        self.assertEqual((original.progress, original.awarded_at), (1, None))
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertEqual(payload["results"][0]["status"], "expired")
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="adjustment").exists())

    def test_retired_catalog_keeps_homework_cap_and_display_policy(self):
        definition = QuestDefinition.objects.create(
            name="MCP-SmokeTest-Homework", description="A retired planning goal", is_system=True,
            quest_type="collection", target_value=2, duration_days=7, coin_reward=40,
            trigger_filter={"allowed_triggers": ["homework_created"]},
        )
        list_goals(self.child)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        due_date = timezone.localdate() + timedelta(days=7)
        HomeworkService.create_assignment(self.child, {"title": "First plan", "due_date": due_date})
        cleanup()
        HomeworkService.create_assignment(self.child, {"title": "Second plan", "due_date": due_date})
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (1, "active"))
        payload = next(row for row in list_goals(self.child)["results"] if row["id"] == f"goal:{occurrence.pk}")
        self.assertEqual(payload["what_counts"], "planned homework (first per day)")

    def test_retired_boss_identity_survives_definition_cleanup(self):
        definition = QuestDefinition.objects.create(
            name="MCP-SmokeTest-Boss", description="A retired boss", is_system=True,
            quest_type="boss", target_value=15, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        list_goals(self.child)
        cleanup()
        self.fact("boss-finish")
        self.assertTrue(_quest_completed(self.child, {"quest_name": definition.name}))
        self.assertTrue(_boss_quests_completed(self.child, {"count": 1}))
        self.assertFalse(_collection_quests_completed(self.child, {"count": 1}))

    def test_retired_catalog_still_uses_approval_timestamp_for_its_cutoff(self):
        zone = ZoneInfo(self.child.family.timezone)
        boundary = timezone.now().astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=boundary)
        definition = QuestDefinition.objects.create(
            name="MCP-SmokeTest-LateApproval", description="Approval after catalog cutoff", is_system=True,
            quest_type="collection", target_value=1, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        list_goals(self.child)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        cleanup()
        # The performed day belongs to parent calendar goals, while catalog
        # enrollment uses today's approval timestamp, even after retirement.
        self.fact("late-approval", occurred_on=boundary.date() - timedelta(days=2))
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (1, "completed"))

    def test_loaded_catalog_goal_cannot_open_cycle_after_cleanup_detaches_it(self):
        # The goal and definition can have been read before maintenance runs.
        loaded = ChallengeGoal.objects.select_related("catalog_definition").get()
        original = ChallengeOccurrence.objects.get()
        cleanup()
        lock_user(self.child)
        self.assertIsNone(_occurrence(loaded, original.ends_at + timedelta(hours=1)))
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
