"""API decimal serialization, retry safety, and atomic payment transitions."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework.test import APIClient

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.timecards.models import Timecard
from apps.timecards.services import TimecardService
from config.tests.factories import make_family


class TimecardPaymentIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            "Payment family", parents=[{"username": "pay-parent"}], children=[{"username": "pay-child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.timecard = Timecard.objects.create(
            user=self.child, week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
            total_earnings=Decimal("5.00"), status=Timecard.Status.APPROVED,
        )
        PaymentLedger.objects.create(
            user=self.child, timecard=self.timecard,
            amount=Decimal("5.00"), entry_type=PaymentLedger.EntryType.HOURLY,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.url = f"/api/timecards/{self.timecard.pk}/mark-paid/"

    def payouts(self):
        return PaymentLedger.objects.filter(timecard=self.timecard, entry_type=PaymentLedger.EntryType.PAYOUT)

    def test_api_decimal_string_round_trip_records_payout(self):
        card = self.client.get(f"/api/timecards/{self.timecard.pk}/").json()
        self.assertEqual(card["total_earnings"], "5.00")
        response = self.client.post(self.url, {"amount": card["total_earnings"]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], Timecard.Status.PAID)
        self.assertEqual(self.payouts().get().amount, Decimal("-5.00"))

    def test_omitted_amount_uses_timecard_total(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.payouts().get().amount, Decimal("-5.00"))

    def test_invalid_amounts_leave_status_and_ledger_unchanged(self):
        for amount in (None, "", "not-money", "NaN", "Infinity", "-Infinity", 0, -1, "1.001", "1000000.00"):
            with self.subTest(amount=amount):
                response = self.client.post(self.url, {"amount": amount}, format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.timecard.refresh_from_db()
                self.assertEqual(self.timecard.status, Timecard.Status.APPROVED)
                self.assertFalse(self.payouts().exists())

    def test_replayed_api_payment_creates_only_one_debit(self):
        for _ in range(2):
            response = self.client.post(self.url, {"amount": "5.00"}, format="json")
            self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(list(self.payouts().values_list("amount", flat=True)), [Decimal("-5.00")])

    def test_stale_service_instance_cannot_duplicate_payout_after_status_change(self):
        stale = Timecard.objects.get(pk=self.timecard.pk)
        TimecardService.mark_paid(self.timecard, self.parent, "5.00")
        Timecard.objects.filter(pk=self.timecard.pk).update(status=Timecard.Status.DISPUTED)
        TimecardService.mark_paid(stale, self.parent, "5.00")
        self.assertEqual(stale.status, Timecard.Status.PAID)
        self.assertEqual(self.payouts().count(), 1)

    def test_failed_ledger_write_rolls_back_the_entire_payment(self):
        record_entry = PaymentService.record_entry

        def write_then_fail(*args, **kwargs):
            record_entry(*args, **kwargs)
            raise RuntimeError("Injected payment failure")

        with patch("apps.timecards.services.PaymentService.record_entry", side_effect=write_then_fail):
            with self.assertRaisesRegex(RuntimeError, "Injected payment failure"):
                TimecardService.mark_paid(self.timecard, self.parent, "5.00")
        self.timecard.refresh_from_db()
        self.assertEqual(self.timecard.status, Timecard.Status.APPROVED)
        self.assertFalse(self.payouts().exists())

    def test_failed_status_write_rolls_back_the_ledger(self):
        with patch.object(Timecard, "save", side_effect=RuntimeError("Injected status failure")):
            with self.assertRaisesRegex(RuntimeError, "Injected status failure"):
                TimecardService.mark_paid(self.timecard, self.parent, "5.00")
        self.timecard.refresh_from_db()
        self.assertEqual(self.timecard.status, Timecard.Status.APPROVED)
        self.assertFalse(self.payouts().exists())

    def test_paid_card_without_payout_can_be_repaired(self):
        # Older failed string-amount requests persisted PAID before writing
        # their ledger row. A retry should complete that missing debit once.
        Timecard.objects.filter(pk=self.timecard.pk).update(status=Timecard.Status.PAID)
        for _ in range(2):
            response = self.client.post(self.url, {"amount": "5.00"}, format="json")
            self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.payouts().count(), 1)

    def test_service_rejects_child_and_foreign_parent_without_writes(self):
        other = make_family("Other", parents=[{"username": "other-pay-parent"}])
        for actor in (self.child, other.parents[0]):
            with self.subTest(role=actor.role, family=actor.family_id):
                with self.assertRaises(PermissionDenied):
                    TimecardService.mark_paid(self.timecard, actor, "5.00")
                self.timecard.refresh_from_db()
                self.assertEqual(self.timecard.status, Timecard.Status.APPROVED)
                self.assertFalse(self.payouts().exists())
