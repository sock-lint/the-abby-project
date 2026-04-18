"""Smoke tests verifying that real instrumentation sites write ActivityEvent rows.

These are end-to-end: they go through the real service, not mocks, and assert
the expected ``event_type`` slugs appear with the correct subject. The goal
is to catch regressions where an instrumented call path silently drops its
ActivityEvent emission.
"""
from decimal import Decimal

from django.test import TestCase

from apps.activity.models import ActivityEvent
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )

    def _types(self, **filters):
        return list(
            ActivityEvent.objects
                .filter(**filters)
                .values_list("event_type", flat=True)
                .order_by("id")
        )


class LedgerInstrumentationTests(_Fixture):
    def test_coin_service_emits_ledger_event(self):
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService

        CoinService.award_coins(
            self.child, 7, CoinLedger.Reason.ADJUSTMENT,
            description="manual", created_by=self.parent,
        )
        self.assertIn("ledger.coins.adjustment", self._types(subject=self.child))

    def test_payment_service_emits_ledger_event(self):
        from apps.payments.models import PaymentLedger
        from apps.payments.services import PaymentService

        PaymentService.record_entry(
            self.child, Decimal("3.25"), PaymentLedger.EntryType.ADJUSTMENT,
            description="manual", created_by=self.parent,
        )
        self.assertIn("ledger.money.adjustment", self._types(subject=self.child))

    def test_award_service_suppresses_inner_ledger_events(self):
        """AwardService.grant emits award.coins but NOT ledger.coins.* underneath."""
        from apps.achievements.services import AwardService
        from apps.rewards.models import CoinLedger

        AwardService.grant(
            self.child,
            coins=10,
            coin_reason=CoinLedger.Reason.HOURLY,
            coin_description="hourly",
            created_by=self.parent,
        )
        types = self._types(subject=self.child)
        self.assertIn("award.coins", types)
        self.assertNotIn("ledger.coins.hourly", types)


class HabitInstrumentationTests(_Fixture):
    def test_habit_tap_emits_event(self):
        from apps.habits.models import Habit
        from apps.habits.services import HabitService

        habit = Habit.objects.create(
            user=self.child, name="Read", habit_type="positive",
            created_by=self.parent,
        )
        HabitService.log_tap(self.child, habit, 1)
        self.assertIn("habit.tap", self._types(subject=self.child))
