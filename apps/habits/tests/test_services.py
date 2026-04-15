from datetime import date

from django.test import TestCase

from apps.habits.models import Habit, HabitLog
from apps.habits.services import HabitService
from apps.projects.models import User
from apps.rpg.models import CharacterProfile


class HabitServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="habitchild", password="testpass", role="child"
        )
        self.parent = User.objects.create_user(
            username="habitparent", password="testpass", role="parent"
        )
        # Ensure character profile exists
        CharacterProfile.objects.get_or_create(user=self.user)
        self.habit = Habit.objects.create(
            name="Read",
            habit_type="positive",
            user=self.user,
            created_by=self.parent,
            coin_reward=2,
            xp_reward=10,
        )

    def test_log_positive_tap(self):
        result = HabitService.log_tap(self.user, self.habit, direction=1)
        self.assertEqual(result["direction"], 1)
        self.assertEqual(result["coin_reward"], 2)
        self.assertEqual(result["xp_reward"], 10)
        self.assertEqual(result["new_strength"], 1)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 1)

    def test_log_negative_tap(self):
        habit = Habit.objects.create(
            name="Junk food",
            habit_type="negative",
            user=self.user,
            created_by=self.parent,
            coin_reward=2,
            xp_reward=10,
        )
        result = HabitService.log_tap(self.user, habit, direction=-1)
        self.assertEqual(result["direction"], -1)
        self.assertEqual(result["coin_reward"], 0)
        self.assertEqual(result["xp_reward"], 0)
        self.assertEqual(result["new_strength"], -1)

    def test_multiple_taps_same_day(self):
        both_habit = Habit.objects.create(
            name="Exercise",
            habit_type="both",
            user=self.user,
            created_by=self.parent,
        )
        HabitService.log_tap(self.user, both_habit, direction=1)
        HabitService.log_tap(self.user, both_habit, direction=1)
        both_habit.refresh_from_db()
        self.assertEqual(both_habit.strength, 2)
        self.assertEqual(HabitLog.objects.filter(habit=both_habit).count(), 2)

    def test_decay_strength(self):
        # Give the habit some strength without logging today
        self.habit.strength = 3
        self.habit.save(update_fields=["strength"])
        target = date(2026, 4, 13)
        count = HabitService.decay_all_habits(self.user, target_date=target)
        self.assertEqual(count, 1)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 2)

    def test_decay_does_not_affect_tapped_today(self):
        self.habit.strength = 3
        self.habit.save(update_fields=["strength"])
        # Tap today
        HabitService.log_tap(self.user, self.habit, direction=1)
        from django.utils import timezone

        count = HabitService.decay_all_habits(self.user, target_date=timezone.localdate())
        self.assertEqual(count, 0)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, 4)  # +1 from tap, no decay

    def test_invalid_direction_raises(self):
        with self.assertRaises(ValueError):
            HabitService.log_tap(self.user, self.habit, direction=2)

    def test_positive_habit_rejects_negative_tap(self):
        with self.assertRaises(ValueError):
            HabitService.log_tap(self.user, self.habit, direction=-1)

    def test_negative_habit_rejects_positive_tap(self):
        habit = Habit.objects.create(
            name="Swearing",
            habit_type="negative",
            user=self.user,
            created_by=self.parent,
        )
        with self.assertRaises(ValueError):
            HabitService.log_tap(self.user, habit, direction=1)
