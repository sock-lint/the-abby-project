"""Tests for payment MCP tools."""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    AdjustPaymentIn,
    GetPaymentBalanceIn,
    RecordPayoutIn,
)
from apps.mcp_server.tools import payments as payment_tools
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.accounts.models import User
from config.tests.factories import make_family


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
        family = make_family(
            "Payout family", parents=[{"username": "p"}],
            children=[{"username": "c"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        PaymentService.record_entry(
            self.child, Decimal("50.00"), PaymentLedger.EntryType.CHORE_REWARD,
        )

    def payout(self, **overrides):
        data = {
            "user_id": self.child.pk, "amount": Decimal("30.00"),
            "transferred_on": timezone.localdate(), "idempotency_key": "transfer-1",
        }
        data.update(overrides)
        return RecordPayoutIn(**data)

    def test_parent_payout_decreases_balance(self) -> None:
        with override_user(self.parent):
            payment_tools.record_payout(self.payout())
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("20.00"))

    def test_child_cannot_payout(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            payment_tools.record_payout(self.payout(amount=Decimal("5.00")))

    def test_retry_reuses_ledger_debit(self) -> None:
        with override_user(self.parent):
            first = payment_tools.record_payout(self.payout(description="Allowance"))
            retry = payment_tools.record_payout(self.payout(description="Allowance"))
        self.assertEqual(first["id"], retry["id"])
        self.assertEqual(PaymentLedger.objects.filter(entry_type="payout").count(), 1)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("20.00"))

    def test_changed_retry_is_validation_error_without_debit(self) -> None:
        with override_user(self.parent):
            payment_tools.record_payout(self.payout())
            with self.assertRaises(MCPValidationError):
                payment_tools.record_payout(self.payout(amount=Decimal("10.00")))
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("20.00"))

    def test_reference_reused_between_rest_and_mcp_is_same_payment(self) -> None:
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.post("/api/payments/greenlight/payout/", {
            "user_id": self.child.pk, "amount": "30.00",
            "transferred_on": timezone.localdate().isoformat(),
            "idempotency_key": "transfer-1", "reference": "greenlight-42",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        with override_user(self.parent):
            retry = payment_tools.record_payout(self.payout(reference="greenlight-42"))
        self.assertEqual(response.data["payout"]["id"], retry["id"])
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("20.00"))

    def test_future_transfer_and_unapproved_funds_rejected(self) -> None:
        with override_user(self.parent):
            with self.assertRaises(MCPValidationError):
                payment_tools.record_payout(self.payout(
                    transferred_on=timezone.localdate() + timedelta(days=1),
                ))
            PaymentService.record_entry(
                self.child, Decimal("25.00"), PaymentLedger.EntryType.HOURLY,
            )
            with self.assertRaises(MCPValidationError):
                payment_tools.record_payout(self.payout(amount=Decimal("60.00")))
        self.assertFalse(PaymentLedger.objects.filter(entry_type="payout").exists())

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
