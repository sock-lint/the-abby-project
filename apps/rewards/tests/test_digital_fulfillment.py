"""Tests for Tier-5 shop-reward ↔ RPG item fulfillment bridge."""
from __future__ import annotations

from django.test import TestCase

from apps.projects.models import User
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService, RewardService
from apps.rpg.models import ItemDefinition, UserInventory


class DigitalItemFulfillmentTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.item = ItemDefinition.objects.create(
            slug="shop-frame-gold",
            name="Gold Frame",
            icon="🖼️",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity="rare",
            coin_value=0,
        )
        # Give the child enough coins to redeem.
        CoinService.award_coins(
            self.child, 500, CoinLedger.Reason.ADJUSTMENT,
            description="seed",
        )

    def _make_reward(self, *, fulfillment_kind, item=None, require_approval=True):
        return Reward.objects.create(
            name=f"Test {fulfillment_kind}-{bool(item)}",
            cost_coins=100,
            requires_parent_approval=require_approval,
            fulfillment_kind=fulfillment_kind,
            item_definition=item,
        )

    def test_real_world_approval_does_not_touch_inventory(self) -> None:
        reward = self._make_reward(
            fulfillment_kind=Reward.FulfillmentKind.REAL_WORLD,
            item=self.item,  # even if set, real_world ignores it
        )
        redemption = RewardService.request_redemption(self.child, reward)
        RewardService.approve(redemption, self.parent)
        self.assertFalse(
            UserInventory.objects.filter(
                user=self.child, item=self.item,
            ).exists(),
        )

    def test_digital_item_approval_credits_inventory(self) -> None:
        reward = self._make_reward(
            fulfillment_kind=Reward.FulfillmentKind.DIGITAL_ITEM,
            item=self.item,
        )
        redemption = RewardService.request_redemption(self.child, reward)
        RewardService.approve(redemption, self.parent)
        inv = UserInventory.objects.get(user=self.child, item=self.item)
        self.assertEqual(inv.quantity, 1)

    def test_both_approval_credits_inventory(self) -> None:
        reward = self._make_reward(
            fulfillment_kind=Reward.FulfillmentKind.BOTH,
            item=self.item,
        )
        redemption = RewardService.request_redemption(self.child, reward)
        RewardService.approve(redemption, self.parent)
        inv = UserInventory.objects.get(user=self.child, item=self.item)
        self.assertEqual(inv.quantity, 1)

    def test_digital_item_second_approval_adds_to_existing_quantity(self) -> None:
        reward = self._make_reward(
            fulfillment_kind=Reward.FulfillmentKind.DIGITAL_ITEM,
            item=self.item,
        )
        # First redemption
        r1 = RewardService.request_redemption(self.child, reward)
        RewardService.approve(r1, self.parent)
        # Second redemption of the same reward
        r2 = RewardService.request_redemption(self.child, reward)
        RewardService.approve(r2, self.parent)
        inv = UserInventory.objects.get(user=self.child, item=self.item)
        self.assertEqual(inv.quantity, 2)

    def test_digital_item_without_fk_is_noop_not_error(self) -> None:
        reward = self._make_reward(
            fulfillment_kind=Reward.FulfillmentKind.DIGITAL_ITEM,
            item=None,  # mis-configured — LLM forgot to link
        )
        redemption = RewardService.request_redemption(self.child, reward)
        # Should not raise
        RewardService.approve(redemption, self.parent)
        redemption.refresh_from_db()
        self.assertEqual(redemption.status, RewardRedemption.Status.FULFILLED)


class LoaderRewardItemLinkTests(TestCase):
    """Verify the RPG content loader wires rewards.yaml to ItemDefinitions."""

    def test_loader_links_reward_to_item_via_slug(self) -> None:
        import tempfile
        from pathlib import Path

        from apps.rpg.content.loader import ContentPack

        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "testpack"
            pack_dir.mkdir()
            (pack_dir / "items.yaml").write_text(
                "items:\n"
                "  - slug: goldframe\n"
                "    name: Gold Frame\n"
                "    item_type: cosmetic_frame\n"
                "    rarity: rare\n",
                encoding="utf-8",
            )
            (pack_dir / "rewards.yaml").write_text(
                "rewards:\n"
                "  - name: Gold Frame Shop Reward\n"
                "    cost_coins: 250\n"
                "    fulfillment_kind: digital_item\n"
                "    item_definition: goldframe\n",
                encoding="utf-8",
            )
            ContentPack(pack_dir, namespace="testpack-").load()

        reward = Reward.objects.get(name="Gold Frame Shop Reward")
        self.assertIsNotNone(reward.item_definition_id)
        self.assertEqual(reward.item_definition.slug, "testpack-goldframe")
        self.assertEqual(
            reward.fulfillment_kind,
            Reward.FulfillmentKind.DIGITAL_ITEM,
        )

    def test_loader_raises_for_unknown_item_slug(self) -> None:
        import tempfile
        from pathlib import Path

        from apps.rpg.content.loader import ContentPack, ContentPackError

        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "badpack"
            pack_dir.mkdir()
            (pack_dir / "rewards.yaml").write_text(
                "rewards:\n"
                "  - name: Ghost\n"
                "    cost_coins: 1\n"
                "    fulfillment_kind: digital_item\n"
                "    item_definition: does-not-exist\n",
                encoding="utf-8",
            )
            with self.assertRaises(ContentPackError):
                ContentPack(pack_dir, namespace="badpack-").load()
