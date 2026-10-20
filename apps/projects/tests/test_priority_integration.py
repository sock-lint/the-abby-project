"""End-to-end integration test for build_next_actions against real DB fixtures.

Unit coverage for individual scoring rules lives in
test_priority_unit.py — this file confirms the wiring works against real
Django models (queries, signals, etc.)."""
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.chores.models import Chore, ChoreCompletion
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.habits.models import Habit, HabitLog
from apps.projects.models import User
from apps.projects.priority import build_next_actions
from apps.rpg.models import CharacterProfile


class BuildNextActionsIntegrationTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        # CharacterProfile auto-created via signal — set streak for test.
        cp = CharacterProfile.objects.get(user=self.child)
        cp.login_streak = 5
        cp.save(update_fields=["login_streak"])

    def test_parent_receives_empty_list(self):
        self.assertEqual(build_next_actions(self.parent), [])

    def test_end_to_end_ordering(self):
        today = datetime.date(2026, 4, 16)  # Thursday

        # Overdue homework (2 days): score 120
        HomeworkAssignment.objects.create(
            title="Reading log", subject="reading", effort_level=3,
            due_date=datetime.date(2026, 4, 14),
            assigned_to=self.child, created_by=self.parent,
        )
        # Due tomorrow: score 60
        HomeworkAssignment.objects.create(
            title="Math workbook", subject="math", effort_level=3,
            due_date=datetime.date(2026, 4, 17),
            assigned_to=self.child, created_by=self.parent,
        )
        # Submitted-but-pending homework: should be filtered out
        submitted = HomeworkAssignment.objects.create(
            title="History essay", subject="social_studies", effort_level=3,
            due_date=datetime.date(2026, 4, 17),
            assigned_to=self.child, created_by=self.parent,
        )
        HomeworkSubmission.objects.create(
            assignment=submitted, user=self.child,
            timeliness=HomeworkSubmission.Timeliness.ON_TIME,
        )

        # Daily chore already done: filtered
        done_daily = Chore.objects.create(
            title="Dishes", recurrence="daily",
            reward_amount=Decimal("0.00"), coin_reward=0,
            assigned_to=self.child, created_by=self.parent,
        )
        ChoreCompletion.objects.create(
            chore=done_daily, user=self.child,
            completed_date=today,
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=Decimal("0.00"),
            coin_reward_snapshot=0,
        )

        # Weekly chore not done: Thursday → score 34
        Chore.objects.create(
            title="Clean Room", recurrence="weekly",
            reward_amount=Decimal("1.00"), coin_reward=2,
            assigned_to=self.child, created_by=self.parent,
        )

        # Untapped habit, streak=5, hour=19 → score 65
        Habit.objects.create(
            user=self.child, created_by=self.parent,
            name="Brush teeth", habit_type="positive",
            strength=3, max_taps_per_day=1, is_active=True,
        )

        actions = build_next_actions(self.child, target_date=today, hour=19)
        result = [(a.kind, a.title, a.score) for a in actions]

        self.assertEqual(result, [
            ("homework", "Reading log", 120),
            ("habit", "Brush teeth", 65),
            ("homework", "Math workbook", 60),
            ("chore", "Clean Room", 34),
        ])

    def test_rejected_homework_still_eligible(self):
        today = datetime.date(2026, 4, 16)
        hw = HomeworkAssignment.objects.create(
            title="Resubmit this", subject="math", effort_level=3,
            due_date=today,
            assigned_to=self.child, created_by=self.parent,
        )
        HomeworkSubmission.objects.create(
            assignment=hw, user=self.child,
            status=HomeworkSubmission.Status.REJECTED,
            timeliness=HomeworkSubmission.Timeliness.ON_TIME,
        )
        actions = build_next_actions(self.child, target_date=today, hour=12)
        titles = [a.title for a in actions]
        self.assertIn("Resubmit this", titles)

    def test_starter_progress_stays_in_today_until_second_positive_tap(self):
        CharacterProfile.objects.filter(user=self.child).update(login_streak=0)
        habit = Habit.objects.create(
            user=self.child, created_by=self.parent, name="Brush your teeth",
            starter_key="brush_teeth", habit_type="positive", max_taps_per_day=2,
        )
        other_child = User.objects.create_user(username="other", role="child")
        Habit.objects.create(
            user=other_child, created_by=self.parent, name="Other child's teeth",
            starter_key="brush_teeth", max_taps_per_day=2,
        )
        today = datetime.date(2026, 4, 16)
        now = timezone.make_aware(datetime.datetime(2026, 4, 16, 7))
        with patch("django.utils.timezone.now", return_value=now):
            def actions():
                return [a for a in build_next_actions(self.child, target_date=today, hour=7)
                        if a.kind == "habit"]

            self.assertEqual([a.title for a in actions()], ["Brush your teeth"])
            self.assertEqual(actions()[0].subtitle, "0/2 today · morning and bedtime")
            HabitLog.objects.create(habit=habit, user=self.child, direction=1)
            HabitLog.objects.create(habit=habit, user=self.child, direction=-1)
            self.assertEqual(actions()[0].subtitle, "1/2 today · morning and bedtime")
            HabitLog.objects.create(habit=habit, user=self.child, direction=1)
            self.assertEqual(actions(), [])

    def test_paused_or_unapproved_starters_are_not_recommended(self):
        habit = Habit.objects.create(
            user=self.child, created_by=self.parent, name="Brush your teeth",
            starter_key="brush_teeth", max_taps_per_day=2, pending_parent_review=True,
        )
        self.assertFalse(any(a.kind == "habit" for a in build_next_actions(self.child, hour=19)))
        habit.pending_parent_review = False
        habit.is_active = False
        habit.save(update_fields=["pending_parent_review", "is_active"])
        self.assertFalse(any(a.kind == "habit" for a in build_next_actions(self.child, hour=19)))
