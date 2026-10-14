"""MCP can filter closed weeks without widening its existing account scope."""
from datetime import date

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied
from apps.mcp_server.schemas import ListTimecardsIn
from apps.mcp_server.tools.timecards import list_timecards
from apps.payments.models import PaymentLedger
from apps.timecards.models import Timecard
from config.tests.factories import make_family


class ClosedTimecardFilterTests(TestCase):
    def setUp(self):
        self.household = make_family(
            "Closed timecard family",
            parents=[{"username": "mcp-closed-parent"}],
            children=[{"username": "mcp-closed-child"}],
        )
        self.foreign = make_family(
            "Other closed timecard family",
            children=[{"username": "mcp-closed-outsider"}],
        )
        self.parent, self.child = self.household.parents[0], self.household.children[0]
        self.closed = Timecard.objects.create(
            user=self.child, week_start=date(2026, 10, 5),
            week_end=date(2026, 10, 11), status="closed",
        )
        Timecard.objects.create(
            user=self.child, week_start=date(2026, 9, 28),
            week_end=date(2026, 10, 4), status=Timecard.Status.APPROVED,
        )
        Timecard.objects.create(
            user=self.foreign.children[0], week_start=date(2026, 10, 5),
            week_end=date(2026, 10, 11), status="closed",
        )

    def test_parent_can_filter_own_childs_closed_weeks(self):
        params = ListTimecardsIn(user_id=self.child.pk, status="closed")
        with override_user(self.parent):
            result = list_timecards(params)
        self.assertEqual([card["id"] for card in result["timecards"]], [self.closed.pk])
        self.assertEqual(result["timecards"][0]["status"], "closed")
        self.assertEqual(result["timecards"][0]["total_earnings"], "0.00")
        self.assertFalse(PaymentLedger.objects.exists())

    def test_closed_filter_preserves_child_and_family_boundaries(self):
        with override_user(self.child):
            result = list_timecards(ListTimecardsIn(status="closed"))
            self.assertEqual([card["id"] for card in result["timecards"]], [self.closed.pk])
            with self.assertRaises(MCPPermissionDenied):
                list_timecards(ListTimecardsIn(user_id=self.foreign.children[0].pk, status="closed"))
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            list_timecards(ListTimecardsIn(user_id=self.foreign.children[0].pk, status="closed"))

