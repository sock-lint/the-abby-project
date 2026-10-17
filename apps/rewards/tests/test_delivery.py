"""Real-world approval is a promise; delivery is a separate parent receipt."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.activity.models import ActivityEvent
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


class DeliveryFixture:
    def setUp(self):
        family = make_family(parents=[{"username": "delivery-parent"}], children=[{"username": "delivery-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.foreign = make_family("Other delivery", parents=[{"username": "other-parent"}]).parents[0]
        self.reward = Reward.objects.create(family=family.family, name="Museum trip", cost_coins=30, stock=3)
        CoinLedger.objects.create(user=self.child, amount=100, reason="adjustment")
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def redeem(self):
        return RewardService.request_redemption(self.child, self.reward)


class RewardDeliveryTests(DeliveryFixture, TestCase):
    def test_approval_waits_for_parent_delivery_preserving_approval_audit(self):
        row = self.redeem()
        response = self.client.post(f"/api/redemptions/{row.pk}/approve/", {"notes": "Saturday after lunch."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "approved")
        self.assertIsNone(response.data["delivered_at"])
        decided_at = response.data["decided_at"]
        for _ in range(2):
            response = self.client.post(f"/api/redemptions/{row.pk}/deliver/", {}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], "fulfilled")
            self.assertEqual(response.data["decided_at"], decided_at)
            self.assertEqual(response.data["parent_notes"], "Saturday after lunch.")
            self.assertEqual(response.data["delivered_by"], self.parent.pk)
            self.assertIsNotNone(response.data["delivered_at"])
        self.assertEqual(ActivityEvent.objects.filter(event_type="reward.deliver").count(), 1)
        self.assertEqual(CoinService.get_balance(self.child), 70)
        self.assertEqual(CoinLedger.objects.filter(redemption=row).count(), 1)

    def test_no_approval_real_world_reward_still_waits_for_delivery(self):
        self.reward.requires_parent_approval = False
        self.reward.save(update_fields=["requires_parent_approval"])
        row = self.redeem()
        self.assertEqual(row.status, "approved")
        self.assertIsNone(row.decided_by)
        self.assertIsNone(row.delivered_at)
        self.assertEqual(RewardService.deliver(row, self.parent).status, "fulfilled")

    def test_combined_saved_promise_credits_item_once_at_approval_not_delivery(self):
        item = ItemDefinition.objects.create(slug="delivery-frame", name="Frame", item_type="cosmetic_frame")
        self.reward.fulfillment_kind = "both"
        self.reward.item_definition = item
        self.reward.save(update_fields=["fulfillment_kind", "item_definition"])
        row = self.redeem()
        stale = RewardRedemption.objects.get(pk=row.pk)
        # Editing the offer must not change this accepted promise.
        Reward.objects.filter(pk=self.reward.pk).update(fulfillment_kind="real_world", item_definition=None)
        RewardService.approve(row, self.parent)
        RewardService.approve(stale, self.parent)
        self.assertEqual(row.status, "approved")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)
        RewardService.deliver(row, self.parent)
        RewardService.deliver(stale, self.parent)
        RewardService.reject(stale, self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)
        self.assertEqual(CoinService.get_balance(self.child), 70)
        self.assertFalse(CoinLedger.objects.filter(redemption=row, reason="refund").exists())
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 2)

    def test_digital_only_still_fulfills_immediately_and_deliver_replay_adds_nothing(self):
        item = ItemDefinition.objects.create(slug="instant-frame", name="Instant frame", item_type="cosmetic_frame")
        self.reward.fulfillment_kind = "digital_item"
        self.reward.item_definition = item
        self.reward.save(update_fields=["fulfillment_kind", "item_definition"])
        row = self.redeem()
        RewardService.approve(row, self.parent)
        self.assertEqual(row.status, "fulfilled")
        RewardService.deliver(row, self.parent)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)
        self.assertIsNone(row.delivered_at)

    def test_delivery_requires_parent_in_same_family_even_on_direct_service_calls(self):
        row = self.redeem()
        RewardService.approve(row, self.parent)
        for actor, expected in [(self.child, 403), (self.foreign, 404)]:
            with self.subTest(actor=actor.username):
                self.client.force_authenticate(actor)
                response = self.client.post(f"/api/redemptions/{row.pk}/deliver/")
                self.assertEqual(response.status_code, expected)
                with self.assertRaises(PermissionDenied):
                    RewardService.deliver(row, actor)
        row.refresh_from_db()
        self.assertEqual(row.status, "approved")
        self.assertIsNone(row.delivered_at)

    def test_pending_and_denied_requests_cannot_be_delivered(self):
        row = self.redeem()
        for rejected in [False, True]:
            if rejected:
                RewardService.reject(row, self.parent)
            response = self.client.post(f"/api/redemptions/{row.pk}/deliver/")
            self.assertEqual(response.status_code, 409)
        row.refresh_from_db()
        self.assertEqual(row.status, "denied")
        self.assertIsNone(row.delivered_at)
        self.assertEqual(CoinService.get_balance(self.child), 100)

    def test_historical_fulfilled_receipt_is_not_rewritten(self):
        row = self.redeem()
        RewardRedemption.objects.filter(pk=row.pk).update(status="fulfilled")
        result = RewardService.deliver(row, self.parent)
        self.assertEqual(result.status, "fulfilled")
        self.assertIsNone(result.delivered_at)
        self.assertFalse(ActivityEvent.objects.filter(event_type="reward.deliver").exists())

    def test_failed_delivery_audit_rolls_back_then_retry_succeeds(self):
        row = self.redeem()
        RewardService.approve(row, self.parent)
        with patch("apps.activity.services.ActivityLogService.record", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                RewardService.deliver(row, self.parent)
        row.refresh_from_db()
        self.assertEqual(row.status, "approved")
        self.assertIsNone(row.delivered_at)
        RewardService.deliver(row, self.parent)
        self.assertEqual(row.status, "fulfilled")

    def test_approved_deliveries_filter_is_separate_from_pending_approvals(self):
        row = self.redeem()
        RewardService.approve(row, self.parent)
        pending = self.client.get("/api/redemptions/?status=pending")
        approved = self.client.get("/api/redemptions/?status=approved")
        self.assertEqual(pending.data["count"], 0)
        self.assertEqual([item["id"] for item in approved.data["results"]], [row.pk])


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class RewardDeliveryConcurrencyTests(DeliveryFixture, TransactionTestCase):
    def test_concurrent_delivery_retries_save_one_receipt_without_refund(self):
        item = ItemDefinition.objects.create(slug="concurrent-frame", name="Frame", item_type="cosmetic_frame")
        self.reward.fulfillment_kind = "both"
        self.reward.item_definition = item
        self.reward.save(update_fields=["fulfillment_kind", "item_definition"])
        row = self.redeem()
        RewardService.approve(row, self.parent)
        ready = Barrier(2)

        def deliver():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                stale = RewardRedemption.objects.get(pk=row.pk)
                ready.wait(timeout=10)
                result = RewardService.deliver(stale, self.parent)
                return result.status, result.delivered_at
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(deliver) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], "fulfilled")
        self.assertEqual(ActivityEvent.objects.filter(event_type="reward.deliver").count(), 1)
        self.assertEqual(CoinService.get_balance(self.child), 70)
        self.assertEqual(CoinLedger.objects.filter(redemption=row).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)
