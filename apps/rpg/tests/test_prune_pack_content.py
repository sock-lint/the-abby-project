"""Tests for ``prune_pack_content`` management command + helper.

Ensures the helper only touches pack-scoped rows (namespace-prefixed
slugs) and leaves core content untouched.
"""
from __future__ import annotations

from django.test import TestCase

from apps.rewards.models import Reward
from apps.rpg.management.commands.prune_pack_content import prune_pack
from apps.rpg.models import DropTable, ItemDefinition


class PrunePackContentTests(TestCase):
    def setUp(self) -> None:
        # Core item (no pack prefix) — must survive prune
        self.core_item = ItemDefinition.objects.create(
            slug="core-food",
            name="Core Food",
            item_type=ItemDefinition.ItemType.FOOD,
            rarity="common",
        )
        # Pack item (prefixed with pack name + dash)
        self.pack_item = ItemDefinition.objects.create(
            slug="testpack-food-a",
            name="Testpack Food A",
            item_type=ItemDefinition.ItemType.FOOD,
            rarity="common",
        )
        # Core drop (must survive)
        self.core_drop = DropTable.objects.create(
            trigger_type="clock_out", item=self.core_item, weight=5,
        )
        # Pack drop (must be deleted)
        self.pack_drop = DropTable.objects.create(
            trigger_type="clock_out", item=self.pack_item, weight=3,
        )
        # Core reward (must survive)
        self.core_reward = Reward.objects.create(
            name="Core Reward",
            description="real-world",
            cost_coins=100,
            rarity="common",
        )
        # Pack reward linked to pack item (must be deleted)
        self.pack_reward = Reward.objects.create(
            name="Testpack Reward",
            description="digital",
            cost_coins=50,
            rarity="common",
            item_definition=self.pack_item,
            fulfillment_kind=Reward.FulfillmentKind.DIGITAL_ITEM,
        )

    def test_prune_deletes_pack_scoped_rows_only(self) -> None:
        counts = prune_pack("testpack", dry_run=False)
        self.assertEqual(counts, {"drops": 1, "rewards": 1})
        self.assertFalse(DropTable.objects.filter(pk=self.pack_drop.pk).exists())
        self.assertFalse(Reward.objects.filter(pk=self.pack_reward.pk).exists())
        # Core content untouched
        self.assertTrue(DropTable.objects.filter(pk=self.core_drop.pk).exists())
        self.assertTrue(Reward.objects.filter(pk=self.core_reward.pk).exists())
        # Items themselves are NEVER deleted (would cascade to UserInventory)
        self.assertTrue(ItemDefinition.objects.filter(pk=self.pack_item.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=self.core_item.pk).exists())

    def test_dry_run_reports_counts_but_persists_nothing(self) -> None:
        counts = prune_pack("testpack", dry_run=True)
        self.assertEqual(counts, {"drops": 1, "rewards": 1})
        # Nothing actually deleted
        self.assertTrue(DropTable.objects.filter(pk=self.pack_drop.pk).exists())
        self.assertTrue(Reward.objects.filter(pk=self.pack_reward.pk).exists())

    def test_unknown_pack_returns_zero_counts(self) -> None:
        counts = prune_pack("nonexistent-pack", dry_run=False)
        self.assertEqual(counts, {"drops": 0, "rewards": 0})
        # Everything still present
        self.assertTrue(DropTable.objects.filter(pk=self.pack_drop.pk).exists())

    def test_pack_name_with_trailing_dash_still_works(self) -> None:
        counts = prune_pack("testpack-", dry_run=False)
        self.assertEqual(counts, {"drops": 1, "rewards": 1})

    def test_prefix_match_is_exact_boundary(self) -> None:
        """Pack 'testpack' must not match items starting with 'testpack2-'."""
        other_pack_item = ItemDefinition.objects.create(
            slug="testpack2-food",
            name="Other Pack Food",
            item_type=ItemDefinition.ItemType.FOOD,
            rarity="common",
        )
        DropTable.objects.create(
            trigger_type="clock_out", item=other_pack_item, weight=1,
        )
        # Prune testpack — must NOT touch testpack2
        counts = prune_pack("testpack", dry_run=False)
        # testpack has 1 drop; testpack2 drop should survive (boundary = "-")
        self.assertEqual(counts["drops"], 1)
        self.assertTrue(
            DropTable.objects.filter(item__slug="testpack2-food").exists()
        )
