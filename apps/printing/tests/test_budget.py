"""Pins the two-dimensional monthly print budget.

Invariants this file exists to protect:

1. The billing month is the **local** (``America/Phoenix``) month. A print
   that finishes at 9pm on the 31st is UTC-tomorrow; billing it to next
   month would hand the child a free spool every time a month ends.
2. Usage sums grams *and* minutes, and only for the period asked about.
3. ``None`` on a dimension means "no cap", and remaining is allowed to go
   negative — a forced approval or an overshooting print must show as an
   overage, not be silently clamped to zero.
4. ``is_active=False`` ledgers everything and enforces nothing.
5. ``check_affordable`` returns one human-readable string per blown
   dimension, so the API can say *which* limit was hit.
6. A failed print is debited proportionally to layers, floored at 10% (a
   print that dies on layer 1 still burned a purge line), capped at 100%,
   and floored again when the layer count is unknown — never the full
   estimate for a print we couldn't measure.
7. ``is_low`` warns at or below 20% remaining on either capped dimension.
8. Every ledger write leaves an audit trail and carries the right
   ``period_month``.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.activity.models import ActivityEvent
from apps.printing.budget import (
    LOW_BUDGET_FRACTION,
    PrintBudgetService,
    month_start,
)
from apps.printing.models import PrintBudgetLedger
from config.tests.factories import make_family

#: 2026-04-01 04:30 UTC is 2026-03-31 21:30 in Phoenix (UTC-7, no DST).
#: A naive UTC date reads April here; the local date reads March.
LATE_ON_THE_LAST_DAY_UTC = datetime.datetime(
    2026, 4, 1, 4, 30, tzinfo=datetime.timezone.utc,
)

MARCH = datetime.date(2026, 3, 1)
FEBRUARY = datetime.date(2026, 2, 1)


class _Fixture(TestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}, {"username": "sibling"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.sibling = self.household.children[1]

    def set_caps(self, *, grams=None, minutes=None, is_active=True):
        budget = PrintBudgetService.get_budget(self.child)
        budget.grams_per_month = grams
        budget.minutes_per_month = minutes
        budget.is_active = is_active
        budget.save()
        return budget

    def spend(self, *, grams="0", minutes=0, month=None, user=None):
        return PrintBudgetService.record(
            user or self.child,
            grams=Decimal(grams),
            minutes=minutes,
            reason=PrintBudgetLedger.Reason.PRINT_COMPLETED,
            month=month,
        )


class MonthStartTests(_Fixture):
    def test_month_start_uses_the_local_date_not_the_utc_date(self):
        # The guard: read naively in UTC this instant is already April.
        self.assertEqual(LATE_ON_THE_LAST_DAY_UTC.date(), datetime.date(2026, 4, 1))

        with mock.patch(
            "apps.printing.budget.timezone.now",
            return_value=LATE_ON_THE_LAST_DAY_UTC,
        ):
            self.assertEqual(month_start(), MARCH)

    def test_the_period_of_a_late_evening_debit_is_still_the_local_month(self):
        with mock.patch(
            "apps.printing.budget.timezone.now",
            return_value=LATE_ON_THE_LAST_DAY_UTC,
        ):
            entry = self.spend(grams="42.00", minutes=30)
            usage = PrintBudgetService.get_usage(self.child)

        self.assertEqual(entry.period_month, MARCH)
        self.assertEqual(usage["grams"], Decimal("42.00"))

    def test_an_explicit_day_is_collapsed_to_the_first_of_its_month(self):
        self.assertEqual(month_start(datetime.date(2026, 3, 17)), MARCH)


class UsageTests(_Fixture):
    def test_get_usage_sums_both_dimensions(self):
        self.spend(grams="40.00", minutes=30, month=MARCH)
        self.spend(grams="12.50", minutes=15, month=MARCH)
        usage = PrintBudgetService.get_usage(self.child, MARCH)
        self.assertEqual(usage["grams"], Decimal("52.50"))
        self.assertEqual(usage["minutes"], 45)

    def test_get_usage_ignores_other_months(self):
        self.spend(grams="500.00", minutes=900, month=FEBRUARY)
        self.spend(grams="10.00", minutes=5, month=MARCH)
        usage = PrintBudgetService.get_usage(self.child, MARCH)
        self.assertEqual(usage["grams"], Decimal("10.00"))
        self.assertEqual(usage["minutes"], 5)

    def test_get_usage_ignores_other_children(self):
        self.spend(grams="99.00", minutes=99, month=MARCH, user=self.sibling)
        usage = PrintBudgetService.get_usage(self.child, MARCH)
        self.assertEqual(usage["grams"], Decimal("0.00"))
        self.assertEqual(usage["minutes"], 0)

    def test_an_empty_month_reads_as_zero_not_none(self):
        usage = PrintBudgetService.get_usage(self.child, MARCH)
        self.assertEqual(usage["grams"], Decimal("0.00"))
        self.assertEqual(usage["minutes"], 0)


class RemainingTests(_Fixture):
    def test_remaining_is_none_for_an_uncapped_dimension(self):
        self.set_caps(grams=Decimal("500.00"), minutes=None)
        remaining = PrintBudgetService.get_remaining(self.child, MARCH)
        self.assertEqual(remaining["grams"], Decimal("500.00"))
        self.assertIsNone(remaining["minutes"])

    def test_remaining_subtracts_this_months_usage(self):
        self.set_caps(grams=Decimal("500.00"), minutes=600)
        self.spend(grams="120.00", minutes=180, month=MARCH)
        remaining = PrintBudgetService.get_remaining(self.child, MARCH)
        self.assertEqual(remaining["grams"], Decimal("380.00"))
        self.assertEqual(remaining["minutes"], 420)

    def test_remaining_goes_negative_when_overspent_and_is_not_clamped(self):
        self.set_caps(grams=Decimal("100.00"), minutes=60)
        self.spend(grams="150.00", minutes=200, month=MARCH)
        remaining = PrintBudgetService.get_remaining(self.child, MARCH)
        self.assertEqual(remaining["grams"], Decimal("-50.00"))
        self.assertEqual(remaining["minutes"], -140)

    def test_an_inactive_budget_reports_no_caps_at_all(self):
        self.set_caps(grams=Decimal("100.00"), minutes=60, is_active=False)
        remaining = PrintBudgetService.get_remaining(self.child, MARCH)
        self.assertIsNone(remaining["grams"])
        self.assertIsNone(remaining["minutes"])


class CheckAffordableTests(_Fixture):
    def test_an_estimate_inside_the_cap_has_no_problems(self):
        self.set_caps(grams=Decimal("500.00"), minutes=600)
        self.assertEqual(
            PrintBudgetService.check_affordable(
                self.child, grams=Decimal("100.00"), minutes=120, month=MARCH,
            ),
            [],
        )

    def test_one_problem_string_per_exceeded_dimension(self):
        self.set_caps(grams=Decimal("100.00"), minutes=60)
        problems = PrintBudgetService.check_affordable(
            self.child, grams=Decimal("250.00"), minutes=600, month=MARCH,
        )
        self.assertEqual(len(problems), 2)
        self.assertIn("filament", problems[0])
        self.assertIn("250.00g", problems[0])
        self.assertIn("print time", problems[1])
        self.assertIn("600 min", problems[1])

    def test_only_the_blown_dimension_is_reported(self):
        self.set_caps(grams=Decimal("100.00"), minutes=6000)
        problems = PrintBudgetService.check_affordable(
            self.child, grams=Decimal("250.00"), minutes=120, month=MARCH,
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("filament", problems[0])

    def test_an_uncapped_dimension_can_never_be_a_problem(self):
        self.set_caps(grams=None, minutes=None)
        self.assertEqual(
            PrintBudgetService.check_affordable(
                self.child, grams=Decimal("99999.00"), minutes=99999, month=MARCH,
            ),
            [],
        )

    def test_an_inactive_budget_enforces_nothing(self):
        self.set_caps(grams=Decimal("1.00"), minutes=1, is_active=False)
        self.assertEqual(
            PrintBudgetService.check_affordable(
                self.child, grams=Decimal("9999.00"), minutes=9999, month=MARCH,
            ),
            [],
        )

    def test_exactly_the_remaining_allowance_still_fits(self):
        self.set_caps(grams=Decimal("100.00"), minutes=60)
        self.assertEqual(
            PrintBudgetService.check_affordable(
                self.child, grams=Decimal("100.00"), minutes=60, month=MARCH,
            ),
            [],
        )


class GramsForFailedPrintTests(TestCase):
    """Pure arithmetic — no users, no rows."""

    def test_debit_is_proportional_to_layers_completed(self):
        self.assertEqual(
            PrintBudgetService.grams_for_failed_print(Decimal("100.00"), 50, 100),
            Decimal("50.00"),
        )

    def test_an_early_failure_is_floored_at_ten_percent(self):
        # Layer 1 of 100 is 1%, but a purge line and a skirt are real filament.
        self.assertEqual(
            PrintBudgetService.grams_for_failed_print(Decimal("100.00"), 1, 100),
            Decimal("10.00"),
        )

    def test_the_debit_is_capped_at_the_full_estimate(self):
        self.assertEqual(
            PrintBudgetService.grams_for_failed_print(Decimal("100.00"), 250, 100),
            Decimal("100.00"),
        )

    def test_an_unknown_layer_count_debits_the_floor_not_the_estimate(self):
        # total_layer_num == 0 means the report never told us. Charging the
        # full estimate for a print we couldn't measure is the wrong default.
        self.assertEqual(
            PrintBudgetService.grams_for_failed_print(Decimal("100.00"), 0, 0),
            Decimal("10.00"),
        )

    def test_no_estimate_means_no_debit(self):
        self.assertEqual(
            PrintBudgetService.grams_for_failed_print(None, 50, 100),
            Decimal("0.00"),
        )
        self.assertEqual(
            PrintBudgetService.grams_for_failed_print(Decimal("0.00"), 50, 100),
            Decimal("0.00"),
        )


class IsLowTests(_Fixture):
    def test_is_low_fires_exactly_at_the_threshold_on_grams(self):
        self.set_caps(grams=Decimal("100.00"))
        self.spend(grams="80.00", month=month_start())
        self.assertEqual(LOW_BUDGET_FRACTION, 0.2)
        self.assertTrue(PrintBudgetService.is_low(self.child))

    def test_is_low_is_false_just_above_the_threshold(self):
        self.set_caps(grams=Decimal("100.00"))
        self.spend(grams="79.00", month=month_start())
        self.assertFalse(PrintBudgetService.is_low(self.child))

    def test_is_low_fires_on_the_minutes_dimension_alone(self):
        self.set_caps(grams=None, minutes=600)
        self.spend(minutes=500, month=month_start())
        self.assertTrue(PrintBudgetService.is_low(self.child))

    def test_is_low_is_false_when_nothing_is_capped(self):
        self.set_caps(grams=None, minutes=None)
        self.spend(grams="99999.00", minutes=99999, month=month_start())
        self.assertFalse(PrintBudgetService.is_low(self.child))

    def test_is_low_is_false_for_an_inactive_budget(self):
        self.set_caps(grams=Decimal("100.00"), is_active=False)
        self.spend(grams="99.00", month=month_start())
        self.assertFalse(PrintBudgetService.is_low(self.child))


class RecordTests(_Fixture):
    def test_record_writes_a_ledger_row_with_the_local_period_month(self):
        with mock.patch(
            "apps.printing.budget.timezone.now",
            return_value=LATE_ON_THE_LAST_DAY_UTC,
        ):
            entry = PrintBudgetService.record(
                self.child,
                grams=Decimal("12.345"),
                minutes=17,
                reason=PrintBudgetLedger.Reason.PRINT_COMPLETED,
                note="finished",
            )
        self.assertEqual(entry.period_month, MARCH)
        self.assertEqual(entry.grams, Decimal("12.35"))  # quantised, half-up
        self.assertEqual(entry.minutes, 17)
        self.assertEqual(entry.note, "finished")

    def test_record_writes_an_activity_event(self):
        PrintBudgetService.record(
            self.child,
            grams=Decimal("40.00"),
            minutes=60,
            reason=PrintBudgetLedger.Reason.PRINT_COMPLETED,
            month=MARCH,
        )
        event = ActivityEvent.objects.get(event_type="print.budget.print_completed")
        self.assertEqual(event.category, "ledger")
        self.assertEqual(event.subject, self.child)
        labels = [step["label"] for step in event.context["breakdown"]]
        self.assertEqual(labels, ["Filament", "Print time"])

    def test_a_negative_adjustment_returns_budget(self):
        self.spend(grams="100.00", minutes=120, month=MARCH)
        PrintBudgetService.record(
            self.child,
            grams=Decimal("-40.00"),
            minutes=-60,
            reason=PrintBudgetLedger.Reason.REFUND,
            recorded_by=self.parent,
            month=MARCH,
        )
        usage = PrintBudgetService.get_usage(self.child, MARCH)
        self.assertEqual(usage["grams"], Decimal("60.00"))
        self.assertEqual(usage["minutes"], 60)

    def test_summary_reports_the_period_and_both_dimensions(self):
        self.set_caps(grams=Decimal("500.00"), minutes=None)
        self.spend(grams="100.00", minutes=90, month=month_start())
        summary = PrintBudgetService.summary(self.child)
        self.assertEqual(summary["period_month"], month_start().isoformat())
        self.assertEqual(summary["grams_used"], Decimal("100.00"))
        self.assertEqual(summary["minutes_used"], 90)
        self.assertEqual(summary["grams_remaining"], Decimal("400.00"))
        self.assertIsNone(summary["minutes_remaining"])
