from django.test import TestCase

from apps.habits.models import Habit, HabitLog
from apps.projects.models import User


class HabitTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="testpass", role="parent")
        self.child = User.objects.create_user(username="child", password="testpass", role="child")

    def test_create_positive_habit(self):
        habit = Habit.objects.create(
            name="Read a book",
            user=self.child,
            created_by=self.parent,
        )
        self.assertEqual(habit.habit_type, Habit.HabitType.POSITIVE)
        self.assertEqual(habit.coin_reward, 1)
        self.assertEqual(habit.xp_reward, 5)
        self.assertEqual(habit.strength, 0)
        self.assertTrue(habit.is_active)
        self.assertEqual(str(habit), "Read a book")

    def test_create_habit_with_icon(self):
        habit = Habit.objects.create(
            name="Exercise",
            icon="💪",
            user=self.child,
            created_by=self.parent,
        )
        self.assertEqual(str(habit), "💪 Exercise")

    def test_create_habit_log(self):
        habit = Habit.objects.create(
            name="Study",
            user=self.child,
            created_by=self.parent,
        )
        log = HabitLog.objects.create(
            habit=habit,
            user=self.child,
            direction=1,
            streak_at_time=3,
        )
        self.assertEqual(log.direction, 1)
        self.assertEqual(log.streak_at_time, 3)
        self.assertEqual(log.habit, habit)

    def test_habit_type_choices(self):
        valid_values = {choice.value for choice in Habit.HabitType}
        self.assertEqual(valid_values, {"positive", "negative", "both"})
