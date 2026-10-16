"""MCP metadata edits cannot put a reserved unit back into stock."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.mcp_server.context import get_in_family, override_user
from apps.mcp_server.errors import MCPNotFoundError
from apps.mcp_server.schemas import UpdateRewardIn
from apps.mcp_server.tools import rewards as reward_tools
from apps.rewards.models import CoinLedger, Reward
from apps.rewards.services import RewardService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MCPRewardStockIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            "MCP stock household", parents=[{"username": "stock-parent"}],
            children=[{"username": "stock-child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.reward = Reward.objects.create(
            family=family.family, name="Last prize", cost_coins=10, stock=1,
        )
        CoinLedger.objects.create(user=self.child, amount=100, reason="adjustment")

    def test_metadata_edit_rechecks_stock_after_family_lookup_and_reservation(self):
        def resolve_then_reserve(*args, **kwargs):
            stale = get_in_family(*args, **kwargs)
            RewardService.request_redemption(self.child, self.reward)
            return stale

        with override_user(self.parent), patch.object(
            reward_tools, "get_in_family", side_effect=resolve_then_reserve,
        ):
            result = reward_tools.update_reward(UpdateRewardIn(
                reward_id=self.reward.pk, description="New description",
            ))
        self.reward.refresh_from_db()
        self.assertEqual((result["stock"], self.reward.stock), (0, 0))
        self.assertEqual(self.reward.description, "New description")

    def test_foreign_and_missing_reward_updates_keep_not_found_concealment(self):
        foreign = make_family("Foreign MCP shop", parents=[{"username": "foreign-stock-parent"}])
        with override_user(foreign.parents[0]):
            for pk in (self.reward.pk, self.reward.pk + 900):
                with self.subTest(pk=pk), self.assertRaises(MCPNotFoundError):
                    reward_tools.update_reward(UpdateRewardIn(reward_id=pk, name="Not yours"))
        self.reward.refresh_from_db()
        self.assertEqual((self.reward.name, self.reward.stock), ("Last prize", 1))
