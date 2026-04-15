"""Tests for Tier-1.3 reward shop CRUD + coin adjustments via MCP."""
from __future__ import annotations

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    AdjustCoinsIn,
    CreateRewardIn,
    DeleteRewardIn,
    UpdateRewardIn,
)
from apps.mcp_server.tools import rewards as reward_tools
from apps.projects.models import User
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService
from apps.rpg.models import ItemDefinition


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )


class CreateRewardTests(_Base):
    def test_basic_create(self) -> None:
        with override_user(self.parent):
            result = reward_tools.create_reward(CreateRewardIn(
                name="Ice Cream",
                cost_coins=50,
                rarity="common",
            ))
        self.assertEqual(result["name"], "Ice Cream")
        self.assertEqual(
            Reward.objects.filter(name="Ice Cream").count(), 1,
        )

    def test_duplicate_name_rejected(self) -> None:
        Reward.objects.create(name="Exists", cost_coins=10)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.create_reward(CreateRewardIn(
                name="Exists", cost_coins=20,
            ))

    def test_child_cannot_create(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            reward_tools.create_reward(CreateRewardIn(
                name="Sneaky", cost_coins=1,
            ))

    def test_digital_item_requires_slug(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.create_reward(CreateRewardIn(
                name="Bare Digital",
                cost_coins=50,
                fulfillment_kind="digital_item",
                # no item_definition_slug
            ))

    def test_digital_item_with_slug_links(self) -> None:
        item = ItemDefinition.objects.create(
            slug="gold-frame",
            name="Gold Frame",
            icon="🖼️",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
        )
        with override_user(self.parent):
            result = reward_tools.create_reward(CreateRewardIn(
                name="Gold Frame Shop",
                cost_coins=500,
                fulfillment_kind="digital_item",
                item_definition_slug="gold-frame",
            ))
        reward = Reward.objects.get(pk=result["id"])
        self.assertEqual(reward.item_definition_id, item.id)

    def test_unknown_item_slug_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.create_reward(CreateRewardIn(
                name="Bad Link",
                cost_coins=1,
                fulfillment_kind="digital_item",
                item_definition_slug="does-not-exist",
            ))


class UpdateRewardTests(_Base):
    def test_partial_update(self) -> None:
        reward = Reward.objects.create(name="R", cost_coins=10)
        with override_user(self.parent):
            result = reward_tools.update_reward(UpdateRewardIn(
                reward_id=reward.id,
                description="now with sprinkles",
                cost_coins=25,
            ))
        reward.refresh_from_db()
        self.assertEqual(reward.cost_coins, 25)
        self.assertIn("sprinkles", reward.description)

    def test_clear_stock_sets_unlimited(self) -> None:
        reward = Reward.objects.create(name="R", cost_coins=10, stock=3)
        with override_user(self.parent):
            reward_tools.update_reward(UpdateRewardIn(
                reward_id=reward.id, clear_stock=True,
            ))
        reward.refresh_from_db()
        self.assertIsNone(reward.stock)

    def test_rename_conflict_rejected(self) -> None:
        a = Reward.objects.create(name="A", cost_coins=10)
        Reward.objects.create(name="B", cost_coins=10)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.update_reward(UpdateRewardIn(
                reward_id=a.id, name="B",
            ))


class DeleteRewardTests(_Base):
    def test_delete_unused_reward(self) -> None:
        reward = Reward.objects.create(name="Disposable", cost_coins=1)
        with override_user(self.parent):
            result = reward_tools.delete_reward(
                DeleteRewardIn(reward_id=reward.id),
            )
        self.assertTrue(result["deleted"])

    def test_cannot_delete_with_redemption_history(self) -> None:
        reward = Reward.objects.create(name="Used", cost_coins=10)
        CoinService.award_coins(
            self.child, 100, CoinLedger.Reason.ADJUSTMENT, description="seed",
        )
        RewardService.request_redemption(self.child, reward)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.delete_reward(DeleteRewardIn(reward_id=reward.id))


class AdjustCoinsTests(_Base):
    def test_grant_coins_updates_balance(self) -> None:
        with override_user(self.parent):
            result = reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=50,
                description="weekly bonus",
            ))
        self.assertEqual(result["new_balance"], 50)

    def test_revoke_goes_through_spend(self) -> None:
        CoinService.award_coins(
            self.child, 100, CoinLedger.Reason.ADJUSTMENT, description="seed",
        )
        with override_user(self.parent):
            result = reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=-30, description="late chore",
            ))
        self.assertEqual(result["new_balance"], 70)

    def test_zero_amount_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=0, description="noop",
            ))

    def test_child_cannot_adjust(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            reward_tools.adjust_coins(AdjustCoinsIn(
                user_id=self.child.id, amount=100, description="self-grant",
            ))
