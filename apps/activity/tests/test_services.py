"""Tests for ActivityLogService emission helpers and scope semantics."""
from django.test import TestCase

from apps.activity.models import ActivityEvent
from apps.activity.services import (
    ActivityLogService,
    activity_scope,
    current_correlation_id,
    ledger_suppressed,
)
from apps.projects.models import User


class ActivityLogServiceTests(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )

    def test_record_writes_row_with_breakdown_and_extras(self):
        event = ActivityLogService.record(
            category="award",
            event_type="award.coins",
            summary="+10 coins",
            actor=self.parent,
            subject=self.child,
            coins_delta=10,
            breakdown=[
                {"label": "base", "value": 5, "op": "×"},
                {"label": "multiplier", "value": 2, "op": "="},
            ],
            extras={"reason": "test"},
        )
        self.assertEqual(event.category, "award")
        self.assertEqual(event.event_type, "award.coins")
        self.assertEqual(event.coins_delta, 10)
        self.assertEqual(len(event.context["breakdown"]), 2)
        self.assertEqual(event.context["breakdown"][0]["op"], "×")
        self.assertEqual(event.context["extras"], {"reason": "test"})

    def test_scope_shares_correlation_id(self):
        with activity_scope() as corr:
            ActivityLogService.record(
                category="system", event_type="x", summary="a",
                subject=self.child,
            )
            ActivityLogService.record(
                category="system", event_type="y", summary="b",
                subject=self.child,
            )
        rows = ActivityEvent.objects.order_by("id")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].correlation_id, corr)
        self.assertEqual(rows[1].correlation_id, corr)

    def test_outside_scope_correlation_is_null(self):
        ActivityLogService.record(
            category="system", event_type="x", summary="a",
            subject=self.child,
        )
        self.assertIsNone(ActivityEvent.objects.get().correlation_id)

    def test_ledger_suppression_flag_inherits_through_nested_scope(self):
        with activity_scope(suppress_inner_ledger=True):
            self.assertTrue(ledger_suppressed())
            with activity_scope():
                self.assertTrue(ledger_suppressed())

    def test_invalid_breakdown_op_raises(self):
        with self.assertRaises(ValueError):
            ActivityLogService.record(
                category="system",
                event_type="x",
                summary="bad",
                subject=self.child,
                breakdown=[{"label": "nope", "value": 1, "op": "!!"}],
            )

    def test_decimal_value_stringified_in_breakdown(self):
        from decimal import Decimal
        ActivityLogService.record(
            category="ledger",
            event_type="ledger.money.hourly",
            summary="pay",
            subject=self.child,
            breakdown=[{"label": "amt", "value": Decimal("3.50"), "op": "="}],
        )
        event = ActivityEvent.objects.get()
        self.assertEqual(event.context["breakdown"][0]["value"], "3.50")

    def test_current_correlation_id_none_outside_scope(self):
        self.assertIsNone(current_correlation_id())
