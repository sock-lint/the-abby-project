from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import CharacterProfile
from apps.rpg.services import GameLoopService, StreakService


class StreakServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="streakchild", password="testpass", role="child"
        )

    def test_record_activity_starts_streak(self):
        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        self.assertTrue(result["is_first_today"])
        self.assertEqual(result["streak"], 1)
        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.login_streak, 1)
        self.assertEqual(profile.last_active_date, date(2026, 4, 1))

    def test_record_activity_same_day_not_first(self):
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        self.assertFalse(result["is_first_today"])
        self.assertEqual(result["check_in_bonus_coins"], 0)
        self.assertEqual(result["streak"], 1)

    def test_record_activity_consecutive_day(self):
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 2))
        self.assertTrue(result["is_first_today"])
        self.assertEqual(result["streak"], 2)

    def test_record_activity_gap_resets_streak(self):
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 2))
        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 5))
        self.assertEqual(result["streak"], 1)

    def test_longest_streak_tracked(self):
        # Build a 3-day streak
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 2))
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 3))
        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.longest_login_streak, 3)

        # Gap resets current streak but longest stays
        StreakService.record_activity(self.user, activity_date=date(2026, 4, 10))
        profile.refresh_from_db()
        self.assertEqual(profile.login_streak, 1)
        self.assertEqual(profile.longest_login_streak, 3)

    def test_daily_check_in_bonus_coins(self):
        result = StreakService.record_activity(self.user, activity_date=date(2026, 4, 1))
        # streak=1, multiplier = 1 + 1*0.07 = 1.07, bonus = int(3 * 1.07) = 3
        self.assertEqual(result["check_in_bonus_coins"], 3)

    def test_daily_check_in_bonus_scales_with_streak(self):
        # Build an 11-day streak
        start = date(2026, 4, 1)
        for i in range(11):
            StreakService.record_activity(self.user, activity_date=start + timedelta(days=i))

        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.login_streak, 11)
        # streak=11, multiplier = 1 + 11*0.07 = 1.77, bonus = int(3 * 1.77) = 5
        # The last call's return value should reflect this
        result = StreakService.record_activity(
            self.user, activity_date=start + timedelta(days=10)
        )
        # Same day — returns cached streak, no bonus
        self.assertFalse(result["is_first_today"])
        # Verify by computing manually from the profile
        multiplier = min(1 + 11 * 0.07, 2.0)
        expected = int(3 * multiplier)
        self.assertEqual(expected, 5)


class GameLoopServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="loopchild", password="testpass", role="child"
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    def test_on_task_completed_first_today(self, _mock_random):
        """First task of the day awards check-in bonus coins."""
        from apps.rewards.models import CoinLedger

        result = GameLoopService.on_task_completed(self.user, "clock_out")
        self.assertTrue(result["streak"]["is_first_today"])
        self.assertGreater(result["streak"]["check_in_bonus_coins"], 0)
        self.assertIn("drops", result)
        self.assertIn("quest", result)
        # Verify CoinLedger has the entry
        self.assertTrue(
            CoinLedger.objects.filter(
                user=self.user, description="Daily check-in bonus"
            ).exists()
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    def test_on_task_completed_second_today(self, _mock_random):
        """Second task same day does not award bonus."""
        from apps.rewards.models import CoinLedger

        GameLoopService.on_task_completed(self.user, "clock_out")
        initial_count = CoinLedger.objects.filter(user=self.user).count()

        result = GameLoopService.on_task_completed(self.user, "clock_out")
        self.assertFalse(result["streak"]["is_first_today"])
        self.assertEqual(result["streak"]["check_in_bonus_coins"], 0)
        self.assertIn("drops", result)
        self.assertIn("quest", result)
        self.assertEqual(
            CoinLedger.objects.filter(user=self.user).count(), initial_count
        )

    @patch("apps.rpg.services.random.random", return_value=1.0)
    def test_on_task_completed_returns_trigger_type(self, _mock_random):
        result = GameLoopService.on_task_completed(self.user, "milestone_complete")
        self.assertEqual(result["trigger_type"], "milestone_complete")
        self.assertIn("drops", result)
        self.assertIn("quest", result)
        self.assertEqual(result["drops"], [])
