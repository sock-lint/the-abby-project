from datetime import date, datetime, timezone
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from apps.activity.models import ActivityEvent
from apps.rewards.models import CoinLedger
from apps.rpg.models import PerfectDayReceipt
from config.tests.factories import make_family


class PerfectDayReceiptBackfillTests(TestCase):
    def setUp(self):
        household = make_family(children=[{"username": "historical-perfect-child"}])
        self.family = household.family
        self.family.timezone = "Asia/Tokyo"
        self.family.save(update_fields=["timezone"])
        self.child = household.children[0]
        self.timestamp = datetime(2026, 10, 15, 15, 55, tzinfo=timezone.utc)
        self.migration = import_module("apps.rpg.migrations.0027_backfill_perfect_day_receipts")

    def event(self, **kwargs):
        return ActivityEvent.objects.create(**{
            "category": "system", "event_type": "system.perfect_day",
            "summary": "Perfect Day: +15 coins", "subject": self.child,
            "coins_delta": 15, "occurred_at": self.timestamp, **kwargs,
        })

    def backfill(self):
        self.migration.backfill_perfect_day_receipts(apps, SimpleNamespace(connection=connection))

    def test_legacy_timestamp_uses_actual_configured_day_despite_family_zone(self):
        self.event()
        self.backfill()
        receipt = PerfectDayReceipt.objects.get(user=self.child)
        self.assertEqual(receipt.day, date(2026, 10, 15))
        self.assertTrue(receipt.historical)

    def test_recorded_day_takes_precedence_over_timestamp_and_zone(self):
        self.event(context={"extras": {"day": "2026-09-30"}})
        self.backfill()
        self.assertEqual(PerfectDayReceipt.objects.get(user=self.child).day, date(2026, 9, 30))

    def test_duplicate_events_and_redelivery_never_rewrite_earned_values(self):
        self.event()
        self.event()
        profile = self.child.character_profile
        profile.perfect_days_count = 2
        profile.save(update_fields=["perfect_days_count"])
        CoinLedger.objects.create(user=self.child, amount=30, reason="adjustment")
        self.backfill()
        self.backfill()
        self.assertEqual(PerfectDayReceipt.objects.filter(user=self.child).count(), 1)
        profile.refresh_from_db()
        self.assertEqual(profile.perfect_days_count, 2)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [30])
        self.assertEqual(ActivityEvent.objects.filter(subject=self.child).count(), 2)

    def test_unrelated_or_deleted_subject_events_do_not_create_receipts(self):
        self.event(event_type="ledger.coins.adjustment")
        self.event(category="rpg")
        self.event(subject=None)
        self.backfill()
        self.assertFalse(PerfectDayReceipt.objects.exists())

    def test_existing_live_receipt_and_malformed_legacy_context_are_safe(self):
        receipt = PerfectDayReceipt.objects.create(user=self.child, day=date(2026, 10, 15))
        for context in [{"extras": {"day": "invalid"}}, {"extras": []}, []]:
            self.event(context=context)
        self.backfill()
        receipt.refresh_from_db()
        self.assertFalse(receipt.historical)
        self.assertEqual(PerfectDayReceipt.objects.count(), 1)
