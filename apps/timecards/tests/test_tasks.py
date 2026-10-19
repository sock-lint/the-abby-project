"""Tests for timecard Celery tasks and optional weekly email summaries."""
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from smtplib import SMTPAuthenticationError, SMTPServerDisconnected
from unittest.mock import patch

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.projects.models import Project, User
from apps.timecards.models import Timecard, TimeEntry
from apps.timecards.tasks import (
    auto_clock_out_task,
    generate_weekly_timecards_task,
    send_weekly_email_summaries,
)
from config.tests.factories import make_family


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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
class DisabledWeeklyEmailTests(SimpleTestCase):
    def test_disabled_email_skips_household_queries_and_delivery(self):
        # SimpleTestCase forbids database queries, including building summaries.
        with patch("django.core.mail.send_mail") as send_mail:
            with self.assertNoLogs("apps.timecards.tasks", level="DEBUG"):
                result = send_weekly_email_summaries()
        self.assertEqual(result, "Weekly emails disabled")
        send_mail.assert_not_called()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    TIME_ZONE="America/Phoenix",
)
class WeeklyEmailTests(TestCase):
    def setUp(self):
        self.families = []
        for name, hours in (("Alpha", 1), ("Beta", 2)):
            household = make_family(
                name,
                parents=[{"username": f"{name}-parent", "email": f"{name}-parent@example.test"}],
                children=[{"username": f"{name}-child", "email": f"{name}-child@example.test"}],
            )
            self.families.append(household)
            project = Project.objects.create(
                title=f"{name} project", assigned_to=household.children[0],
                created_by=household.parents[0], status="in_progress",
            )
            clock_in = datetime(2026, 10, 13, 17, tzinfo=datetime_timezone.utc)
            TimeEntry.objects.create(
                user=household.children[0], project=project, status="completed",
                clock_in=clock_in, clock_out=clock_in + timedelta(hours=hours),
            )

    def test_enabled_email_sends_each_family_only_its_own_summaries(self):
        with patch("apps.timecards.tasks.timezone.localdate", return_value=date(2026, 10, 18)):
            send_weekly_email_summaries()

        self.assertEqual(len(mail.outbox), 4)
        for household, other in zip(self.families, reversed(self.families)):
            for user in (household.children[0], household.parents[0]):
                message = next(message for message in mail.outbox if message.to == [user.email])
                self.assertIn(household.children[0].display_label, message.body)
                self.assertNotIn(other.children[0].display_label, message.body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.test",
    )
    def test_configured_smtp_failures_remain_monitored_and_do_not_retry(self):
        for failure_index, failure in (
            (0, SMTPAuthenticationError(535, b"synthetic authentication failure")),
            (2, SMTPServerDisconnected("synthetic connection failure")),
        ):
            deliveries = [1, 1, 1, 1]
            deliveries[failure_index] = failure
            with self.subTest(failure=type(failure).__name__):
                with patch("apps.timecards.tasks.timezone.localdate", return_value=date(2026, 10, 18)):
                    with patch("django.core.mail.send_mail", side_effect=deliveries) as send_mail:
                        with self.assertLogs("apps.timecards.tasks", level="ERROR") as captured:
                            send_weekly_email_summaries()
                self.assertEqual(send_mail.call_count, 4)
                self.assertEqual(len(captured.records), 1)
                self.assertIs(captured.records[0].exc_info[1], failure)
