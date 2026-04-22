"""Tests for savings goals — computed current_amount, service, completion pipeline."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.notifications.models import Notification, NotificationType
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import SavingsGoal, User
from apps.projects.savings_service import SavingsGoalService
from apps.projects.serializers import SavingsGoalSerializer
from apps.rewards.models import CoinLedger


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )

    def _add_balance(self, amount, *, entry_type="adjustment"):
        # Use a low-level create so we can seed balance without going
        # through PaymentService.record_entry (which triggers our own
        # completion hook — convenient in most tests, but some cases
        # need explicit control over when the hook fires).
        return PaymentLedger.objects.create(
            user=self.child,
            amount=Decimal(amount),
            entry_type=entry_type,
            description="test seed",
        )


class SerializerDerivesCurrentAmountTests(_Fixture):
    def test_current_amount_matches_live_balance(self):
        goal = SavingsGoal.objects.create(
            user=self.child, title="Bike", target_amount=Decimal("100.00"),
        )
        self._add_balance("40.00")

        data = SavingsGoalSerializer(goal).data
        self.assertEqual(Decimal(str(data["current_amount"])), Decimal("40.00"))
        self.assertEqual(data["percent_complete"], 40)

    def test_negative_balance_clamped_to_zero(self):
        goal = SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("50.00"),
        )
        self._add_balance("-10.00")
        data = SavingsGoalSerializer(goal).data
        self.assertEqual(Decimal(str(data["current_amount"])), Decimal("0"))
        self.assertEqual(data["percent_complete"], 0)


@override_settings(COINS_PER_SAVINGS_GOAL_DOLLAR=2)
class CheckAndCompleteTests(_Fixture):
    def test_no_op_when_balance_below_target(self):
        SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("50.00"),
        )
        self._add_balance("10.00")
        newly = SavingsGoalService.check_and_complete(self.child)
        self.assertEqual(newly, [])

    def test_completes_goal_when_balance_meets_target(self):
        goal = SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("25.00"),
        )
        self._add_balance("25.00")

        newly = SavingsGoalService.check_and_complete(self.child)

        self.assertEqual(len(newly), 1)
        self.assertEqual(newly[0].pk, goal.pk)
        goal.refresh_from_db()
        self.assertTrue(goal.is_completed)
        self.assertIsNotNone(goal.completed_at)

    def test_completion_awards_coins_target_times_rate(self):
        SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("50.00"),
        )
        self._add_balance("50.00")

        SavingsGoalService.check_and_complete(self.child)

        savings_entries = CoinLedger.objects.filter(
            user=self.child,
            reason=CoinLedger.Reason.ADJUSTMENT,
            description__startswith="Savings goal:",
        )
        self.assertEqual(savings_entries.count(), 1)
        # $50 * COINS_PER_SAVINGS_GOAL_DOLLAR=2 = 100 coins
        self.assertEqual(savings_entries.first().amount, 100)

    def test_completion_notifies_child_and_parents(self):
        SavingsGoal.objects.create(
            user=self.child, title="Bike", target_amount=Decimal("25.00"),
        )
        self._add_balance("25.00")

        SavingsGoalService.check_and_complete(self.child)

        child_notif = Notification.objects.filter(
            user=self.child,
            notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
        )
        parent_notif = Notification.objects.filter(
            user=self.parent,
            notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
        )
        self.assertEqual(child_notif.count(), 1)
        self.assertEqual(parent_notif.count(), 1)

    def test_idempotent_when_goal_already_completed(self):
        goal = SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("25.00"),
            is_completed=True, completed_at=timezone.now(),
        )
        self._add_balance("25.00")

        newly = SavingsGoalService.check_and_complete(self.child)
        self.assertEqual(newly, [])
        # No coin ledger entry for the savings goal.
        self.assertFalse(CoinLedger.objects.filter(
            user=self.child, description__startswith="Savings goal:",
        ).exists())

    def test_calling_twice_does_not_double_award(self):
        SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("25.00"),
        )
        self._add_balance("25.00")

        SavingsGoalService.check_and_complete(self.child)
        SavingsGoalService.check_and_complete(self.child)

        self.assertEqual(
            CoinLedger.objects.filter(
                user=self.child, description__startswith="Savings goal:",
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                user=self.child,
                notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
            ).count(),
            1,
        )


class PaymentServiceHookTests(_Fixture):
    def test_ledger_entry_that_crosses_target_auto_completes(self):
        goal = SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("30.00"),
        )

        # Crossing the target via PaymentService.record_entry should fire
        # the completion pipeline through the hook.
        PaymentService.record_entry(
            self.child, Decimal("30.00"),
            PaymentLedger.EntryType.ADJUSTMENT,
            description="seed", created_by=self.parent,
        )

        goal.refresh_from_db()
        self.assertTrue(goal.is_completed)

    def test_ledger_entry_below_target_leaves_pending(self):
        goal = SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("100.00"),
        )
        PaymentService.record_entry(
            self.child, Decimal("50.00"),
            PaymentLedger.EntryType.ADJUSTMENT,
            description="seed", created_by=self.parent,
        )

        goal.refresh_from_db()
        self.assertFalse(goal.is_completed)

    def test_hook_failure_does_not_break_ledger_write(self):
        SavingsGoal.objects.create(
            user=self.child, title="X", target_amount=Decimal("10.00"),
        )

        with patch(
            "apps.projects.savings_service.SavingsGoalService.check_and_complete",
            side_effect=RuntimeError("boom"),
        ):
            entry = PaymentService.record_entry(
                self.child, Decimal("10.00"),
                PaymentLedger.EntryType.ADJUSTMENT,
                description="seed", created_by=self.parent,
            )

        # Ledger row was written despite the downstream failure.
        self.assertIsNotNone(entry.pk)
        self.assertTrue(
            PaymentLedger.objects.filter(pk=entry.pk).exists()
        )


class SerializerLazyCompletionTests(_Fixture):
    def test_reading_a_goal_auto_completes_if_threshold_met(self):
        """The ``to_representation`` path runs completion detection too.

        Guards against the case where a parent lowers ``target_amount``
        to something the child has already saved past — no ledger write
        needed, but the goal should auto-complete on the next fetch.
        """
        # Seed balance without firing the payments hook (see _add_balance).
        self._add_balance("40.00")

        goal = SavingsGoal.objects.create(
            user=self.child, title="Headphones", target_amount=Decimal("30.00"),
        )
        self.assertFalse(goal.is_completed)

        SavingsGoalSerializer(goal).data

        goal.refresh_from_db()
        self.assertTrue(goal.is_completed)
