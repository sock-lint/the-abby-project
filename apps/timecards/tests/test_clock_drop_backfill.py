"""The frozen clock-out eligibility history never replays hourly rewards."""
from datetime import date, datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings

from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, DropLog, UserInventory
from apps.timecards.models import ClockOutDropReceipt, TimeEntry
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ClockDropBackfillTests(TestCase):
    def test_freezes_only_eligible_completed_work_by_local_close_day_without_awards(self):
        family = make_family(
            "Clock backfill", parents=[{"username": "clock-history-parent"}],
            children=[{"username": "clock-history-child"}, {"username": "clock-history-small"}],
        )
        child, small = family.children
        project = Project.objects.create(
            title="Historical work", created_by=family.parents[0], assigned_to=child, status="active",
        )
        close = datetime(2026, 4, 16, 7, 5, tzinfo=timezone.utc)
        for minutes in (4, 6):
            TimeEntry.objects.create(
                user=child, project=project, clock_in=close - timedelta(minutes=minutes),
                clock_out=close, status="completed", notes="Original saved work",
            )
        TimeEntry.objects.create(
            user=small, project=project, clock_in=close - timedelta(minutes=9), clock_out=close, status="completed",
        )
        TimeEntry.objects.create(
            user=small, project=project, clock_in=close - timedelta(minutes=60), clock_out=close, status="voided",
        )
        homework = Project.objects.create(
            title="Historical study", created_by=family.parents[0], assigned_to=small,
            status="active", is_homework_plan=True,
        )
        TimeEntry.objects.create(
            user=small, project=homework, clock_in=close - timedelta(minutes=60), clock_out=close, status="completed",
        )
        CoinLedger.objects.create(user=child, amount=15, reason="hourly")
        before_entries = list(TimeEntry.objects.order_by("pk").values())
        before_profiles = list(CharacterProfile.objects.order_by("pk").values())
        before_ledgers = list(CoinLedger.objects.order_by("pk").values())
        backfill = import_module("apps.timecards.migrations.0005_backfill_clock_out_drop_receipts")
        editor = SimpleNamespace(connection=connection)
        backfill.preserve_completed_work_days(apps, editor)
        backfill.preserve_completed_work_days(apps, editor)
        receipt = ClockOutDropReceipt.objects.get()
        self.assertEqual((receipt.user_id, receipt.occurred_on, receipt.historical), (child.pk, date(2026, 4, 16), True))
        self.assertEqual(list(TimeEntry.objects.order_by("pk").values()), before_entries)
        self.assertEqual(list(CharacterProfile.objects.order_by("pk").values()), before_profiles)
        self.assertEqual(list(CoinLedger.objects.order_by("pk").values()), before_ledgers)
        self.assertFalse(DropLog.objects.exists())
        self.assertFalse(UserInventory.objects.exists())
