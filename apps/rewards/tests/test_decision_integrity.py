"""Approval receipts own their side effects even when callers hold stale rows."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.rewards.models import CoinLedger, ExchangeRequest, Reward, RewardRedemption
from apps.rewards.services import (
    CoinService, ExchangeService, InsufficientFundsError, RewardService,
)
from apps.rewards.views import ExchangeRequestViewSet, RewardRedemptionViewSet
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


class DecisionIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "parent"}], children=[{"username": "child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        CoinLedger.objects.create(user=self.child, amount=100, reason="adjustment")
        PaymentLedger.objects.create(user=self.child, amount=Decimal("10"), entry_type="hourly")
        self.item = ItemDefinition.objects.create(
            slug="review-frame", name="Frame", item_type="cosmetic_frame",
        )
        self.reward = Reward.objects.create(
            family=family.family, name="Frame", cost_coins=60, stock=3,
            fulfillment_kind="digital_item", item_definition=self.item,
        )

    def redeem(self):
        return RewardService.request_redemption(self.child, self.reward)

    def exchange(self, amount="2.00"):
        return ExchangeService.request_exchange(self.child, amount)

    def test_api_approve_replay_credits_one_item_and_returns_fulfilled(self):
        redemption = self.redeem()
        for _ in range(2):
            response = self.client.post(f"/api/redemptions/{redemption.pk}/approve/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], "fulfilled")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)
        self.assertEqual(CoinService.get_balance(self.child), 40)

    def test_stale_approve_cannot_duplicate_inventory(self):
        redemption = self.redeem()
        stale = RewardRedemption.objects.get(pk=redemption.pk)
        RewardService.approve(redemption, self.parent)
        result = RewardService.approve(stale, self.parent)
        self.assertEqual(result.status, "fulfilled")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)

    def test_stale_rejection_refunds_and_restores_stock_only_once(self):
        redemption = self.redeem()
        stale = RewardRedemption.objects.get(pk=redemption.pk)
        RewardService.reject(redemption, self.parent)
        result = RewardService.reject(stale, self.parent)
        self.reward.refresh_from_db()
        self.assertEqual(result.status, "denied")
        self.assertEqual(CoinService.get_balance(self.child), 100)
        self.assertEqual(self.reward.stock, 3)
        self.assertEqual(CoinLedger.objects.filter(redemption=redemption, reason="refund").count(), 1)

    def test_stale_reject_cannot_refund_fulfilled_redemption(self):
        redemption = self.redeem()
        stale = RewardRedemption.objects.get(pk=redemption.pk)
        RewardService.approve(redemption, self.parent)
        with patch.object(RewardRedemptionViewSet, "get_object", return_value=stale):
            response = self.client.post(f"/api/redemptions/{redemption.pk}/reject/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "fulfilled")
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 2)
        self.assertEqual(CoinService.get_balance(self.child), 40)
        self.assertFalse(CoinLedger.objects.filter(redemption=redemption, reason="refund").exists())

    def test_stale_approve_cannot_fulfill_denied_redemption(self):
        redemption = self.redeem()
        stale = RewardRedemption.objects.get(pk=redemption.pk)
        RewardService.reject(redemption, self.parent)
        result = RewardService.approve(stale, self.parent)
        self.assertEqual(result.status, "denied")
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.item).exists())

    def test_fulfillment_failure_rolls_back_status_and_inventory(self):
        redemption = self.redeem()
        credit = RewardService._maybe_credit_digital_item

        def credit_then_fail(row):
            credit(row)
            raise RuntimeError("fulfillment failed")

        with patch.object(RewardService, "_maybe_credit_digital_item", side_effect=credit_then_fail):
            with self.assertRaises(RuntimeError):
                RewardService.approve(redemption, self.parent)
        redemption.refresh_from_db()
        self.assertEqual(redemption.status, "pending")
        self.assertIsNone(redemption.decided_at)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.item).exists())
        RewardService.approve(redemption, self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)

    def test_rejection_failure_rolls_back_refund_and_stock(self):
        redemption = self.redeem()
        with patch("apps.rewards.services.finalize_decision", side_effect=RuntimeError("decision failed")):
            with self.assertRaises(RuntimeError):
                RewardService.reject(redemption, self.parent)
        redemption.refresh_from_db()
        self.reward.refresh_from_db()
        self.assertEqual(redemption.status, "pending")
        self.assertEqual(self.reward.stock, 2)
        self.assertEqual(CoinService.get_balance(self.child), 40)
        self.assertFalse(CoinLedger.objects.filter(redemption=redemption, reason="refund").exists())

    def test_api_exchange_replay_debits_once_and_returns_approved(self):
        exchange = self.exchange()
        stale = ExchangeRequest.objects.get(pk=exchange.pk)
        first = self.client.post(f"/api/coins/exchange/{exchange.pk}/approve/")
        with patch.object(ExchangeRequestViewSet, "get_object", return_value=stale):
            replay = self.client.post(f"/api/coins/exchange/{exchange.pk}/approve/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["status"], "approved")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("8"))
        self.assertEqual(CoinService.get_balance(self.child), 120)
        self.assertEqual(PaymentLedger.objects.filter(user=self.child, entry_type="coin_exchange").count(), 1)
        self.assertEqual(self.child.notifications.filter(notification_type="exchange_approved").count(), 1)

    def test_stale_reject_cannot_reverse_approved_exchange(self):
        exchange = self.exchange()
        stale = ExchangeRequest.objects.get(pk=exchange.pk)
        ExchangeService.approve(exchange, self.parent)
        result = ExchangeService.reject(stale, self.parent)
        self.assertEqual(result.status, "approved")
        self.assertFalse(self.child.notifications.filter(notification_type="exchange_denied").exists())
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("8"))

    def test_stale_approve_cannot_spend_denied_exchange(self):
        exchange = self.exchange()
        stale = ExchangeRequest.objects.get(pk=exchange.pk)
        ExchangeService.reject(exchange, self.parent)
        result = ExchangeService.approve(stale, self.parent)
        self.assertEqual(result.status, "denied")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("10"))
        self.assertEqual(CoinService.get_balance(self.child), 100)

    def test_repeated_stale_rejection_notifies_once(self):
        exchange = self.exchange()
        stale = ExchangeRequest.objects.get(pk=exchange.pk)
        ExchangeService.reject(exchange, self.parent)
        ExchangeService.reject(stale, self.parent)
        self.assertEqual(stale.status, "denied")
        self.assertEqual(self.child.notifications.filter(notification_type="exchange_denied").count(), 1)

    def test_exchange_failure_rolls_back_money_debit(self):
        exchange = self.exchange()
        with patch.object(CoinService, "award_coins", side_effect=RuntimeError("credit failed")):
            with self.assertRaises(RuntimeError):
                ExchangeService.approve(exchange, self.parent)
        exchange.refresh_from_db()
        self.assertEqual(exchange.status, "pending")
        self.assertIsNone(exchange.decided_at)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("10"))
        self.assertFalse(PaymentLedger.objects.filter(user=self.child, entry_type="coin_exchange").exists())
        ExchangeService.approve(exchange, self.parent)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("8"))

    def test_distinct_pending_exchanges_recheck_remaining_balance(self):
        first, second = self.exchange("7"), self.exchange("7")
        ExchangeService.approve(first, self.parent)
        with self.assertRaises(InsufficientFundsError):
            ExchangeService.approve(second, self.parent)
        second.refresh_from_db()
        self.assertEqual(second.status, "pending")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("3"))


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class DecisionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "parent"}], children=[{"username": "child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        PaymentLedger.objects.create(user=self.child, amount=Decimal("10"), entry_type="hourly")

    def test_distinct_exchange_approvals_cannot_overdraw_one_wallet(self):
        requests = [ExchangeService.request_exchange(self.child, "7") for _ in range(2)]
        barrier = Barrier(2)

        def approve(pk):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                exchange = ExchangeRequest.objects.get(pk=pk)
                barrier.wait(timeout=10)
                try:
                    ExchangeService.approve(exchange, self.parent)
                    return "approved"
                except InsufficientFundsError:
                    return "insufficient"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(approve, row.pk) for row in requests]
            outcomes = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(outcomes, ["approved", "insufficient"])
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("3"))
        self.assertEqual(CoinService.get_balance(self.child), 70)
        self.assertEqual(ExchangeRequest.objects.filter(status="approved").count(), 1)

    def test_competing_exchange_decisions_have_one_winner(self):
        exchange = ExchangeService.request_exchange(self.child, "2")
        barrier = Barrier(2)

        def decide(method):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                stale = ExchangeRequest.objects.get(pk=exchange.pk)
                barrier.wait(timeout=10)
                return method(stale, self.parent).status
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(decide, method) for method in (ExchangeService.approve, ExchangeService.reject)]
            outcomes = [future.result(timeout=15) for future in futures]
        exchange.refresh_from_db()
        self.assertEqual(outcomes, [exchange.status, exchange.status])
        expected_balance = Decimal("8") if exchange.status == "approved" else Decimal("10")
        self.assertEqual(PaymentService.get_balance(self.child), expected_balance)
        expected_coins = 20 if exchange.status == "approved" else 0
        self.assertEqual(CoinService.get_balance(self.child), expected_coins)
