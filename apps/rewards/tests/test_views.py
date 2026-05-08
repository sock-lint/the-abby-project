"""Tests for rewards views — Reward CRUD, redemption, coins, exchange."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.notifications.models import Notification, NotificationType
from apps.payments.services import PaymentService
from apps.projects.models import User
from apps.rewards.models import (
    CoinLedger, ExchangeRequest, Reward, RewardRedemption, RewardWishlist,
)
from apps.rewards.services import CoinService, RewardService
from apps.rpg.models import ItemDefinition


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

    def test_parent_can_create_digital_reward(self):
        item = ItemDefinition.objects.create(
            name="Shop Tonic",
            icon="!",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "xp_boost"},
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/rewards/", {
            "name": "XP Tonic",
            "cost_coins": 25,
            "fulfillment_kind": Reward.FulfillmentKind.DIGITAL_ITEM,
            "item_definition": item.pk,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertEqual(resp.json()["fulfillment_kind"], Reward.FulfillmentKind.DIGITAL_ITEM)
        self.assertEqual(resp.json()["item_definition"], item.pk)

    def test_digital_reward_requires_item(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/rewards/", {
            "name": "Broken",
            "cost_coins": 25,
            "fulfillment_kind": Reward.FulfillmentKind.DIGITAL_ITEM,
        }, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("item_definition", resp.json())

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


class RewardOutOfStockAndWishlistTests(_Fixture):
    """Wishlist toggle + 409 OOS payload + restock fanout."""

    def setUp(self):
        super().setUp()
        # Two rewards in the same family — one out of stock, one as a peer.
        self.oos = Reward.objects.create(
            name="Sold-Out Sticker", cost_coins=20, stock=0, is_active=True,
        )
        self.peer = Reward.objects.create(
            name="Peer Sticker", cost_coins=22, stock=5, is_active=True,
        )
        # Make sure both are in the same family so the queryset includes them.
        self.peer.family = self.oos.family
        self.peer.save()
        CoinService.award_coins(self.child, 200, CoinLedger.Reason.HOURLY)

    def test_redeem_oos_returns_409_with_similar(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/rewards/{self.oos.pk}/redeem/")
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["code"], "out_of_stock")
        # At least one similar reward returned.
        self.assertGreaterEqual(len(body["similar"]), 1)
        peer_ids = {r["id"] for r in body["similar"]}
        self.assertIn(self.peer.pk, peer_ids)
        # The OOS reward itself is excluded from "similar".
        self.assertNotIn(self.oos.pk, peer_ids)

    def test_post_to_wishlist_creates_entry(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/rewards/{self.oos.pk}/wishlist/")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            RewardWishlist.objects.filter(user=self.child, reward=self.oos).exists()
        )

    def test_post_to_wishlist_is_idempotent(self):
        self.client.force_authenticate(self.child)
        self.client.post(f"/api/rewards/{self.oos.pk}/wishlist/")
        resp = self.client.post(f"/api/rewards/{self.oos.pk}/wishlist/")
        # Second POST returns 200 not 201 — the row already existed.
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            RewardWishlist.objects.filter(user=self.child, reward=self.oos).count(),
            1,
        )

    def test_delete_wishlist_removes_entry(self):
        RewardWishlist.objects.create(user=self.child, reward=self.oos)
        self.client.force_authenticate(self.child)
        resp = self.client.delete(f"/api/rewards/{self.oos.pk}/wishlist/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            RewardWishlist.objects.filter(user=self.child, reward=self.oos).exists()
        )

    def test_restock_notifies_wishlisted_users_and_clears(self):
        """When stock flips 0 → ≥1, notify every wishlist user once and
        wipe their wishlist rows so a future cycle doesn't re-spam."""
        RewardWishlist.objects.create(user=self.child, reward=self.oos)
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(
            f"/api/rewards/{self.oos.pk}/", {"stock": 5}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # Notification fired exactly once for the wishlist user.
        notifs = Notification.objects.filter(
            user=self.child,
            notification_type=NotificationType.REWARD_RESTOCKED,
        )
        self.assertEqual(notifs.count(), 1)
        # Wishlist row cleared so re-out-of-stock → re-restock doesn't re-fire.
        self.assertFalse(
            RewardWishlist.objects.filter(user=self.child, reward=self.oos).exists()
        )

    def test_no_restock_notification_when_stock_unchanged(self):
        """A PATCH that leaves stock at 0 must NOT fire a restock alert."""
        RewardWishlist.objects.create(user=self.child, reward=self.oos)
        self.client.force_authenticate(self.parent)
        # Edit name only — stock stays 0.
        self.client.patch(
            f"/api/rewards/{self.oos.pk}/", {"name": "Renamed"}, format="json",
        )
        notifs = Notification.objects.filter(
            user=self.child,
            notification_type=NotificationType.REWARD_RESTOCKED,
        )
        self.assertEqual(notifs.count(), 0)
        # Wishlist row left alone since no restock happened.
        self.assertTrue(
            RewardWishlist.objects.filter(user=self.child, reward=self.oos).exists()
        )

    def test_my_wishlist_lists_only_own(self):
        other_child = User.objects.create_user(
            username="c2", password="pw", role="child",
        )
        RewardWishlist.objects.create(user=self.child, reward=self.oos)
        RewardWishlist.objects.create(user=other_child, reward=self.peer)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/rewards/my-wishlist/")
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.json()]
        self.assertEqual(ids, [self.oos.pk])

    def test_serializer_exposes_on_my_wishlist(self):
        RewardWishlist.objects.create(user=self.child, reward=self.oos)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/rewards/")
        body = resp.json()
        # DRF list view may be paginated (results: [...]) or flat — handle both.
        items = body.get("results") if isinstance(body, dict) else body
        rewards = {r["id"]: r for r in items}
        self.assertTrue(rewards[self.oos.pk]["on_my_wishlist"])
        self.assertFalse(rewards[self.peer.pk]["on_my_wishlist"])


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
