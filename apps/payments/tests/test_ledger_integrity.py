"""Integrity tests for the PaymentLedger — mixed-type balance math,
coin-exchange debits, and the hourly/bounty/adjustment mix that the
app's real award paths produce.

These exercise behavior that the existing ``test_services.py`` touches
only individually; here we assert the composite math that the Payments
page and the exchange flow both depend on.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import User
from apps.rewards.models import CoinLedger


class MixedEntryTypeBalanceTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")

    def test_balance_sums_across_every_entry_type(self):
        """A realistic week: hourly + bounty + project bonus + milestone
        bonus + chore reward + materials reimbursement + adjustment +
        coin_exchange debit + payout. Balance must equal the signed sum."""
        rows = [
            (Decimal("20.00"), PaymentLedger.EntryType.HOURLY),
            (Decimal("15.00"), PaymentLedger.EntryType.BOUNTY_PAYOUT),
            (Decimal("5.00"), PaymentLedger.EntryType.PROJECT_BONUS),
            (Decimal("3.00"), PaymentLedger.EntryType.MILESTONE_BONUS),
            (Decimal("2.00"), PaymentLedger.EntryType.CHORE_REWARD),
            (Decimal("4.50"), PaymentLedger.EntryType.MATERIALS_REIMBURSEMENT),
            (Decimal("-1.50"), PaymentLedger.EntryType.ADJUSTMENT),
            (Decimal("-2.00"), PaymentLedger.EntryType.COIN_EXCHANGE),
        ]
        for amount, entry_type in rows:
            PaymentService.record_entry(self.child, amount, entry_type)
        PaymentService.record_payout(self.child, Decimal("10.00"), self.parent)

        expected = sum(r[0] for r in rows) + Decimal("-10.00")
        self.assertEqual(PaymentService.get_balance(self.child), expected)

    def test_coin_exchange_debit_path(self):
        """The money->coins exchange path writes a negative PaymentLedger
        row with entry_type=coin_exchange. Balance must go down by exactly
        the exchange amount, regardless of any matching CoinLedger side."""
        PaymentService.record_entry(
            self.child, Decimal("10.00"), PaymentLedger.EntryType.HOURLY,
        )
        PaymentService.record_entry(
            self.child, Decimal("-4.00"), PaymentLedger.EntryType.COIN_EXCHANGE,
            description="Exchanged $4 for 40 coins",
            created_by=self.parent,
        )
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("6.00"))
        # The paired CoinLedger write is a separate service's responsibility;
        # the payment side should stand on its own.
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 0)

    def test_breakdown_keeps_zero_categories_absent(self):
        """If no row of a given entry_type exists, it shouldn't appear in
        the breakdown — the Payments UI renders one tile per present key."""
        PaymentService.record_entry(
            self.child, Decimal("5.00"), PaymentLedger.EntryType.HOURLY,
        )
        breakdown = PaymentService.get_breakdown(self.child)
        self.assertIn(PaymentLedger.EntryType.HOURLY, breakdown)
        self.assertNotIn(PaymentLedger.EntryType.BOUNTY_PAYOUT, breakdown)

    def test_record_entry_never_mutates_existing_rows(self):
        """Append-only ledger: successive writes create distinct rows."""
        PaymentService.record_entry(
            self.child, Decimal("1.00"), PaymentLedger.EntryType.HOURLY,
        )
        PaymentService.record_entry(
            self.child, Decimal("1.00"), PaymentLedger.EntryType.HOURLY,
        )
        self.assertEqual(
            PaymentLedger.objects.filter(
                user=self.child, entry_type=PaymentLedger.EntryType.HOURLY,
            ).count(),
            2,
        )
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("2.00"))
