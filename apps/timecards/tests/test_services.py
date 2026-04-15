"""Tests for ClockService, TimeEntryService, TimecardService."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.payments.models import PaymentLedger
from apps.projects.models import Project, User
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.services import ClockService, TimecardService, TimeEntryService


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(
            username="c", password="pw", role="child", hourly_rate=Decimal("5.00"),
        )
        self.project = Project.objects.create(
            title="Birdhouse", created_by=self.parent, assigned_to=self.child,
            status="active", difficulty=1,
        )


class ClockInTests(_Fixture):
    def _fake_noon(self):
        """Build a timezone-aware datetime safely inside quiet-hour-free window."""
        return timezone.make_aware(timezone.datetime(2026, 4, 15, 12, 0))

    @patch("apps.timecards.services.timezone.localtime")
    def test_clock_in_creates_active_entry(self, mock_local):
        mock_local.return_value = self._fake_noon()
        entry = ClockService.clock_in(self.child, self.project)
        self.assertEqual(entry.status, "active")
        self.assertEqual(entry.user, self.child)
        # Project flipped to in_progress.
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "in_progress")

    @patch("apps.timecards.services.timezone.localtime")
    def test_quiet_hours_blocked(self, mock_local):
        late = timezone.make_aware(timezone.datetime(2026, 4, 15, 23, 0))
        mock_local.return_value = late
        with self.assertRaisesRegex(ValueError, "quiet hours"):
            ClockService.clock_in(self.child, self.project)

    @patch("apps.timecards.services.timezone.localtime")
    def test_double_clock_in_blocked(self, mock_local):
        mock_local.return_value = self._fake_noon()
        ClockService.clock_in(self.child, self.project)
        with self.assertRaisesRegex(ValueError, "Already clocked in"):
            ClockService.clock_in(self.child, self.project)

    def test_unassigned_project_blocked(self):
        other = User.objects.create_user(username="o", password="pw", role="child")
        with self.assertRaisesRegex(ValueError, "not assigned"):
            ClockService.clock_in(other, self.project)


class ClockOutTests(_Fixture):
    @patch("apps.timecards.services.timezone.localtime")
    def test_clock_out_closes_entry_and_awards(self, mock_local):
        mock_local.return_value = timezone.make_aware(timezone.datetime(2026, 4, 15, 12, 0))
        ClockService.clock_in(self.child, self.project)
        entry = TimeEntry.objects.get(user=self.child, status="active")
        # Rewind clock_in so duration > 0.
        entry.clock_in = timezone.now() - timezone.timedelta(hours=2)
        entry.save()

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            closed = ClockService.clock_out(self.child)

        self.assertEqual(closed.status, "completed")
        self.assertGreater(closed.duration_minutes, 0)

    def test_clock_out_without_active_raises(self):
        with self.assertRaisesRegex(ValueError, "No active"):
            ClockService.clock_out(self.child)


class AutoClockOutTests(_Fixture):
    def test_auto_clocks_out_stale_entries(self):
        entry = TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now() - timezone.timedelta(hours=10),
            status="active",
        )
        count = ClockService.auto_clock_out()
        self.assertEqual(count, 1)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "completed")
        self.assertTrue(entry.auto_clocked_out)

    def test_fresh_entries_unaffected(self):
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        count = ClockService.auto_clock_out()
        self.assertEqual(count, 0)


class OneActiveEntryConstraintTests(_Fixture):
    def test_db_blocks_two_active(self):
        TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=timezone.now(), status="active",
        )
        with self.assertRaises(IntegrityError):
            TimeEntry.objects.create(
                user=self.child, project=self.project,
                clock_in=timezone.now(), status="active",
            )


class TimeEntryServiceTests(_Fixture):
    def _make_entry(self, day_offset_days, minutes=60):
        clock_in = timezone.now() - timezone.timedelta(days=day_offset_days)
        entry = TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=clock_in,
            clock_out=clock_in + timezone.timedelta(minutes=minutes),
            duration_minutes=minutes,
            status="completed",
        )
        return entry

    def test_current_streak(self):
        # Worked today, yesterday, and 2 days ago.
        self._make_entry(0)
        self._make_entry(1)
        self._make_entry(2)
        self.assertEqual(TimeEntryService.current_streak(self.child), 3)

    def test_streak_breaks_on_gap(self):
        self._make_entry(0)
        self._make_entry(3)
        self.assertEqual(TimeEntryService.current_streak(self.child), 1)

    def test_longest_streak_at_least(self):
        self._make_entry(0)
        self._make_entry(1)
        self.assertTrue(TimeEntryService.longest_streak_at_least(self.child, 2))
        self.assertFalse(TimeEntryService.longest_streak_at_least(self.child, 5))

    def test_no_entries_zero_streak(self):
        self.assertEqual(TimeEntryService.current_streak(self.child), 0)


class TimecardServiceTests(_Fixture):
    def _entry_in_week(self, week_start, offset_days, minutes):
        clock_in_day = timezone.make_aware(
            timezone.datetime.combine(
                week_start + timedelta(days=offset_days),
                timezone.datetime.min.time(),
            )
        ) + timezone.timedelta(hours=10)
        return TimeEntry.objects.create(
            user=self.child, project=self.project,
            clock_in=clock_in_day,
            clock_out=clock_in_day + timezone.timedelta(minutes=minutes),
            duration_minutes=minutes,
            status="completed",
        )

    def test_generate_creates_timecard_and_ledger(self):
        monday = date(2026, 4, 13)
        self._entry_in_week(monday, 0, 60)  # 1h
        self._entry_in_week(monday, 1, 120)  # 2h

        tc = TimecardService.generate_weekly_timecard(self.child, monday)
        self.assertIsNotNone(tc)
        self.assertEqual(tc.total_hours, Decimal("3.00"))
        self.assertEqual(tc.hourly_earnings, Decimal("15.00"))
        self.assertEqual(tc.status, "pending")
        # Ledger rows written for each entry.
        self.assertEqual(
            PaymentLedger.objects.filter(user=self.child, entry_type="hourly").count(),
            2,
        )

    def test_generate_returns_none_for_empty_week(self):
        monday = date(2026, 4, 13)
        self.assertIsNone(TimecardService.generate_weekly_timecard(self.child, monday))

    def test_approve_uses_approval_workflow_fields(self):
        monday = date(2026, 4, 13)
        self._entry_in_week(monday, 0, 60)
        tc = TimecardService.generate_weekly_timecard(self.child, monday)

        TimecardService.approve_timecard(tc, self.parent, notes="great work")

        tc.refresh_from_db()
        self.assertEqual(tc.status, "approved")
        self.assertEqual(tc.decided_by, self.parent)
        self.assertIsNotNone(tc.decided_at)
        self.assertEqual(tc.parent_notes, "great work")

    def test_mark_paid_records_negative_payout(self):
        monday = date(2026, 4, 13)
        self._entry_in_week(monday, 0, 60)
        tc = TimecardService.generate_weekly_timecard(self.child, monday)

        TimecardService.mark_paid(tc, self.parent, Decimal("5.00"))
        tc.refresh_from_db()
        self.assertEqual(tc.status, "paid")
        self.assertTrue(PaymentLedger.objects.filter(
            user=self.child, entry_type="payout", amount=Decimal("-5.00"),
        ).exists())
