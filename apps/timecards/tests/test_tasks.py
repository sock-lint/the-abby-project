"""Tests for timecard Celery tasks — auto_clock_out, generate_weekly_timecards."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import Project, User
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.tasks import auto_clock_out_task, generate_weekly_timecards_task


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.project = Project.objects.create(
            title="P", assigned_to=self.child, created_by=self.parent,
            status="in_progress",
        )


class AutoClockOutTests(_Fixture):
    def test_auto_clocks_out_stale_entries(self):
        entry = TimeEntry.objects.create(
            user=self.child, project=self.project, status="active",
            clock_in=timezone.now() - timedelta(hours=9),
        )
        auto_clock_out_task()
        entry.refresh_from_db()
        self.assertEqual(entry.status, "completed")
        self.assertTrue(entry.auto_clocked_out)
        self.assertIsNotNone(entry.clock_out)

    def test_does_not_clock_out_recent_entries(self):
        entry = TimeEntry.objects.create(
            user=self.child, project=self.project, status="active",
            clock_in=timezone.now() - timedelta(hours=1),
        )
        auto_clock_out_task()
        entry.refresh_from_db()
        self.assertEqual(entry.status, "active")


class GenerateWeeklyTimecardsTests(_Fixture):
    def test_generates_timecard_for_completed_entries(self):
        now = timezone.now()
        # Monday of current week.
        monday = now - timedelta(days=now.weekday())
        TimeEntry.objects.create(
            user=self.child, project=self.project, status="completed",
            clock_in=monday.replace(hour=10, minute=0),
            clock_out=monday.replace(hour=12, minute=0),
            duration_minutes=120,
        )
        generate_weekly_timecards_task()
        self.assertTrue(
            Timecard.objects.filter(user=self.child).exists()
        )
        tc = Timecard.objects.get(user=self.child)
        self.assertGreater(tc.total_hours, Decimal("0"))

    def test_no_entries_no_timecard(self):
        generate_weekly_timecards_task()
        self.assertFalse(Timecard.objects.filter(user=self.child).exists())
