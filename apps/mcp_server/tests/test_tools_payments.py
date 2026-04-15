"""Tests for payment MCP tools."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.mcp_server.schemas import (
    AdjustPaymentIn,
    GetPaymentBalanceIn,
    RecordPayoutIn,
)
from apps.mcp_server.tools import payments as payment_tools
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.accounts.models import User


class PaymentBalanceTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        PaymentService.record_entry(
            self.child, Decimal("25.00"), PaymentLedger.EntryType.HOURLY,
            description="week 1",
        )

    def test_child_sees_own_balance(self) -> None:
        with override_user(self.child):
            result = payment_tools.get_payment_balance(GetPaymentBalanceIn())
        self.assertEqual(Decimal(result["balance"]), Decimal("25.00"))

    def test_child_cannot_see_other_balance(self) -> None:
        other = User.objects.create_user(username="o", password="pw", role="child")
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            payment_tools.get_payment_balance(
                GetPaymentBalanceIn(user_id=other.id),
            )


class RecordPayoutTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        PaymentService.record_entry(
            self.child, Decimal("50.00"), PaymentLedger.EntryType.HOURLY,
        )

    def test_parent_payout_decreases_balance(self) -> None:
        with override_user(self.parent):
            payment_tools.record_payout(
                RecordPayoutIn(user_id=self.child.id, amount=Decimal("30.00")),
            )
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("20.00"))

    def test_child_cannot_payout(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            payment_tools.record_payout(
                RecordPayoutIn(user_id=self.child.id, amount=Decimal("5.00")),
            )

    def test_parent_adjust_adds_negative(self) -> None:
        with override_user(self.parent):
            payment_tools.adjust_payment(
                AdjustPaymentIn(
                    user_id=self.child.id,
                    amount=Decimal("-5.00"),
                    description="late fee",
                ),
            )
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("45.00"))
