"""Tests for config.services — finalize_decision and BaseLedgerService."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from config.services import finalize_decision


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")


class FinalizeDecisionTests(_Fixture):
    def _make_exchange_request(self):
        from apps.rewards.models import ExchangeRequest

        return ExchangeRequest.objects.create(
            user=self.child, dollar_amount=Decimal("5.00"),
            coin_amount=50, exchange_rate=10,
        )

    def test_stamps_status_decided_at_decided_by(self):
        exchange = self._make_exchange_request()
        finalize_decision(exchange, "approved", self.parent)
        exchange.refresh_from_db()
        self.assertEqual(exchange.status, "approved")
        self.assertIsNotNone(exchange.decided_at)
        self.assertEqual(exchange.decided_by, self.parent)

    def test_writes_parent_notes_when_field_exists(self):
        exchange = self._make_exchange_request()
        finalize_decision(exchange, "approved", self.parent, notes="Good job")
        exchange.refresh_from_db()
        self.assertEqual(exchange.parent_notes, "Good job")

    def test_skips_parent_notes_when_empty(self):
        exchange = self._make_exchange_request()
        finalize_decision(exchange, "approved", self.parent, notes="")
        exchange.refresh_from_db()
        self.assertEqual(exchange.parent_notes, "")

    def test_decided_by_can_be_none(self):
        """Auto-approvals (e.g. no-approval rewards) pass None as parent."""
        exchange = self._make_exchange_request()
        finalize_decision(exchange, "approved", None)
        exchange.refresh_from_db()
        self.assertIsNone(exchange.decided_by)


class BaseLedgerServicePaymentTests(_Fixture):
    def test_balance_zero_when_no_entries(self):
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("0.00"))

    def test_balance_sums_positive_and_negative(self):
        PaymentService.record_entry(self.child, Decimal("10.00"), "hourly")
        PaymentService.record_entry(self.child, Decimal("-3.00"), "payout")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("7.00"))

    def test_breakdown_groups_by_entry_type(self):
        PaymentService.record_entry(self.child, Decimal("10.00"), "hourly")
        PaymentService.record_entry(self.child, Decimal("5.00"), "project_bonus")
        breakdown = PaymentService.get_breakdown(self.child)
        self.assertEqual(breakdown["hourly"], Decimal("10.00"))
        self.assertEqual(breakdown["project_bonus"], Decimal("5.00"))

    def test_balance_per_user_isolation(self):
        child2 = User.objects.create_user(username="c2", password="pw", role="child")
        PaymentService.record_entry(self.child, Decimal("10.00"), "hourly")
        PaymentService.record_entry(child2, Decimal("20.00"), "hourly")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("10.00"))
        self.assertEqual(PaymentService.get_balance(child2), Decimal("20.00"))


class BaseLedgerServiceCoinTests(_Fixture):
    def test_coin_balance_zero_when_no_entries(self):
        self.assertEqual(CoinService.get_balance(self.child), 0)

    def test_coin_balance_sums_correctly(self):
        CoinService.award_coins(self.child, 50, CoinLedger.Reason.HOURLY)
        CoinService.award_coins(self.child, -10, CoinLedger.Reason.REDEMPTION)
        self.assertEqual(CoinService.get_balance(self.child), 40)
