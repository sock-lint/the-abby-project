"""Tests for PaymentService — ledger writes, balance, breakdown, payouts."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import Project, User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")


class RecordEntryTests(_Fixture):
    def test_creates_ledger_row(self):
        entry = PaymentService.record_entry(
            self.child, Decimal("5.00"),
            PaymentLedger.EntryType.HOURLY,
            description="1h @ $5",
            created_by=self.parent,
        )
        self.assertEqual(entry.amount, Decimal("5.00"))
        self.assertEqual(entry.user, self.child)
        self.assertEqual(entry.created_by, self.parent)
        self.assertEqual(entry.entry_type, "hourly")

    def test_supports_all_entry_types(self):
        for et in PaymentLedger.EntryType.values:
            PaymentService.record_entry(
                self.child, Decimal("1.00"), et,
                description=f"test {et}",
            )
        # One row per entry type.
        self.assertEqual(
            PaymentLedger.objects.filter(user=self.child).count(),
            len(PaymentLedger.EntryType.values),
        )

    def test_negative_amounts_accepted(self):
        entry = PaymentService.record_entry(
            self.child, Decimal("-3.00"),
            PaymentLedger.EntryType.ADJUSTMENT, description="deduction",
        )
        self.assertEqual(entry.amount, Decimal("-3.00"))

    def test_project_and_timecard_optional(self):
        entry = PaymentService.record_entry(
            self.child, Decimal("1"), PaymentLedger.EntryType.HOURLY,
        )
        self.assertIsNone(entry.project)
        self.assertIsNone(entry.timecard)


class RecordPayoutTests(_Fixture):
    def test_payout_writes_negative_amount(self):
        entry = PaymentService.record_payout(self.child, Decimal("10"), self.parent)
        self.assertEqual(entry.amount, Decimal("-10"))
        self.assertEqual(entry.entry_type, "payout")
        self.assertEqual(entry.created_by, self.parent)

    def test_payout_normalizes_sign(self):
        """Payout should produce negative even if caller passes negative."""
        entry = PaymentService.record_payout(self.child, Decimal("-15"), self.parent)
        self.assertEqual(entry.amount, Decimal("-15"))


class BalanceTests(_Fixture):
    def test_empty_balance_is_zero(self):
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("0.00"))

    def test_balance_sums_ledger(self):
        PaymentService.record_entry(self.child, Decimal("10"), PaymentLedger.EntryType.HOURLY)
        PaymentService.record_entry(self.child, Decimal("5"), PaymentLedger.EntryType.CHORE_REWARD)
        PaymentService.record_payout(self.child, Decimal("3"), self.parent)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("12"))

    def test_balance_scoped_per_user(self):
        PaymentService.record_entry(self.child, Decimal("10"), PaymentLedger.EntryType.HOURLY)
        self.assertEqual(PaymentService.get_balance(self.parent), Decimal("0.00"))


class BreakdownTests(_Fixture):
    def test_breakdown_groups_by_type(self):
        PaymentService.record_entry(self.child, Decimal("10"), PaymentLedger.EntryType.HOURLY)
        PaymentService.record_entry(self.child, Decimal("5"), PaymentLedger.EntryType.HOURLY)
        PaymentService.record_entry(self.child, Decimal("3"), PaymentLedger.EntryType.CHORE_REWARD)

        breakdown = PaymentService.get_breakdown(self.child)
        self.assertEqual(breakdown["hourly"], Decimal("15"))
        self.assertEqual(breakdown["chore_reward"], Decimal("3"))
