"""Tests for rewards.services — CoinService, RewardService, ExchangeService."""
from decimal import Decimal

from django.test import TestCase

from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import User
from apps.rewards.models import CoinLedger, ExchangeRequest, Reward, RewardRedemption
from apps.rewards.services import (
    CoinService,
    ExchangeService,
    InsufficientCoinsError,
    InsufficientFundsError,
    RewardService,
    RewardUnavailableError,
)


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")


# ── CoinService ──────────────────────────────────────────────────────────

class CoinServiceTests(_Fixture):
    def test_award_coins_creates_entry(self):
        entry = CoinService.award_coins(self.child, 50, CoinLedger.Reason.HOURLY)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount, 50)
        self.assertEqual(CoinService.get_balance(self.child), 50)

    def test_award_zero_returns_none(self):
        entry = CoinService.award_coins(self.child, 0, CoinLedger.Reason.HOURLY)
        self.assertIsNone(entry)

    def test_spend_coins_creates_negative_entry(self):
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.HOURLY)
        entry = CoinService.spend_coins(self.child, 30, CoinLedger.Reason.REDEMPTION)
        self.assertEqual(entry.amount, -30)
        self.assertEqual(CoinService.get_balance(self.child), 70)

    def test_spend_coins_insufficient_raises(self):
        CoinService.award_coins(self.child, 10, CoinLedger.Reason.HOURLY)
        with self.assertRaises(InsufficientCoinsError):
            CoinService.spend_coins(self.child, 50, CoinLedger.Reason.REDEMPTION)

    def test_spend_zero_returns_none(self):
        entry = CoinService.spend_coins(self.child, 0, CoinLedger.Reason.REDEMPTION)
        self.assertIsNone(entry)

    def test_get_breakdown(self):
        CoinService.award_coins(self.child, 50, CoinLedger.Reason.HOURLY)
        CoinService.award_coins(self.child, 20, CoinLedger.Reason.PROJECT_BONUS)
        breakdown = CoinService.get_breakdown(self.child)
        self.assertEqual(breakdown["hourly"], 50)
        self.assertEqual(breakdown["project_bonus"], 20)


# ── RewardService ────────────────────────────────────────────────────────

class RewardServiceTests(_Fixture):
    def setUp(self):
        super().setUp()
        CoinService.award_coins(self.child, 200, CoinLedger.Reason.HOURLY)
        self.reward = Reward.objects.create(
            name="Ice cream", cost_coins=50, is_active=True,
            requires_parent_approval=True, stock=3,
        )

    def test_request_redemption_happy_path(self):
        redemption = RewardService.request_redemption(self.child, self.reward)
        self.assertEqual(redemption.status, RewardRedemption.Status.PENDING)
        self.assertEqual(redemption.coin_cost_snapshot, 50)
        # Coins held immediately.
        self.assertEqual(CoinService.get_balance(self.child), 150)
        # Stock decremented.
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 2)

    def test_request_redemption_insufficient_coins(self):
        expensive = Reward.objects.create(
            name="Trip", cost_coins=999, is_active=True,
        )
        with self.assertRaises(InsufficientCoinsError):
            RewardService.request_redemption(self.child, expensive)

    def test_request_redemption_inactive_reward(self):
        self.reward.is_active = False
        self.reward.save()
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(self.child, self.reward)

    def test_request_redemption_out_of_stock(self):
        self.reward.stock = 0
        self.reward.save()
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(self.child, self.reward)

    def test_request_redemption_notifies_parents(self):
        RewardService.request_redemption(self.child, self.reward)
        self.assertTrue(
            Notification.objects.filter(
                notification_type="redemption_requested",
            ).exists()
        )

    def test_auto_fulfill_without_approval(self):
        no_approval = Reward.objects.create(
            name="Sticker", cost_coins=10, is_active=True,
            requires_parent_approval=False,
        )
        redemption = RewardService.request_redemption(self.child, no_approval)
        self.assertEqual(redemption.status, RewardRedemption.Status.FULFILLED)

    def test_approve_redemption(self):
        redemption = RewardService.request_redemption(self.child, self.reward)
        result = RewardService.approve(redemption, self.parent, notes="Enjoy!")
        self.assertEqual(result.status, RewardRedemption.Status.FULFILLED)
        result.refresh_from_db()
        self.assertEqual(result.decided_by, self.parent)

    def test_approve_already_approved_is_noop(self):
        redemption = RewardService.request_redemption(self.child, self.reward)
        RewardService.approve(redemption, self.parent)
        # Second approve should not crash.
        result = RewardService.approve(redemption, self.parent)
        self.assertEqual(result.status, RewardRedemption.Status.FULFILLED)

    def test_reject_refunds_coins(self):
        redemption = RewardService.request_redemption(self.child, self.reward)
        balance_after_hold = CoinService.get_balance(self.child)  # 150
        RewardService.reject(redemption, self.parent)
        redemption.refresh_from_db()
        self.assertEqual(redemption.status, RewardRedemption.Status.DENIED)
        # Coins refunded.
        self.assertEqual(CoinService.get_balance(self.child), balance_after_hold + 50)

    def test_reject_already_rejected_is_noop(self):
        redemption = RewardService.request_redemption(self.child, self.reward)
        RewardService.reject(redemption, self.parent)
        result = RewardService.reject(redemption, self.parent)
        self.assertEqual(result.status, RewardRedemption.Status.DENIED)


class LowStockSignalTests(_Fixture):
    """``request_redemption`` fires ``LOW_REWARD_STOCK`` to parents the first
    time stock drops into the 0/1 zone — added 2026-05 so parents can restock
    or retire a prize before an awkward "out of stock" conversation."""
    def setUp(self):
        super().setUp()
        from apps.notifications.models import NotificationType
        self.NotificationType = NotificationType
        CoinService.award_coins(self.child, 1000, CoinLedger.Reason.HOURLY)

    def _build_reward(self, *, stock):
        return Reward.objects.create(
            name=f"Prize-stock-{stock}",
            cost_coins=10,
            is_active=True,
            requires_parent_approval=True,
            stock=stock,
        )

    def test_redemption_dropping_to_one_left_fires_low_stock(self):
        reward = self._build_reward(stock=2)
        RewardService.request_redemption(self.child, reward)
        self.assertTrue(
            Notification.objects.filter(
                notification_type=self.NotificationType.LOW_REWARD_STOCK,
                user=self.parent,
            ).exists(),
        )

    def test_redemption_dropping_to_zero_fires_low_stock(self):
        reward = self._build_reward(stock=1)
        RewardService.request_redemption(self.child, reward)
        self.assertTrue(
            Notification.objects.filter(
                notification_type=self.NotificationType.LOW_REWARD_STOCK,
                user=self.parent,
            ).exists(),
        )

    def test_redemption_with_plenty_of_stock_does_not_fire(self):
        reward = self._build_reward(stock=5)
        RewardService.request_redemption(self.child, reward)
        self.assertFalse(
            Notification.objects.filter(
                notification_type=self.NotificationType.LOW_REWARD_STOCK,
            ).exists(),
        )

    def test_unlimited_stock_never_fires(self):
        # ``stock=None`` means unlimited — the low-stock branch must skip.
        reward = Reward.objects.create(
            name="Unlimited Prize", cost_coins=10, is_active=True,
            requires_parent_approval=True, stock=None,
        )
        RewardService.request_redemption(self.child, reward)
        self.assertFalse(
            Notification.objects.filter(
                notification_type=self.NotificationType.LOW_REWARD_STOCK,
            ).exists(),
        )


# ── ExchangeService ──────────────────────────────────────────────────────

class ExchangeServiceTests(_Fixture):
    def setUp(self):
        super().setUp()
        # Give child $50 balance.
        PaymentService.record_entry(
            self.child, Decimal("50.00"), "hourly",
        )

    def test_request_exchange_happy_path(self):
        exchange = ExchangeService.request_exchange(self.child, "10.00")
        self.assertEqual(exchange.status, ExchangeRequest.Status.PENDING)
        self.assertEqual(exchange.dollar_amount, Decimal("10.00"))
        self.assertEqual(exchange.coin_amount, 100)  # 10 × default rate of 10
        # Notification sent to parents.
        self.assertTrue(
            Notification.objects.filter(
                notification_type="exchange_requested",
            ).exists()
        )

    def test_request_exchange_minimum_amount(self):
        with self.assertRaises(ValueError):
            ExchangeService.request_exchange(self.child, "0.50")

    def test_request_exchange_insufficient_funds(self):
        with self.assertRaises(InsufficientFundsError):
            ExchangeService.request_exchange(self.child, "100.00")

    def test_request_exchange_invalid_amount(self):
        with self.assertRaises(ValueError):
            ExchangeService.request_exchange(self.child, "abc")

    def test_approve_exchange(self):
        exchange = ExchangeService.request_exchange(self.child, "10.00")
        result = ExchangeService.approve(exchange, self.parent)
        result.refresh_from_db()
        self.assertEqual(result.status, ExchangeRequest.Status.APPROVED)
        # Payment debited.
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("40.00"))
        # Coins credited.
        self.assertEqual(CoinService.get_balance(self.child), 100)
        # Notification sent.
        self.assertTrue(
            Notification.objects.filter(
                notification_type="exchange_approved",
            ).exists()
        )

    def test_approve_exchange_insufficient_balance_at_approval(self):
        exchange = ExchangeService.request_exchange(self.child, "10.00")
        # Drain balance after request (money not held at request time).
        PaymentService.record_entry(
            self.child, Decimal("-50.00"), "payout",
        )
        with self.assertRaises(InsufficientFundsError):
            ExchangeService.approve(exchange, self.parent)

    def test_reject_exchange_no_ledger_side_effects(self):
        exchange = ExchangeService.request_exchange(self.child, "10.00")
        result = ExchangeService.reject(exchange, self.parent, notes="Not now")
        result.refresh_from_db()
        self.assertEqual(result.status, ExchangeRequest.Status.DENIED)
        # Balance unchanged (money was never held).
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("50.00"))
        # Denial notification.
        self.assertTrue(
            Notification.objects.filter(
                notification_type="exchange_denied",
            ).exists()
        )

    def test_reject_already_rejected_is_noop(self):
        exchange = ExchangeService.request_exchange(self.child, "10.00")
        ExchangeService.reject(exchange, self.parent)
        result = ExchangeService.reject(exchange, self.parent)
        self.assertEqual(result.status, ExchangeRequest.Status.DENIED)
