"""Saved physical promises remain deliverable after account deactivation."""
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import rpg_management
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InactiveRedemptionDeliveryTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Saved delivery household", parents=[{
            "username": "saved-delivery-parent", "is_staff": True,
        }], children=[{"username": "saved-delivery-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        other = make_family("Foreign delivery household", parents=[{
            "username": "foreign-delivery-parent", "is_staff": True,
        }], children=[{"username": "foreign-delivery-child"}])
        self.foreign_parent, self.foreign_child = other.parents[0], other.children[0]
        self.reward = Reward.objects.create(family=family.family, name="Saved park outing", cost_coins=5,
            fulfillment_kind="real_world", requires_parent_approval=False)
        CoinService.award_coins(self.child, 50, CoinLedger.Reason.ADJUSTMENT)
        self.redemption = RewardService.request_redemption(self.child, self.reward)

    def wire(self, *, name="deliver_reward_redemption", params=None, actor=None, scopes=None, confirmation=True):
        with override_user(actor or self.parent, scopes=scopes if scopes is not None else frozenset({"mcp:read", "mcp:write"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params or {
                "user_id": self.child.pk, "redemption_id": self.redemption.pk,
            }, "confirmation": confirmation})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def assert_error(self, result, code):
        self.assertIn("error", result, result)
        self.assertEqual(result["error"]["code"], code, result)

    def deactivate_child(self):
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)

    def balances(self):
        return (list(CoinLedger.objects.order_by("pk").values()), list(UserInventory.objects.order_by("pk").values()))

    def test_inactive_saved_promise_is_readable_deliverable_and_replayable_without_more_rewards(self):
        self.deactivate_child()
        before = self.balances()
        saved = self.wire(name="get_reward_redemption")
        self.assertEqual(saved["status"], "approved")
        delivered = self.wire()
        self.assertNotIn("error", delivered, delivered)
        self.assertEqual((delivered["status"], delivered["delivered_by"]), ("fulfilled", self.parent.pk))
        self.assertTrue(delivered["delivered_at"])
        self.assertEqual(delivered["decided_at"], saved["decided_at"])
        self.assertEqual(delivered["decided_by"], saved["decided_by"])
        self.assertEqual(self.wire(), delivered)
        self.assertEqual(self.balances(), before)
        native = APIClient()
        native.force_authenticate(self.parent)
        replay = native.post(f"/api/redemptions/{self.redemption.pk}/deliver/", {}, format="json")
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["delivered_at"], delivered["delivered_at"])
        self.assertEqual(self.balances(), before)

    def test_active_saved_physical_promise_still_delivers(self):
        self.assertEqual(self.wire()["status"], "fulfilled")

    def test_inactive_combined_promise_keeps_the_digital_grant_from_approval(self):
        item = ItemDefinition.objects.create(slug="saved-combined-food", name="Saved snack", item_type="food")
        reward = Reward.objects.create(family=self.parent.family, name="Outing and snack", cost_coins=5,
            fulfillment_kind="both", item_definition=item, requires_parent_approval=False)
        redemption = RewardService.request_redemption(self.child, reward)
        self.assertEqual(redemption.status, "approved")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)
        self.deactivate_child()
        before = self.balances()
        delivered = self.wire(params={"user_id": self.child.pk, "redemption_id": redemption.pk})
        self.assertNotIn("error", delivered, delivered)
        self.assertEqual(delivered["status"], "fulfilled")
        self.assertEqual(self.wire(params={"user_id": self.child.pk, "redemption_id": redemption.pk}), delivered)
        self.assertEqual(self.balances(), before)

    def test_native_delivery_while_inactive_then_mcp_retry_preserves_original_audit(self):
        self.deactivate_child()
        before = self.balances()
        native = APIClient()
        native.force_authenticate(self.parent)
        delivered = native.post(f"/api/redemptions/{self.redemption.pk}/deliver/", {}, format="json")
        self.assertEqual(delivered.status_code, 200, delivered.data)
        replay = self.wire()
        self.assertNotIn("error", replay, replay)
        self.assertEqual(replay["status"], "fulfilled")
        self.assertEqual(replay["delivered_at"], delivered.data["delivered_at"])
        self.assertEqual(self.balances(), before)

    def test_inactive_pending_denied_and_canceled_promises_remain_invalid(self):
        self.deactivate_child()
        for status in ("pending", "denied", "canceled"):
            with self.subTest(status=status):
                RewardRedemption.objects.filter(pk=self.redemption.pk).update(status=status)
                before = self.balances()
                self.assert_error(self.wire(), "invalid_request")
                self.redemption.refresh_from_db()
                self.assertEqual(self.redemption.status, status)
                self.assertIsNone(self.redemption.delivered_at)
                self.assertEqual(self.balances(), before)

    def test_inactive_malformed_digital_only_approved_promise_cannot_be_physically_delivered(self):
        self.deactivate_child()
        item = ItemDefinition.objects.create(slug="saved-delivery-food", name="Saved food", item_type="food")
        RewardRedemption.objects.filter(pk=self.redemption.pk).update(
            fulfillment_kind_snapshot="digital_item", item_definition_snapshot=item)
        before = self.balances()
        self.assert_error(self.wire(), "invalid_request")
        self.assertEqual(self.balances(), before)

    def test_foreign_and_departed_child_promises_stay_hidden(self):
        self.deactivate_child()
        self.assert_error(self.wire(params={"user_id": self.foreign_child.pk,
            "redemption_id": self.redemption.pk}), "not_found")
        get_user_model().objects.filter(pk=self.child.pk).update(family=self.foreign_parent.family)
        self.assert_error(self.wire(), "not_found")
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, "approved")

    def test_target_move_after_scalar_resolution_is_rechecked_before_delivery(self):
        self.deactivate_child()
        original = rpg_management.resolve_child_in_family
        def moved(actor, requested):
            child = original(actor, requested)
            get_user_model().objects.filter(pk=child.pk).update(family=self.foreign_parent.family)
            return child
        with patch.object(rpg_management, "resolve_child_in_family", side_effect=moved):
            self.assert_error(self.wire(), "not_found")
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, "approved")

    def test_cached_parent_must_retain_current_activity_staff_role_and_family(self):
        self.deactivate_child()
        for changes in ({"is_active": False}, {"is_staff": False}, {"role": "child"},
                        {"family": self.foreign_parent.family}):
            with self.subTest(changes=changes):
                get_user_model().objects.filter(pk=self.parent.pk).update(**changes)
                result = self.wire()
                self.assertIn("error", result, result)
                self.assertIn(result["error"]["code"], {"permission_denied", "not_found"})
                get_user_model().objects.filter(pk=self.parent.pk).update(
                    is_active=True, is_staff=True, role="parent", family=self.child.family)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, "approved")

    def test_delivery_still_requires_write_scope_confirmation_and_parent_role(self):
        self.deactivate_child()
        self.assert_error(self.wire(scopes=frozenset({"mcp:read"})), "permission_denied")
        self.assert_error(self.wire(confirmation=False), "confirmation_required")
        self.assert_error(self.wire(actor=self.child), "permission_denied")
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, "approved")
