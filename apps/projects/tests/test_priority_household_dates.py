"""Today uses the same household task dates as submission and review."""
from datetime import date, datetime, timezone
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore
from apps.chores.services import ChoreService
from apps.homework.models import HomeworkAssignment
from apps.habits.models import Habit, HabitLog
from apps.projects.priority import build_next_actions
from apps.rpg.models import CharacterProfile
from config.tests.factories import make_family


class PriorityHouseholdDateTests(TestCase):
    def setUp(self):
        household = make_family(
            "Tokyo priority household", parents=[{"username": "priority-parent"}],
            children=[{"username": "priority-child"}],
        )
        self.family = household.family
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        self.parent, self.child = household.parents[0], household.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def test_today_homework_urgency_matches_household_midnight(self):
        assignment = HomeworkAssignment.objects.create(
            title="Yesterday in Tokyo", assigned_to=self.child, created_by=self.parent,
            subject="math", due_date=date(2026, 10, 17),
        )
        at = datetime(2026, 10, 17, 15, 30, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data["next_actions"] if item["id"] == assignment.pk and item["kind"] == "homework")
        self.assertIn("1 day overdue", row["subtitle"])
        self.assertEqual(row["score"], 110)

    def test_today_does_not_offer_weekly_chore_already_submitted_on_household_monday(self):
        chore = Chore.objects.create(
            title="Monday watering", family=self.family, created_by=self.parent,
            assigned_to=self.child, recurrence="weekly",
        )
        at = datetime(2026, 10, 18, 15, 30, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            completion = ChoreService.submit_completion(self.child, chore)
            response = self.client.get("/api/dashboard/")
        self.assertEqual(completion.completed_date, date(2026, 10, 19))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(item["id"] == chore.pk and item["kind"] == "chore" for item in response.data["next_actions"]))

    def streak_habit(self):
        CharacterProfile.objects.filter(user=self.child).update(login_streak=5)
        return Habit.objects.create(
            user=self.child, created_by=self.parent, name="Read quietly",
            habit_type="positive", max_taps_per_day=1, strength=1,
        )

    def test_household_task_rollover_keeps_already_tapped_habit_on_its_accounting_day(self):
        habit = self.streak_habit()
        # Tokyo is Oct18, while the existing habit accounting day is Oct17.
        at = datetime(2026, 10, 18, 2, 30, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            HabitLog.objects.create(habit=habit, user=self.child, direction=1)
            actions = build_next_actions(self.child)
        self.assertFalse(any(item.kind == "habit" for item in actions))
        self.assertEqual(HabitLog.objects.filter(user=self.child).count(), 1)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).login_streak, 5)

    def test_household_evening_does_not_move_the_existing_streak_protection_hour(self):
        self.streak_habit()
        # Tokyo is 19:30; Phoenix's existing streak gate is still at 03:30.
        at = datetime(2026, 10, 17, 10, 30, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=at):
            actions = build_next_actions(self.child)
        self.assertFalse(any(item.kind == "habit" for item in actions))
