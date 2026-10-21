"""Untimed reading milestones retain one promise through late starts and gaps."""
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.quests.goals import ingest_activity, list_goals, set_pin
from apps.quests.milestone_eligibility import prerequisite_unavailable
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService
from config.tests.factories import make_family


READING = {"allowed_triggers": ["reading_logged"]}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UntimedReadingTests(TestCase):
    def setUp(self):
        family = make_family("Untimed reading", parents=[{"username": "untimed-parent"}],
                             children=[{"username": "untimed-reader"}, {"username": "untimed-sibling"}])
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        self.companion = QuestDefinition.objects.create(
            name="Reading Companion", description="Three Adventures, at your own pace.",
            quest_type="collection", target_value=3, duration_days=None,
            is_system=True, trigger_filter=READING, coin_reward=0, xp_reward=0,
        )
        self.now = timezone.now()

    def fact(self, key, day, *, trigger="reading_logged"):
        at = self.now + timedelta(days=day)
        with patch("django.utils.timezone.now", return_value=at):
            return ingest_activity(self.child, trigger, key, trigger, occurred_at=at, fresh_milestone=True)

    def occurrence(self):
        return ChallengeOccurrence.objects.get(goal__user=self.child, goal__catalog_definition=self.companion)

    def test_late_starter_completes_without_expiry_or_duplicate_reward(self):
        self.fact("enrollment", 0, trigger="habit_log")
        original = self.occurrence()
        self.assertIsNone(original.ends_at)
        self.assertIsNone(original.goal.ends_at)
        for day in [30, 50, 100]:
            self.fact(f"reading-{day}", day)
        finished = self.occurrence()
        self.assertEqual((finished.pk, finished.status, finished.progress), (original.pk, "completed", 3))
        receipt = finished.reward_receipt.copy()
        awarded_at = finished.awarded_at
        self.fact("reading-100", 100)
        self.fact("later", 200)
        finished.refresh_from_db()
        self.assertEqual((finished.progress, finished.reward_receipt, finished.awarded_at), (3, receipt, awarded_at))
        self.assertEqual(ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.companion).count(), 1)
        self.assertEqual(finished.goal.occurrences.count(), 1)

    def test_list_and_pin_keep_long_inactive_untimed_window_active(self):
        self.fact("enrollment", 0, trigger="habit_log")
        original = self.occurrence()
        at = self.now + timedelta(days=1000)
        with patch("django.utils.timezone.now", return_value=at):
            payload = list_goals(self.child)
            row = next(row for row in payload["results"] if row["id"] == f"goal:{original.pk}")
            self.assertEqual(row["status"], "active")
            self.assertIsNone(row["ends_at"])
            self.assertFalse(prerequisite_unavailable(self.child, self.companion.pk))
            set_pin(self.child, row["id"])
            self.assertEqual(list_goals(self.child)["pin"], row["id"])
        self.assertEqual(original.goal.occurrences.count(), 1)

    def test_retired_untimed_promise_can_finish_without_reopening(self):
        self.fact("first", 0)
        original = self.occurrence()
        self.companion.delete()
        self.fact("second", 100)
        self.fact("third", 200)
        original.refresh_from_db()
        self.assertEqual((original.status, original.progress), ("completed", 3))
        self.assertEqual(original.goal.occurrences.count(), 1)

    def test_existing_timed_goal_preserves_original_deadline_after_catalog_edit(self):
        self.companion.duration_days = 14
        self.companion.save()
        self.fact("first", 0)
        original = self.occurrence()
        deadline = original.ends_at
        self.companion.duration_days = None
        self.companion.save()
        self.fact("late-second", 30)
        original.refresh_from_db()
        self.assertEqual((original.progress, original.ends_at, original.goal.ends_at), (1, deadline, deadline))
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=30)):
            # The expired unpaid timed promise remains reachable through an
            # explicit retry, so it does not permanently lock its successors.
            self.assertFalse(prerequisite_unavailable(self.child, self.companion.pk))
            listed = next(row for row in list_goals(self.child)["results"] if row["id"] == f"goal:{original.pk}")
            self.assertEqual(listed["retry"], {"allowed": True, "reason": None, "latest_attempt_id": f"goal:{original.pk}"})

    def test_old_legacy_timed_run_keeps_its_accepted_deadline(self):
        old = Quest.objects.create(definition=self.companion, current_progress=2,
                                   start_date=self.now, end_date=self.now + timedelta(days=14),
                                   reward_items_snapshot=[])
        QuestParticipant.objects.create(quest=old, user=self.child)
        deadline = old.end_date
        result = QuestService.record_progress(self.child, "reading_logged", {})
        old.refresh_from_db()
        self.assertTrue(result["completed"])
        self.assertEqual((old.status, old.end_date), ("completed", deadline))

    def test_new_legacy_solo_and_coop_refuse_before_any_campaign_write(self):
        with self.assertRaisesMessage(ValueError, "progresses automatically"):
            QuestService.start_quest(self.child, self.companion.pk)
        with self.assertRaisesMessage(ValueError, "progresses automatically"):
            QuestService.start_co_op_quest(self.companion.pk, [self.child, self.sibling])
        self.assertFalse(Quest.objects.exists())

    def test_three_late_adventures_unlock_voyager_on_next_new_fact(self):
        category = SkillCategory.objects.create(name="Untimed Language Arts")
        skill = Skill.objects.create(name="Reading Comprehension", category=category)
        SkillProgress.objects.create(user=self.child, skill=skill, level=1, xp_points=100, unlocked=True)
        voyager = QuestDefinition.objects.create(
            name="Reading Voyager", description="Twenty Adventures in 84 days.",
            quest_type="collection", target_value=20, duration_days=84, is_system=True,
            trigger_filter=READING, prerequisite_quest=self.companion, required_skill=skill,
            required_skill_level=1,
        )
        self.fact("enrollment", 0, trigger="habit_log")
        for day in [30, 50, 100]:
            self.fact(f"reading-{day}", day)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child, catalog_definition=voyager).exists())
        self.fact("opening", 101)
        goal = ChallengeGoal.objects.get(user=self.child, catalog_definition=voyager)
        self.assertEqual((goal.starts_at, goal.ends_at),
                         (self.now + timedelta(days=101), self.now + timedelta(days=185)))
        self.assertEqual(goal.occurrences.get().progress, 1)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.sibling).exists())

    def test_model_restricts_untimed_to_one_time_global_reading_collections(self):
        self.companion.full_clean()
        for fields in [{"is_system": False}, {"created_by": self.parent}, {"is_repeatable": True},
                       {"quest_type": "boss"}, {"trigger_filter": {"allowed_triggers": ["habit_log"]}},
                       {"trigger_filter": {**READING, "on_time": True}}]:
            with self.subTest(fields=fields):
                for name, value in fields.items():
                    setattr(self.companion, name, value)
                with self.assertRaises(ValidationError):
                    self.companion.full_clean()
                self.companion.refresh_from_db()

    def test_feedback_does_not_classify_an_untimed_voyager_as_a_mature_window(self):
        from apps.quests.voyager_feedback import voyager_feedback
        self.companion.name = "Reading Voyager"
        self.companion.save()
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        self.fact("first", 0)
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=100)):
            report = voyager_feedback(self.parent)
        group = next(row for row in report["policy_groups"] if row["policy"] == "other_or_unknown")
        self.assertEqual((group["accepted_windows"], group["unknown_windows"], group["mature_denominator"]), (1, 1, 0))

    def completion_items(self):
        from apps.quests.models import QuestRewardItem
        from apps.rpg.models import DropTable, ItemDefinition
        promised = ItemDefinition.objects.create(
            slug="untimed-promised-snack", name="Promised snack", item_type="food",
        )
        discovered = ItemDefinition.objects.create(
            slug="untimed-completion-snack", name="Completion discovery", item_type="food",
        )
        reward = QuestRewardItem.objects.create(quest_definition=self.companion, item=promised, quantity=2)
        DropTable.objects.create(trigger_type="quest_complete", item=discovered, weight=1)
        return promised, discovered, reward

    def test_late_completion_keeps_promised_items_and_rolls_loot_once_after_replay_or_return(self):
        from apps.quests.models import ChallengeActivity
        from apps.rpg.models import DropLog, UserInventory
        promised, discovered, reward = self.completion_items()
        self.fact("first", 0)
        # The accepted promise stays at two items after an authored link edit.
        reward.quantity = 9
        reward.save(update_fields=["quantity"])
        self.fact("second", 30)
        self.fact("third", 100)
        completed = self.occurrence()
        self.assertEqual((completed.status, completed.progress), ("completed", 3))
        self.assertEqual([(row["item_id"], row["quantity"]) for row in completed.reward_receipt["items"]],
                         [(promised.pk, 2)])
        self.fact("third", 100)
        self.fact("after-long-return", 1000)
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1000)):
            list_goals(self.child)
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type="quest_complete", item=discovered).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=discovered).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=promised).quantity, 2)
        self.assertFalse(DropLog.objects.filter(user=self.sibling).exists())
        self.assertEqual(set(ChallengeActivity.objects.values_list("trigger_type", flat=True)), {"reading_logged"})
        self.assertEqual(completed.goal.occurrences.count(), 1)

    def test_late_completion_loot_failure_rolls_back_and_retry_pays_one_original_promise(self):
        from apps.quests.models import ChallengeActivity
        from apps.rpg.models import DropLog, UserInventory
        promised, discovered, _ = self.completion_items()
        self.fact("first", 0)
        self.fact("second", 30)
        with patch.object(DropLog.objects, "create", side_effect=RuntimeError("completion drop unavailable")):
            with self.assertRaisesMessage(RuntimeError, "completion drop unavailable"):
                self.fact("retry-third", 100)
        pending = self.occurrence()
        self.assertEqual((pending.status, pending.progress), ("active", 2))
        self.assertIsNone(pending.ends_at)
        self.assertIsNone(pending.completed_at)
        self.assertIsNone(pending.awarded_at)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(DropLog.objects.exists())
        self.assertIsNone(ChallengeActivity.objects.get(source_id="retry-third").processed_at)
        self.fact("retry-third", 100)
        self.fact("retry-third", 100)
        self.fact("later", 1000)
        pending.refresh_from_db()
        self.assertEqual((pending.status, pending.progress), ("completed", 3))
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type="quest_complete", item=discovered).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=discovered).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=promised).quantity, 2)
        self.assertEqual(pending.goal.occurrences.count(), 1)
