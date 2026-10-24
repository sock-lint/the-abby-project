"""A repeating goal's first cycle is its accepted window; later cycles are future offers."""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.quests.queries import active_system_definitions
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UnsavedRepeatWindowTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 1, 18, 0, tzinfo=ZoneInfo("UTC"))
        # date_joined ignores a patched clock, so pin it explicitly.
        self.child = make_family("Unsaved windows", parents=[{"username": "unsaved-parent"}], children=[
            {"username": "unsaved-child", "date_joined": self.now - timedelta(days=30)},
        ]).children[0]
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def definition(self, *, name="Weekly taps", repeat=True, coins=10):
        return QuestDefinition.objects.create(
            name=name, description="Two habit taps.", quest_type="collection", target_value=2,
            duration_days=7, is_system=True, is_repeatable=repeat, coin_reward=coins,
            trigger_filter={"allowed_triggers": ["habit_log"]},
        )

    def fact(self, key, at, trigger="habit_log"):
        with patch("django.utils.timezone.now", return_value=at):
            return ingest_activity(self.child, "unsaved-windows", key, trigger, occurred_at=at)

    def enroll_without_window(self, definition):
        # Ineligible planned homework enrolls the child without saving a window.
        self.fact("plan", self.now, trigger="homework_created")
        goal = ChallengeGoal.objects.get(user=self.child, catalog_definition=definition)
        self.assertFalse(goal.occurrences.exists())
        return goal

    def coins(self):
        return list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True))

    def test_unresolved_duplicate_cannot_open_a_later_cycle_by_activity_or_listing(self):
        original = self.definition()
        goal = self.enroll_without_window(original)
        self.definition()
        self.assertFalse(active_system_definitions().filter(pk=original.pk).exists())
        later = goal.starts_at + timedelta(days=21, hours=1)
        self.fact("return-1", later)
        self.fact("return-2", later + timedelta(minutes=5))
        with patch("django.utils.timezone.now", return_value=later + timedelta(minutes=10)):
            list_goals(self.child)
        self.assertFalse(ChallengeOccurrence.objects.filter(goal=goal).exists())
        self.assertEqual(self.coins(), [])

    def test_demoted_definition_cannot_open_a_later_cycle(self):
        original = self.definition(name="Demoted weekly")
        goal = self.enroll_without_window(original)
        QuestDefinition.objects.filter(pk=original.pk).update(is_system=False)
        later = goal.starts_at + timedelta(days=21, hours=1)
        self.fact("demoted-1", later)
        self.fact("demoted-2", later + timedelta(minutes=5))
        self.assertFalse(ChallengeOccurrence.objects.filter(goal=goal).exists())

    def test_one_time_goal_keeps_its_only_window_after_a_duplicate_appears(self):
        original = self.definition(name="Once", repeat=False)
        goal = self.enroll_without_window(original)
        self.definition(name="Once", repeat=False)
        self.fact("once-1", self.now + timedelta(hours=1))
        self.assertEqual(list(goal.occurrences.values_list("starts_at", flat=True)), [goal.starts_at])

    def test_later_unsaved_cycle_adopts_the_current_versioned_offer(self):
        original = self.definition(name="Old weekly", coins=40)
        goal = self.enroll_without_window(original)
        QuestDefinition.objects.filter(pk=original.pk).update(coin_reward=10, trigger_filter={
            "allowed_triggers": ["habit_log"], "reward_policy_version": 2, "distinct_active_days": True})
        later = goal.starts_at + timedelta(days=21, hours=1)
        self.fact("v2-1", later)
        self.fact("v2-2", later + timedelta(minutes=5))
        window = goal.occurrences.get()
        self.assertEqual((window.snapshot["coins"], window.snapshot["filter"].get("distinct_active_days")), (10, True))
        self.assertEqual(self.coins(), [])
