from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.chores.models import Chore, ChoreCompletion
from apps.projects.models import User
from apps.rpg.models import CharacterProfile, Habit
from apps.rpg.tasks import decay_habit_strength_task, evaluate_perfect_day_task


class PerfectDayTaskTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="pdparent", password="testpass", role="parent"
        )
        self.child = User.objects.create_user(
            username="pdchild", password="testpass", role="child"
        )
        self.profile = CharacterProfile.objects.create(
            user=self.child,
            last_active_date=timezone.localdate(),
        )

    def test_perfect_day_with_all_chores_done(self):
        """Active user with all daily chores approved gets perfect day."""
        chore = Chore.objects.create(
            title="Make bed",
            recurrence=Chore.Recurrence.DAILY,
            assigned_to=self.child,
        )
        # Mark chore as completed today
        ChoreCompletion.objects.create(
            chore=chore,
            user=self.child,
            completed_date=timezone.localdate(),
            status=ChoreCompletion.Status.APPROVED,
        )

        result = evaluate_perfect_day_task()
        self.assertIn("1/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)

    def test_not_perfect_if_inactive(self):
        """User not active today gets no perfect day."""
        self.profile.last_active_date = date(2026, 1, 1)
        self.profile.save(update_fields=["last_active_date"])

        result = evaluate_perfect_day_task()
        self.assertIn("0/", result)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)


class DecayHabitTaskTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="decayparent", password="testpass", role="parent"
        )
        self.child = User.objects.create_user(
            username="decaychild", password="testpass", role="child"
        )

    def test_decay_reduces_untapped_habits(self):
        """Habit with strength=5 decays to 4."""
        habit = Habit.objects.create(
            name="Read",
            habit_type="positive",
            user=self.child,
            created_by=self.parent,
            strength=5,
        )

        result = decay_habit_strength_task()
        self.assertIn("1 habits decayed", result)

        habit.refresh_from_db()
        self.assertEqual(habit.strength, 4)
