from collections import defaultdict
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.pets.expeditions import ExpeditionService
from apps.pets.models import PetSpecies, PotionType, UserMount
from apps.projects.models import User
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, DropService


class RarityBalanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rarity-odds", role="child")

    def entry(self, name, rarity, kind="food", weight=10, trigger="clock_out"):
        item = ItemDefinition.objects.create(name=name, item_type=kind, rarity=rarity)
        return DropTable.objects.create(item=item, trigger_type=trigger, weight=weight)

    def capture_drop(self):
        captured = []
        def pick(entries, *, weights, k):
            captured.append((entries, weights))
            return [max(zip(entries, weights), key=lambda pair: pair[1])[0]]
        with patch("apps.rpg.services.random.random", return_value=0), patch(
            "apps.rpg.services.random.choices", side_effect=pick,
        ):
            result = DropService.process_drops(self.user, "clock_out")
        totals = defaultdict(float)
        entries, weights = captured[0]
        for entry, weight in zip(entries, weights):
            totals[entry.item.rarity] += weight
        return result, {key: value / sum(weights) for key, value in totals.items()}

    def test_catalog_growth_does_not_dilute_tier_odds(self):
        self.entry("Common food", "common")
        self.entry("Rare food", "rare", weight=2)
        _result, before = self.capture_drop()
        for number in range(20):
            self.entry(f"Extra common {number}", "common")
        _result, after = self.capture_drop()
        self.assertAlmostEqual(before["rare"], after["rare"])
        self.assertAlmostEqual(after["rare"], 10 / 70)

    def test_same_tier_unowned_cosmetics_precede_duplicate_salvage(self):
        first = self.entry("Earlier frame", "rare", "cosmetic_frame")
        second = self.entry("New frame", "rare", "cosmetic_frame")
        UserInventory.objects.create(user=self.user, item=first.item)
        result, odds = self.capture_drop()
        self.assertEqual(result[0]["item_id"], second.item_id)
        self.assertFalse(result[0]["was_salvaged"])
        self.assertAlmostEqual(odds["rare"], 1)

    def test_expedition_tier_budget_excludes_unlisted_rarities(self):
        from apps.pets.expeditions import ExpeditionService
        self.entry("Rare snack", "rare")
        self.entry("Legendary snack", "legendary")
        captured = []
        def pick(entries, *, weights, k):
            captured.append((entries, weights))
            return [entries[0]]
        with patch("apps.pets.expeditions.random.choices", side_effect=pick):
            ExpeditionService._roll_loot(self.user, "short")
        entries, weights = captured[0]
        legendary = sum(weight for entry, weight in zip(entries, weights) if entry.item.rarity == "legendary")
        self.assertEqual(legendary, 0)

    def lucky_dip(self, quantity=1):
        item = ItemDefinition.objects.create(
            name="Rare cosmetic dip", item_type="consumable", rarity="rare",
            metadata={"effect": "lucky_dip", "rarities": ["rare"]},
        )
        UserInventory.objects.create(user=self.user, item=item, quantity=quantity)
        return item

    def test_lucky_dip_consumption_prefers_unowned_same_tier_collectible(self):
        owned = self.entry("Owned rare frame", "rare", "cosmetic_frame").item
        unowned = self.entry("Unowned rare title", "rare", "cosmetic_title").item
        UserInventory.objects.create(user=self.user, item=owned)
        dip = self.lucky_dip()

        # Choosing the highest effective weight makes an owned selection
        # deterministic if duplicate protection ever stops being applied.
        def pick(items, *, weights, k):
            return [max(zip(items, weights), key=lambda pair: pair[1])[0]]

        with patch("apps.rpg.services.random.choices", side_effect=pick):
            result = ConsumableService.use(self.user, dip.pk)
        self.assertEqual(result["detail"]["granted_item_id"], unowned.pk)
        self.assertFalse(result["detail"]["salvaged"])
        self.assertFalse(UserInventory.objects.filter(user=self.user, item=dip).exists())
        self.assertEqual(UserInventory.objects.get(user=self.user, item=unowned).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=owned).quantity, 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.user).exists())

    def test_lucky_dip_all_owned_keeps_exact_coin_salvage_when_consumed_in_bulk(self):
        frame = self.entry("Collected rare frame", "rare", "cosmetic_frame").item
        frame.coin_value = 27
        frame.save(update_fields=["coin_value"])
        UserInventory.objects.create(user=self.user, item=frame)
        dip = self.lucky_dip(quantity=2)
        result = ConsumableService.use(self.user, dip.pk, quantity=2)
        self.assertEqual(result["quantity_used"], 2)
        self.assertEqual([row["salvaged"] for row in result["details"]], [True, True])
        self.assertEqual(list(CoinLedger.objects.filter(user=self.user).values_list("amount", flat=True)), [27, 27])
        self.assertEqual(UserInventory.objects.get(user=self.user, item=frame).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.user, item=dip).exists())

    def test_expedition_avoids_duplicate_cosmetics_within_locked_loot_and_claims_once(self):
        species = PetSpecies.objects.create(slug="rarity-qa-mount", name="QA mount")
        potion = PotionType.objects.create(slug="base", name="Base")
        mount = UserMount.objects.create(user=self.user, species=species, potion=potion)
        entries = [self.entry(f"Unowned frame {number}", "rare", "cosmetic_frame", trigger="expedition_returned")
                   for number in range(3)]

        def pick(items, *, weights, k):
            return [max(zip(items, weights), key=lambda pair: pair[1])[0]]

        with patch("apps.pets.expeditions.random.choices", side_effect=pick):
            expedition = ExpeditionService.start(self.user, mount.pk, "long")
        expected_ids = {entry.item_id for entry in entries}
        self.assertEqual({row["item_id"] for row in expedition.loot["items"]}, expected_ids)
        self.assertEqual(len(expedition.loot["items"]), 3)
        expedition.returns_at = timezone.now() - timedelta(seconds=1)
        expedition.save(update_fields=["returns_at"])
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            first = ExpeditionService.claim(self.user, expedition.pk)
            second = ExpeditionService.claim(self.user, expedition.pk)
        self.assertTrue(first["freshly_claimed"])
        self.assertFalse(second["freshly_claimed"])
        self.assertEqual({row["item_id"] for row in first["items"]}, expected_ids)
        self.assertEqual(dict(UserInventory.objects.filter(user=self.user, item_id__in=expected_ids)
                              .values_list("item_id", "quantity")), dict.fromkeys(expected_ids, 1))
