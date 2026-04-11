"""Tests for reward / coin MCP tools."""
from __future__ import annotations

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    DecideRedemptionIn,
    GetCoinBalanceIn,
    ListRewardsIn,
    RequestRedemptionIn,
)
from apps.mcp_server.tools import rewards as reward_tools
from apps.projects.models import User
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService


class CoinBalanceTests(TestCase):
    def setUp(self) -> None:
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        CoinService.award_coins(
            self.child, 50, CoinLedger.Reason.HOURLY, description="test",
        )

    def test_get_balance_returns_total(self) -> None:
        with override_user(self.child):
            result = reward_tools.get_coin_balance(GetCoinBalanceIn())
        self.assertEqual(result["balance"], 50)
        self.assertIn("breakdown", result)
        self.assertEqual(len(result["recent_ledger"]), 1)

    def test_list_rewards_exposes_balance(self) -> None:
        Reward.objects.create(name="Ice cream", cost_coins=30)
        with override_user(self.child):
            result = reward_tools.list_rewards(ListRewardsIn())
        self.assertEqual(result["balance"], 50)
        self.assertEqual(len(result["rewards"]), 1)


class RequestRedemptionTests(TestCase):
    def setUp(self) -> None:
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.reward = Reward.objects.create(
            name="Extra screen time", cost_coins=20,
            requires_parent_approval=True,
        )

    def test_insufficient_coins_raises_validation_error(self) -> None:
        with override_user(self.child), self.assertRaises(MCPValidationError):
            reward_tools.request_redemption(
                RequestRedemptionIn(reward_id=self.reward.id),
            )

    def test_happy_path_holds_coins(self) -> None:
        CoinService.award_coins(
            self.child, 100, CoinLedger.Reason.HOURLY, description="seed",
        )
        with override_user(self.child):
            result = reward_tools.request_redemption(
                RequestRedemptionIn(reward_id=self.reward.id),
            )
        self.assertEqual(result["status"], "pending")
        self.assertEqual(CoinService.get_balance(self.child), 80)


class ApproveDenyRedemptionTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.reward = Reward.objects.create(
            name="Toy", cost_coins=10, requires_parent_approval=True,
        )
        CoinService.award_coins(
            self.child, 50, CoinLedger.Reason.HOURLY, description="seed",
        )
        with override_user(self.child):
            self.redemption_id = reward_tools.request_redemption(
                RequestRedemptionIn(reward_id=self.reward.id),
            )["id"]

    def test_child_cannot_approve(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            reward_tools.approve_redemption(
                DecideRedemptionIn(redemption_id=self.redemption_id),
            )

    def test_parent_approve_fulfills(self) -> None:
        with override_user(self.parent):
            result = reward_tools.approve_redemption(
                DecideRedemptionIn(redemption_id=self.redemption_id, notes="yes"),
            )
        self.assertEqual(result["status"], "fulfilled")
        self.assertEqual(CoinService.get_balance(self.child), 40)

    def test_parent_deny_refunds(self) -> None:
        with override_user(self.parent):
            result = reward_tools.deny_redemption(
                DecideRedemptionIn(redemption_id=self.redemption_id, notes="no"),
            )
        self.assertEqual(result["status"], "denied")
        # Held 10 deducted at request, refunded back on deny => 50.
        self.assertEqual(CoinService.get_balance(self.child), 50)
