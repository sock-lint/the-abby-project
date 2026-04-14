from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import CharacterProfile, Habit, HabitLog


class CharacterProfileTests(TestCase):
    def test_profile_auto_created_on_user_save(self):
        user = User.objects.create_user(username="testchild", password="testpass")
        self.assertTrue(CharacterProfile.objects.filter(user=user).exists())

    def test_profile_defaults(self):
        user = User.objects.create_user(username="testchild2", password="testpass")
        profile = user.character_profile
        self.assertEqual(profile.level, 0)
        self.assertEqual(profile.login_streak, 0)
        self.assertEqual(profile.longest_login_streak, 0)
        self.assertIsNone(profile.last_active_date)
        self.assertEqual(profile.perfect_days_count, 0)

    def test_str(self):
        user = User.objects.create_user(username="abby", password="testpass", display_name="Abby")
        profile = user.character_profile
        self.assertEqual(str(profile), "Abby (Level 0)")

    def test_str_no_display_name(self):
        user = User.objects.create_user(username="kiduser", password="testpass")
        profile = user.character_profile
        self.assertEqual(str(profile), "kiduser (Level 0)")


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
