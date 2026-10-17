"""Saved shop promises and finite stock survive stale clients and offer edits."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService, RewardUnavailableError
from apps.rewards.views import RewardViewSet
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


class ShopFixture:
    def setUp(self):
        family = make_family(
            "Shop integrity", parents=[{"username": "shop-parent"}],
            children=[{"username": "shop-a"}, {"username": "shop-b"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        self.item = ItemDefinition.objects.create(
            slug="promised-frame", name="Promised frame", item_type="cosmetic_frame",
        )
        self.replacement = ItemDefinition.objects.create(
            slug="replacement-title", name="Replacement title", item_type="cosmetic_title",
        )
        self.reward = Reward.objects.create(
            family=family.family, name="Frame prize", cost_coins=60, stock=1,
            fulfillment_kind="both", item_definition=self.item,
        )
        for child in family.children:
            CoinLedger.objects.create(user=child, amount=100, reason="adjustment")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ShopIntegrityTests(ShopFixture, TestCase):
    def test_redemption_api_projects_saved_promise_without_changing_current_offer(self):
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(
            cost_coins=80, fulfillment_kind="real_world", item_definition=self.replacement,
        )
        client = APIClient()
        client.force_authenticate(self.child)
        response = client.get(f"/api/redemptions/{pending.pk}/")
        self.assertEqual(response.status_code, 200)
        saved = response.data["reward"]
        self.assertEqual(saved["fulfillment_kind"], "both")
        self.assertEqual(saved["item_definition"], self.item.pk)
        self.assertEqual(saved["item_definition_detail"]["id"], self.item.pk)
        self.assertEqual(saved["item_definition_detail"]["name"], self.item.name)
        self.assertEqual(saved["cost_coins"], 60)
        offer = client.get(f"/api/rewards/{self.reward.pk}/").data
        self.assertEqual(offer["fulfillment_kind"], "real_world")
        self.assertEqual(offer["item_definition"], self.replacement.pk)
        self.assertEqual(offer["cost_coins"], 80)

    def test_pending_item_is_not_replaced_by_offer_edit(self):
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(item_definition=self.replacement)
        pending = RewardRedemption.objects.get(pk=pending.pk)
        RewardService.approve(pending, self.parent)
        RewardService.approve(pending, self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.replacement).exists())
        self.assertEqual(CoinService.get_balance(self.child), 40)

    def test_pending_digital_delivery_survives_retirement_and_kind_change(self):
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(
            fulfillment_kind="real_world", item_definition=None, is_active=False,
        )
        RewardService.approve(RewardRedemption.objects.get(pk=pending.pk), self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)

    def test_real_world_promise_does_not_gain_later_digital_delivery(self):
        self.reward.fulfillment_kind = "real_world"
        self.reward.save(update_fields=["fulfillment_kind"])
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(fulfillment_kind="digital_item")
        RewardService.approve(RewardRedemption.objects.get(pk=pending.pk), self.parent)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_original_item_is_protected_after_offer_replaces_it(self):
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(item_definition=self.replacement)
        with self.assertRaises(ProtectedError):
            self.item.delete()
        with self.assertRaises(ProtectedError):
            self.reward.delete()
        self.assertTrue(RewardRedemption.objects.filter(pk=pending.pk, status="pending").exists())

    def test_failure_after_inventory_write_rolls_back_and_retry_keeps_original_item(self):
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(item_definition=self.replacement)
        credit = RewardService._maybe_credit_digital_item

        def fail_after_credit(row):
            credit(row)
            raise RuntimeError("synthetic fulfillment failure")

        with patch.object(RewardService, "_maybe_credit_digital_item", side_effect=fail_after_credit):
            with self.assertRaises(RuntimeError):
                RewardService.approve(pending, self.parent)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "pending")
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        RewardService.approve(pending, self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.replacement).exists())

    def test_stale_offer_cannot_sell_last_item_twice(self):
        stale = Reward.objects.get(pk=self.reward.pk)
        RewardService.request_redemption(self.child, self.reward)
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(self.sibling, stale)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 0)
        self.assertEqual(CoinService.get_balance(self.sibling), 100)
        self.assertEqual(RewardRedemption.objects.count(), 1)

    def test_parent_metadata_patch_cannot_restore_stock_from_stale_offer(self):
        stale = Reward.objects.get(pk=self.reward.pk)
        RewardService.request_redemption(self.child, self.reward)
        client = APIClient()
        client.force_authenticate(self.parent)
        with patch.object(RewardViewSet, "get_object", return_value=stale):
            response = client.patch(
                f"/api/rewards/{self.reward.pk}/", {"name": "Renamed frame prize"}, format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 0)
        self.assertEqual(self.reward.name, "Renamed frame prize")
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(self.sibling, self.reward)

    def test_stale_api_offer_returns_existing_out_of_stock_conflict(self):
        stale = Reward.objects.get(pk=self.reward.pk)
        RewardService.request_redemption(self.child, self.reward)
        client = APIClient()
        client.force_authenticate(self.sibling)
        with patch.object(RewardViewSet, "get_object", return_value=stale):
            response = client.post(f"/api/rewards/{self.reward.pk}/redeem/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "out_of_stock")
        self.assertIn("similar", response.data)

    def test_stale_offer_uses_authoritative_price_approval_and_item(self):
        stale = Reward.objects.get(pk=self.reward.pk)
        Reward.objects.filter(pk=self.reward.pk).update(
            cost_coins=80, requires_parent_approval=False, item_definition=self.replacement,
        )
        result = RewardService.request_redemption(self.child, stale)
        self.assertEqual(result.coin_cost_snapshot, 80)
        self.assertEqual(result.status, "approved")
        self.assertEqual(CoinService.get_balance(self.child), 20)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.replacement).quantity, 1)

    def test_unlimited_request_does_not_create_stock_after_later_limit(self):
        self.reward.stock = None
        self.reward.save(update_fields=["stock"])
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(stock=5)
        RewardService.reject(RewardRedemption.objects.get(pk=pending.pk), self.parent)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 5)
        self.assertEqual(CoinService.get_balance(self.child), 100)

    def test_rejection_restores_reserved_stock_and_frozen_cost_only_once_after_edits(self):
        pending = RewardService.request_redemption(self.child, self.reward)
        Reward.objects.filter(pk=self.reward.pk).update(cost_coins=90, item_definition=self.replacement)
        RewardService.reject(pending, self.parent)
        RewardService.reject(pending, self.parent)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 1)
        self.assertEqual(CoinService.get_balance(self.child), 100)
        self.assertEqual(CoinLedger.objects.filter(redemption=pending, reason="refund").count(), 1)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_missing_historical_digital_item_stays_pending_and_can_be_refunded(self):
        Reward.objects.filter(pk=self.reward.pk).update(item_definition=None)
        self.reward.refresh_from_db()
        pending = RewardRedemption.objects.create(
            user=self.child, reward=self.reward, coin_cost_snapshot=60,
        )
        CoinService.spend_coins(
            self.child, 60, CoinLedger.Reason.REDEMPTION, redemption=pending,
        )
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.post(f"/api/redemptions/{pending.pk}/approve/")
        self.assertEqual(response.status_code, 409)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "pending")
        self.assertIsNone(pending.decided_at)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        response = client.post(f"/api/redemptions/{pending.pk}/reject/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "denied")
        self.assertEqual(CoinService.get_balance(self.child), 100)

    def test_cross_family_service_cannot_hold_coins_or_reserve_stock(self):
        foreign = make_family("Other shop", children=[{"username": "other-shop-child"}]).children[0]
        CoinLedger.objects.create(user=foreign, amount=100, reason="adjustment")
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(foreign, self.reward)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 1)
        self.assertEqual(CoinService.get_balance(foreign), 100)
        self.assertFalse(RewardRedemption.objects.filter(user=foreign).exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ShopStockConcurrencyTests(ShopFixture, TransactionTestCase):
    def test_two_buyers_with_stale_offer_have_one_winner_for_last_item(self):
        ready = Barrier(2)

        def buy(child):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                reward = Reward.objects.get(pk=self.reward.pk)
                ready.wait(timeout=10)
                try:
                    RewardService.request_redemption(child, reward)
                    return "reserved"
                except RewardUnavailableError:
                    return "out_of_stock"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(buy, child) for child in (self.child, self.sibling)]
            outcomes = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(outcomes, ["reserved", "out_of_stock"])
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 0)
        self.assertEqual(RewardRedemption.objects.count(), 1)
        self.assertEqual(CoinLedger.objects.filter(reason="redemption").count(), 1)
        self.assertCountEqual(
            [CoinService.get_balance(child) for child in (self.child, self.sibling)], [40, 100],
        )
