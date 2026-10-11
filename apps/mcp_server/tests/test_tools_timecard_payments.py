"""MCP payments share the family authorization and retry-safe service."""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import MarkTimecardPaidIn, VoidTimeEntryIn
from apps.mcp_server.tools.timecards import mark_timecard_paid, void_time_entry
from apps.payments.models import PaymentLedger
from apps.projects.models import Project
from apps.timecards.models import Timecard, TimeEntry
from config.tests.factories import make_family


class MCPTimecardPaymentTests(TestCase):
    def setUp(self):
        self.alpha = make_family(
            "Alpha", parents=[{"username": "mcp-pay-parent-a"}], children=[{"username": "mcp-pay-child-a"}],
        )
        self.bravo = make_family("Bravo", parents=[{"username": "mcp-pay-parent-b"}])
        self.card = Timecard.objects.create(
            user=self.alpha.children[0], week_start=date(2026, 10, 5), week_end=date(2026, 10, 11),
            total_earnings=Decimal("5.00"), status=Timecard.Status.APPROVED,
        )
        self.params = MarkTimecardPaidIn(timecard_id=self.card.pk)

    def test_parent_cannot_pay_foreign_family_card(self):
        with override_user(self.bravo.parents[0]), self.assertRaises(MCPNotFoundError):
            mark_timecard_paid(self.params)
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Timecard.Status.APPROVED)
        self.assertFalse(PaymentLedger.objects.filter(timecard=self.card).exists())

    def test_child_cannot_pay_their_own_card(self):
        with override_user(self.alpha.children[0]), self.assertRaises(MCPPermissionDenied):
            mark_timecard_paid(self.params)
        self.assertFalse(PaymentLedger.objects.filter(timecard=self.card).exists())

    def test_own_parent_can_retry_without_duplicate_payout(self):
        PaymentLedger.objects.create(
            user=self.alpha.children[0], timecard=self.card, amount=Decimal("5.00"),
            entry_type=PaymentLedger.EntryType.HOURLY,
        )
        with override_user(self.alpha.parents[0]):
            for _ in range(2):
                result = mark_timecard_paid(self.params)
                self.assertEqual(result["status"], Timecard.Status.PAID)
        self.assertEqual(PaymentLedger.objects.get(
            timecard=self.card, entry_type=PaymentLedger.EntryType.PAYOUT,
        ).amount, Decimal("-5.00"))

    def test_unearned_card_payment_is_a_transport_validation_error(self):
        with override_user(self.alpha.parents[0]), self.assertRaisesRegex(MCPValidationError, "approved amount available"):
            mark_timecard_paid(self.params)
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Timecard.Status.APPROVED)
        self.assertFalse(PaymentLedger.objects.filter(timecard=self.card).exists())

    def test_service_permission_error_is_handled_for_transport(self):
        with override_user(self.alpha.parents[0]):
            with patch(
                "apps.mcp_server.tools.timecards.TimecardService.mark_paid",
                side_effect=PermissionDenied("Family access changed"),
            ):
                with self.assertRaisesRegex(MCPPermissionDenied, "Family access changed"):
                    mark_timecard_paid(self.params)

    def test_parent_cannot_void_foreign_family_entry(self):
        project = Project.objects.create(
            title="Work", created_by=self.alpha.parents[0], assigned_to=self.alpha.children[0],
        )
        entry = TimeEntry.objects.create(
            user=self.alpha.children[0], project=project, clock_in=timezone.now() - timedelta(hours=1),
            clock_out=timezone.now(), status=TimeEntry.Status.COMPLETED,
        )
        with override_user(self.bravo.parents[0]), self.assertRaises(MCPNotFoundError):
            void_time_entry(VoidTimeEntryIn(entry_id=entry.pk))
        entry.refresh_from_db()
        self.assertEqual(entry.status, TimeEntry.Status.COMPLETED)
        with override_user(self.alpha.parents[0]):
            result = void_time_entry(VoidTimeEntryIn(entry_id=entry.pk))
        self.assertEqual(result["status"], TimeEntry.Status.VOIDED)
