"""New random payouts change without repricing established rewards."""
from datetime import timedelta
from importlib import import_module
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestRewardItem
from apps.quests.services import QuestService
from apps.rewards.services import CoinService
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, DropService, InventoryItemService
from config.tests.factories import make_family


class NewRandomCoinPolicyTests(TestCase):
    def setUp(self):
        self.user = make_family("Coin policy", children=[{"username": "policy-child"}]).children[0]
        self.old, _ = ItemDefinition.objects.get_or_create(slug="pouch-medium", defaults={
            "name": "Medium Coin Pouch", "icon": "P", "item_type": "coin_pouch",
            "rarity": "uncommon", "coin_value": 15, "metadata": {"coins": 15},
        })
        self.new, _ = ItemDefinition.objects.get_or_create(slug="pouch-medium-v2", defaults={
            "name": "Medium Coin Pouch (3 Coins)", "icon": "P", "item_type": "coin_pouch",
            "rarity": "uncommon", "coin_value": 3,
            "metadata": {"coins": 3, "no_random_drop": True},
        })

    def choose_old(self, candidates, **kwargs):
        return [next(candidate for candidate in candidates
                     if getattr(candidate, "item", candidate).pk == self.old.pk)]

    def roll_drop(self, trigger="clock_out"):
        DropTable.objects.create(item=self.old, trigger_type=trigger, weight=1)
        with patch("apps.rpg.services.random.random", return_value=0), patch(
            "apps.rpg.services.random.choices", side_effect=self.choose_old,
        ):
            return DropService.process_drops(self.user, trigger)

    def test_activity_drop_grants_reduced_version_without_changing_original_stack(self):
        UserInventory.objects.create(user=self.user, item=self.old, quantity=2)
        result = self.roll_drop()
        self.assertEqual(result[0]["item_id"], self.new.pk)
        self.assertEqual(DropLog.objects.get(user=self.user).item_id, self.new.pk)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.old).quantity, 2)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.new).quantity, 1)
        self.old.refresh_from_db()
        self.assertEqual((self.old.coin_value, self.old.metadata), (15, {"coins": 15}))

    def test_accomplishment_drop_uses_same_reduced_pouch(self):
        DropTable.objects.create(item=self.old, trigger_type="perfect_day", weight=1)
        with patch("apps.rpg.services.random.random", return_value=0), patch(
            "apps.rpg.services.random.choices", side_effect=self.choose_old,
        ):
            result = DropService.award_accomplishment(self.user, "perfect_day")
        self.assertEqual(result[0]["item_id"], self.new.pk)

    def test_owned_mystery_box_keeps_original_selected_pouch_without_extra_candidates(self):
        box = ItemDefinition.objects.create(name="Policy mystery", item_type="consumable",
            metadata={"effect": "mystery_box"})
        UserInventory.objects.create(user=self.user, item=box)
        with patch("apps.rpg.services.random.choices", side_effect=self.choose_old) as choices:
            result = ConsumableService.use(self.user, box.pk)
        self.assertEqual(result["detail"]["granted_item_id"], self.old.pk)
        self.assertNotIn(self.new.pk, {item.pk for item in choices.call_args.args[0]})

    def test_existing_pouch_still_opens_for_full_value_with_lucky_coin(self):
        UserInventory.objects.create(user=self.user, item=self.old)
        CharacterProfile.objects.filter(user=self.user).update(
            coin_boost_expires_at=timezone.now() + timedelta(hours=1))
        result = InventoryItemService.open_coin_pouch(self.user, self.old.pk)
        self.assertEqual(result["coins_awarded"], 15)
        self.assertEqual(CoinService.get_balance(self.user), 15)

    def test_inventory_hints_omit_an_unavailable_replacement_instead_of_failing(self):
        DropTable.objects.create(item=self.old, trigger_type="clock_out", weight=1)
        UserInventory.objects.create(user=self.user, item=self.old)
        client = APIClient()
        client.force_authenticate(self.user)
        self.assertEqual(client.get("/api/inventory/").status_code, 200)
        ItemDefinition.objects.filter(pk=self.new.pk).update(coin_value=99)
        self.assertEqual(client.get("/api/inventory/").status_code, 200)
        self.new.delete()
        self.assertEqual(client.get("/api/inventory/").status_code, 200)

    def test_missing_replacement_fails_random_award_without_repricing_or_fallback(self):
        self.new.delete()
        UserInventory.objects.create(user=self.user, item=self.old, quantity=2)
        with self.assertRaisesMessage(ValueError, "pouch definition is unavailable"):
            self.roll_drop()
        self.assertFalse(DropLog.objects.filter(user=self.user).exists())
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.old).quantity, 2)
        self.assertEqual(CoinService.get_balance(self.user), 0)

    def test_altered_replacement_fails_read_only_lookup(self):
        from apps.rpg.coin_policy import resolve_random_pouch
        ItemDefinition.objects.filter(pk=self.new.pk).update(coin_value=99)
        before = list(ItemDefinition.objects.order_by("pk").values())
        with self.assertRaisesMessage(ValueError, "pouch definition is unavailable"):
            resolve_random_pouch(self.old)
        self.assertEqual(list(ItemDefinition.objects.order_by("pk").values()), before)

    def test_new_pouch_api_explains_and_pays_its_reduced_face_value(self):
        UserInventory.objects.create(user=self.user, item=self.new)
        client = APIClient()
        client.force_authenticate(self.user)
        row = next(row for row in client.get("/api/inventory/").data if row["item"]["id"] == self.new.pk)
        self.assertEqual(row["item"]["effect_summary"], "Open to collect 3 coins.")
        self.assertEqual(client.post(f"/api/inventory/{self.new.pk}/open/").data["coins_awarded"], 3)

    def test_drop_acquisition_hints_follow_new_item_but_authored_promises_keep_old(self):
        DropTable.objects.create(item=self.old, trigger_type="clock_out", weight=1)
        UserInventory.objects.create(user=self.user, item=self.old)
        UserInventory.objects.create(user=self.user, item=self.new)
        definition = QuestDefinition.objects.create(name="Promised pouch", quest_type="collection",
            target_value=1, is_system=True)
        QuestRewardItem.objects.create(quest_definition=definition, item=self.old)
        client = APIClient()
        client.force_authenticate(self.user)
        rows = {row["item"]["id"]: row["item"] for row in client.get("/api/inventory/").data}
        self.assertTrue(any(source["kind"] == "drop" for source in rows[self.new.pk]["acquisition_sources"]))
        self.assertFalse(any(source["kind"] == "drop" for source in rows[self.old.pk]["acquisition_sources"]))
        self.assertTrue(any(source["kind"] == "challenge" for source in rows[self.old.pk]["acquisition_sources"]))

    def test_accepted_quest_fulfills_original_item_and_cannot_repeat(self):
        definition = QuestDefinition.objects.create(name="Accepted pouch", quest_type="collection", target_value=1)
        QuestRewardItem.objects.create(quest_definition=definition, item=self.new)
        quest = Quest.objects.create(definition=definition, end_date=timezone.now() + timedelta(days=1),
            reward_items_snapshot=[{"item_id": self.old.pk, "quantity": 1}])
        QuestParticipant.objects.create(quest=quest, user=self.user)
        QuestService._complete_quest(quest, self.user)
        QuestService._complete_quest(quest, self.user)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.old).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.user, item=self.new).exists())


class ExpeditionCoinPolicyTests(TestCase):
    choose_old = NewRandomCoinPolicyTests.choose_old

    def setUp(self):
        NewRandomCoinPolicyTests.setUp(self)
        species = PetSpecies.objects.create(slug="policy-species", name="Policy companion")
        potion = PotionType.objects.create(slug="policy-potion", name="Policy potion")
        self.mount = UserMount.objects.create(user=self.user, species=species, potion=potion)

    def test_new_trips_have_reduced_bases_and_unchanged_item_slots(self):
        for tier, expected in (("short", 3), ("standard", 7), ("long", 15)):
            with self.subTest(tier=tier), patch("apps.pets.expeditions.random.random", return_value=0.5):
                loot = ExpeditionService._roll_loot(self.user, tier)
                self.assertEqual(loot["coins"], expected)
        from apps.pets.expeditions import TIER_CONFIG
        self.assertEqual([TIER_CONFIG[tier]["item_slots"] for tier in ("short", "standard", "long")], [1, 2, 3])

    def test_new_trip_freezes_reduced_pouch_identity_before_claim(self):
        DropTable.objects.create(item=self.old, trigger_type="clock_out", weight=1)
        with patch("apps.pets.expeditions.random.random", return_value=0.5), patch(
            "apps.pets.expeditions.random.choices", side_effect=self.choose_old,
        ):
            expedition = ExpeditionService.start(self.user, self.mount.pk, "short")
        self.assertEqual(expedition.loot["coins"], 3)
        self.assertEqual(expedition.loot["items"][0]["item_id"], self.new.pk)
        expedition.returns_at = timezone.now() - timedelta(seconds=1)
        expedition.save(update_fields=["returns_at"])
        CharacterProfile.objects.filter(user=self.user).update(
            coin_boost_expires_at=timezone.now() + timedelta(hours=1))
        first = ExpeditionService.claim(self.user, expedition.pk)
        second = ExpeditionService.claim(self.user, expedition.pk)
        self.assertEqual((first["coins_awarded"], second["coins_awarded"]), (6, 0))
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.new).quantity, 1)

    def test_existing_trip_preserves_frozen_coins_items_and_rollback(self):
        expedition = MountExpedition.objects.create(mount=self.mount, tier="long", status="active",
            started_at=timezone.now() - timedelta(hours=9), returns_at=timezone.now() - timedelta(hours=1),
            loot={"coins": 75, "items": [{"item_id": self.old.pk, "quantity": 2}]})
        with patch("apps.rpg.inventory.grant_item", side_effect=RuntimeError("storage failure")):
            with self.assertRaises(RuntimeError):
                ExpeditionService.claim(self.user, expedition.pk)
        expedition.refresh_from_db()
        self.assertEqual(expedition.status, "active")
        self.assertEqual(CoinService.get_balance(self.user), 0)
        result = ExpeditionService.claim(self.user, expedition.pk)
        self.assertEqual(result["coins_awarded"], 75)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.old).quantity, 2)


class CoinPolicyContentTests(TestCase):
    def test_upgrade_rejects_owned_reserved_identity_collision_before_any_writes(self):
        user = make_family("Collision", children=[{"username": "collision-child"}]).children[0]
        ItemDefinition.objects.create(slug="pouch-small", name="Installed small pouch", item_type="coin_pouch",
            rarity="common", coin_value=5, metadata={"coins": 5})
        old = ItemDefinition.objects.create(slug="pouch-medium", name="Installed medium pouch", item_type="coin_pouch",
            rarity="uncommon", coin_value=15, metadata={"coins": 15})
        collision = ItemDefinition.objects.create(slug="pouch-medium-v2", name="Earlier custom promise",
            item_type="coin_pouch", rarity="uncommon", coin_value=500, metadata={"coins": 500})
        UserInventory.objects.create(user=user, item=old, quantity=2)
        UserInventory.objects.create(user=user, item=collision, quantity=3)
        items_before = list(ItemDefinition.objects.order_by("pk").values())
        inventory_before = list(UserInventory.objects.order_by("pk").values())
        migration = import_module("apps.rpg.migrations.0040_random_coin_pouch_versions")
        with self.assertRaisesMessage(ValueError, "Reserved random Coin pouch identity conflicts"):
            migration.add_random_pouches(apps, None)
        self.assertEqual(list(ItemDefinition.objects.order_by("pk").values()), items_before)
        self.assertEqual(list(UserInventory.objects.order_by("pk").values()), inventory_before)

    def test_upgrade_rejects_reserved_identity_collision_even_without_original_source(self):
        ItemDefinition.objects.create(slug="pouch-medium-v2", name="Earlier custom promise",
            item_type="coin_pouch", rarity="uncommon", coin_value=500, metadata={"coins": 500})
        before = list(ItemDefinition.objects.values())
        migration = import_module("apps.rpg.migrations.0040_random_coin_pouch_versions")
        with self.assertRaisesMessage(ValueError, "Reserved random Coin pouch identity conflicts"):
            migration.add_random_pouches(apps, None)
        self.assertEqual(list(ItemDefinition.objects.values()), before)

    def test_upgrade_adds_only_versions_of_installed_pouches_without_touching_owned_work(self):
        user = make_family("Migration", children=[{"username": "migration-child"}]).children[0]
        old = ItemDefinition.objects.create(slug="pouch-mega", name="Saved Mega Hoard",
            item_type="coin_pouch", rarity="legendary", coin_value=500, metadata={"coins": 500})
        UserInventory.objects.create(user=user, item=old, quantity=2)
        before = ItemDefinition.objects.filter(pk=old.pk).values().get()
        migration = import_module("apps.rpg.migrations.0040_random_coin_pouch_versions")
        migration.add_random_pouches(apps, None)
        migration.add_random_pouches(apps, None)
        self.assertEqual(ItemDefinition.objects.filter(pk=old.pk).values().get(), before)
        self.assertEqual(UserInventory.objects.get(user=user, item=old).quantity, 2)
        self.assertEqual(list(ItemDefinition.objects.exclude(pk=old.pk).values_list("slug", flat=True)),
            ["pouch-mega-v2"])

    def test_empty_database_migration_leaves_catalog_initialization_to_startup(self):
        migration = import_module("apps.rpg.migrations.0040_random_coin_pouch_versions")
        migration.add_random_pouches(apps, None)
        self.assertFalse(ItemDefinition.objects.exists())

    def test_bundled_reload_adds_replacements_without_repricing_original_pouches(self):
        call_command("loadrpgcontent", stdout=StringIO())
        original = ItemDefinition.objects.get(slug="pouch-mega")
        call_command("loadrpgcontent", stdout=StringIO())
        original.refresh_from_db()
        self.assertEqual((original.coin_value, original.metadata), (500, {"coins": 500}))
        self.assertTrue(ItemDefinition.objects.filter(slug="pouch-mega-v2").exists())
        replacement = ItemDefinition.objects.get(slug="pouch-mega-v2")
        self.assertEqual((replacement.coin_value, replacement.metadata["coins"]), (100, 100))
        self.assertFalse(DropTable.objects.filter(item=replacement).exists())
