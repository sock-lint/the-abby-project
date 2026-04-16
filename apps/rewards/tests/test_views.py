"""Tests for rewards views — Reward CRUD, redemption, coins, exchange."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.payments.services import PaymentService
from apps.projects.models import User
from apps.rewards.models import CoinLedger, ExchangeRequest, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()


# ── RewardViewSet ────────────────────────────────────────────────────────

class RewardViewSetTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.active = Reward.objects.create(
            name="Sticker", cost_coins=10, is_active=True,
        )
        self.inactive = Reward.objects.create(
            name="Hidden", cost_coins=10, is_active=False,
        )

    def test_parent_sees_all_rewards(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/rewards/")
        self.assertEqual(resp.status_code, 200)
        names = [r["name"] for r in resp.json()["results"]]
        self.assertIn("Sticker", names)
        self.assertIn("Hidden", names)

    def test_child_sees_only_active_rewards(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/rewards/")
        self.assertEqual(resp.status_code, 200)
        names = [r["name"] for r in resp.json()["results"]]
        self.assertIn("Sticker", names)
        self.assertNotIn("Hidden", names)

    def test_parent_can_create_reward(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/rewards/", {
            "name": "New reward", "cost_coins": 25,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))

    def test_child_cannot_create_reward(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/rewards/", {
            "name": "Hack", "cost_coins": 1,
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_redeem_action_success(self):
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.HOURLY)
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/rewards/{self.active.pk}/redeem/")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], "pending")

    def test_redeem_action_insufficient_coins(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/rewards/{self.active.pk}/redeem/")
        self.assertEqual(resp.status_code, 400)


# ── RewardRedemptionViewSet ──────────────────────────────────────────────

class RewardRedemptionViewSetTests(_Fixture):
    def setUp(self):
        super().setUp()
        CoinService.award_coins(self.child, 200, CoinLedger.Reason.HOURLY)
        self.reward = Reward.objects.create(
            name="Treat", cost_coins=30, is_active=True,
            requires_parent_approval=True,
        )
        self.redemption = RewardService.request_redemption(self.child, self.reward)

    def test_child_sees_own_redemptions(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/redemptions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 1)

    def test_parent_approve_action(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/redemptions/{self.redemption.pk}/approve/")
        self.assertEqual(resp.status_code, 200)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, RewardRedemption.Status.FULFILLED)

    def test_parent_reject_action(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/redemptions/{self.redemption.pk}/reject/")
        self.assertEqual(resp.status_code, 200)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, RewardRedemption.Status.DENIED)

    def test_child_cannot_approve(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/redemptions/{self.redemption.pk}/approve/")
        self.assertEqual(resp.status_code, 403)


# ── CoinBalanceView ──────────────────────────────────────────────────────

class CoinBalanceViewTests(_Fixture):
    def test_returns_balance_and_breakdown(self):
        CoinService.award_coins(self.child, 50, CoinLedger.Reason.HOURLY)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/coins/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["balance"], 50)
        self.assertIn("breakdown", data)
        self.assertIn("recent_transactions", data)


# ── CoinAdjustmentView ──────────────────────────────────────────────────

class CoinAdjustmentViewTests(_Fixture):
    def test_parent_can_adjust(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/coins/adjust/", {
            "user_id": self.child.id, "amount": 25,
            "description": "Bonus",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CoinService.get_balance(self.child), 25)

    def test_child_cannot_adjust(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/coins/adjust/", {
            "amount": 100, "description": "hack",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_zero_amount_rejected(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/coins/adjust/", {
            "user_id": self.child.id, "amount": 0,
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_negative_amount_checks_balance(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/coins/adjust/", {
            "user_id": self.child.id, "amount": -10,
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Insufficient", resp.json()["error"])


# ── ExchangeRequestView ─────────────────────────────────────────────────

class ExchangeRequestViewTests(_Fixture):
    def setUp(self):
        super().setUp()
        PaymentService.record_entry(self.child, Decimal("50.00"), "hourly")

    def test_create_exchange_request(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/coins/exchange/", {
            "dollar_amount": "5.00",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["dollar_amount"], "5.00")

    def test_missing_dollar_amount(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/coins/exchange/", {}, format="json")
        self.assertEqual(resp.status_code, 400)


# ── ExchangeRequestViewSet ──────────────────────────────────────────────

class ExchangeRequestViewSetTests(_Fixture):
    def setUp(self):
        super().setUp()
        PaymentService.record_entry(self.child, Decimal("50.00"), "hourly")
        self.exchange = ExchangeRequest.objects.create(
            user=self.child, dollar_amount=Decimal("10.00"),
            coin_amount=100, exchange_rate=10,
        )

    def test_list_exchanges(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/coins/exchange/list/")
        self.assertEqual(resp.status_code, 200)

    def test_parent_approve(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/coins/exchange/{self.exchange.pk}/approve/")
        self.assertEqual(resp.status_code, 200)
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, ExchangeRequest.Status.APPROVED)

    def test_parent_reject(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/coins/exchange/{self.exchange.pk}/reject/")
        self.assertEqual(resp.status_code, 200)
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, ExchangeRequest.Status.DENIED)

    def test_unauthenticated_cannot_approve(self):
        resp = self.client.post(f"/api/coins/exchange/{self.exchange.pk}/approve/")
        self.assertEqual(resp.status_code, 401)


# ── ExchangeRateView ────────────────────────────────────────────────────

class ExchangeRateViewTests(_Fixture):
    def test_returns_rate(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/coins/exchange/rate/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("coins_per_dollar", resp.json())
