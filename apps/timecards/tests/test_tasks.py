"""Tests for timecard Celery tasks — auto_clock_out, generate_weekly_timecards."""
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
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


@override_settings(TIME_ZONE="America/Phoenix")
class GenerateWeeklyTimecardsTests(_Fixture):
    def test_generates_timecard_for_completed_entries(self):
        # UTC has already reached Monday while Phoenix is still Sunday.
        # Work and task week selection must use the same local calendar.
        for now, expected_week_start in (
            (datetime(2026, 10, 12, 1, 43, tzinfo=datetime_timezone.utc), date(2026, 10, 5)),
            (datetime(2026, 10, 12, 19, 43, tzinfo=datetime_timezone.utc), date(2026, 10, 12)),
        ):
            with self.subTest(now=now), timezone.override("America/Phoenix"), patch("django.utils.timezone.now", return_value=now):
                local_now = timezone.localtime()
                monday = local_now - timedelta(days=local_now.weekday())
                TimeEntry.objects.create(
                    user=self.child, project=self.project, status="completed",
                    clock_in=monday.replace(hour=10, minute=0, second=0, microsecond=0),
                    clock_out=monday.replace(hour=12, minute=0, second=0, microsecond=0),
                )
                generate_weekly_timecards_task()
                self.assertTrue(Timecard.objects.filter(user=self.child, week_start=expected_week_start).exists())
                tc = Timecard.objects.get(user=self.child, week_start=expected_week_start)
                self.assertEqual(tc.week_start, expected_week_start)
                self.assertEqual(tc.week_end, expected_week_start + timedelta(days=6))
                self.assertEqual(tc.total_hours, Decimal("2.00"))

    def test_no_entries_no_timecard(self):
        generate_weekly_timecards_task()
        self.assertFalse(Timecard.objects.filter(user=self.child).exists())
