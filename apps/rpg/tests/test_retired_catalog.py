"""The shipped catalog retires exact unused identities without resetting users."""
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.pets.models import MountExpedition, PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestRewardItem
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import CharacterProfile, ContentPackEntry, DropTable, ItemDefinition, RPGContentOverride, UserInventory
from apps.rpg.retired_catalog import RetiredCatalogCollision, retire_unused_catalog
from config.tests.factories import make_family


class ShippedCatalogRetirementTests(TestCase):
    def test_default_load_only_authors_the_current_roster_and_planned_potions(self):
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(PetSpecies.objects.count(), 15)
        self.assertEqual(set(PotionType.objects.values_list("slug", flat=True)), {"base", "fire", "ice"})
        self.assertFalse(ItemDefinition.objects.filter(item_type="cosmetic_pet_accessory").exists())
        self.assertEqual(set(ItemDefinition.objects.filter(
            item_type="food", food_species__isnull=False,
        ).values_list("slug", flat=True)), {"food-birdseed"})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExistingCatalogRetirementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())
        cls.user = make_family(children=[{"username": "retirement-child"}]).children[0]
        cls.base = PotionType.objects.get(slug="base")
        cls.fire = PotionType.objects.get(slug="fire")
        cls.chick = PetSpecies.objects.get(slug="chick")
        cls.food = ItemDefinition.objects.get(slug="food-birdseed")

    def legacy_catalog(self):
        self.wolf = PetSpecies.objects.create(slug="wolf", name="Wolf", sprite_key="wolf")
        self.shadow = PotionType.objects.create(slug="shadow", name="Shadow")
        self.egg = ItemDefinition.objects.create(
            slug="wolf-egg", name="Wolf Egg", item_type="egg", pet_species=self.wolf, metadata={"species": "wolf"},
        )
        self.potion = ItemDefinition.objects.create(
            slug="shadow-potion", name="Shadow Potion", item_type="potion", potion_type=self.shadow,
        )
        self.accessory = ItemDefinition.objects.create(
            slug="accessory-party-hat", name="Party Hat", item_type="cosmetic_pet_accessory",
        )

    def incubation(self, species, potion, egg):
        now = timezone.now()
        return PetIncubation.objects.create(
            user=self.user, request_id=uuid4(), species=species, potion_type=potion,
            egg_item=egg, accepted_pair={}, started_at=now, ready_at=now, hatched_at=now,
        )

    def offer(self, name, item, kind="digital_item"):
        return Reward.objects.create(
            family=self.user.family, name=name, cost_coins=5, fulfillment_kind=kind, item_definition=item,
        )

    def test_cleanup_removes_obsolete_dependencies_and_keeps_supported_ownership_and_balances(self):
        self.legacy_catalog()
        old_pet = UserPet.objects.create(user=self.user, species=self.wolf, potion=self.base)
        old_mount = UserMount.objects.create(user=self.user, species=self.wolf, potion=self.fire)
        shadow_pet = UserPet.objects.create(user=self.user, species=self.chick, potion=self.shadow)
        kept_pet = UserPet.objects.create(user=self.user, species=self.chick, potion=self.fire, growth_points=45)
        kept_mount = UserMount.objects.create(user=self.user, species=self.chick, potion=self.fire)
        old_incubation = self.incubation(self.wolf, self.base, self.egg)
        shadow_incubation = self.incubation(self.chick, self.shadow, ItemDefinition.objects.get(slug="chick-egg"))
        kept_incubation = self.incubation(self.chick, self.fire, ItemDefinition.objects.get(slug="chick-egg"))
        old_expedition = MountExpedition.objects.create(mount=old_mount, tier="short", returns_at=timezone.now())
        kept_expedition = MountExpedition.objects.create(
            mount=kept_mount, tier="short", returns_at=timezone.now(),
            loot={"coins": 7, "items": [{"item_id": self.egg.pk, "quantity": 1}, {"item_id": self.food.pk, "quantity": 2}]},
        )
        old_offer = self.offer("Old egg offer", self.egg)
        old_redemption = RewardRedemption.objects.create(user=self.user, reward=old_offer, coin_cost_snapshot=5)
        kept_offer = self.offer("Birdseed offer", self.food)
        kept_redemption = RewardRedemption.objects.create(user=self.user, reward=kept_offer, coin_cost_snapshot=5)
        real_world = self.offer("Real-world treat", self.egg, kind="real_world")
        CoinLedger.objects.create(user=self.user, amount=20, reason="adjustment")
        spend = CoinLedger.objects.create(user=self.user, amount=-5, reason="redemption", redemption=old_redemption)
        before_ledger = list(CoinLedger.objects.order_by("pk").values_list("pk", "amount"))
        before_user = type(self.user).objects.values().get(pk=self.user.pk)
        UserInventory.objects.create(user=self.user, item=self.egg, quantity=3)
        safe_inventory = UserInventory.objects.create(user=self.user, item=self.food, quantity=4)
        DropTable.objects.create(trigger_type="clock_out", item=self.egg)
        ItemDefinition.objects.filter(slug="food-meat").update(food_species=self.wolf)
        definition = QuestDefinition.objects.create(name="Retirement snapshot", quest_type="collection", target_value=1)
        old_link = QuestRewardItem.objects.create(quest_definition=definition, item=self.egg)
        kept_link = QuestRewardItem.objects.create(quest_definition=definition, item=self.food)
        quest = Quest.objects.create(definition=definition, end_date=timezone.now(), reward_items_snapshot=[
            {"item_id": self.egg.pk, "quantity": 1}, {"item_id": self.food.pk, "quantity": 2},
        ])
        goal = ChallengeGoal.objects.create(
            user=self.user, family=self.user.family, name="Retirement goal", metric="count", target=3,
            timezone_name="America/Phoenix", starts_at=timezone.now(), ends_at=timezone.now(),
            reward_items=quest.reward_items_snapshot,
        )
        occurrence = ChallengeOccurrence.objects.create(
            goal=goal, starts_at=timezone.now(), ends_at=timezone.now(), progress=2,
            snapshot={"coins": 12, "xp": 8, "items": quest.reward_items_snapshot},
            reward_receipt={"coins": 12, "xp": 8, "items": quest.reward_items_snapshot},
        )
        profile = CharacterProfile.objects.get(user=self.user)
        profile.active_pet_accessory = self.accessory
        profile.pending_companion_growth = [
            {"pet_id": old_pet.pk, "species_slug": "wolf"},
            {"pet_id": kept_pet.pk, "species_slug": "chick", "potion_slug": "fire"},
        ]
        profile.save()
        ownership = ContentPackEntry.objects.create(pack="old-pack", kind="item", key=self.egg.slug,
                                                    model_label="rpg.itemdefinition", object_id=self.egg.pk)
        override = RPGContentOverride.objects.create(model_label="rpg.itemdefinition", object_id=self.egg.pk)

        report = retire_unused_catalog()

        for model, pk in [(UserPet, old_pet.pk), (UserPet, shadow_pet.pk), (UserMount, old_mount.pk),
                          (PetIncubation, old_incubation.pk), (PetIncubation, shadow_incubation.pk),
                          (MountExpedition, old_expedition.pk), (Reward, old_offer.pk),
                          (RewardRedemption, old_redemption.pk), (QuestRewardItem, old_link.pk),
                          (ContentPackEntry, ownership.pk), (RPGContentOverride, override.pk)]:
            with self.subTest(model=model.__name__, pk=pk):
                self.assertFalse(model.objects.filter(pk=pk).exists())
        self.assertEqual(type(self.user).objects.values().get(pk=self.user.pk), before_user)
        self.assertEqual(list(CoinLedger.objects.order_by("pk").values_list("pk", "amount")), before_ledger)
        spend.refresh_from_db()
        self.assertIsNone(spend.redemption_id)
        self.assertTrue(UserPet.objects.filter(pk=kept_pet.pk, growth_points=45).exists())
        self.assertTrue(UserMount.objects.filter(pk=kept_mount.pk).exists())
        self.assertTrue(PetIncubation.objects.filter(pk=kept_incubation.pk).exists())
        self.assertTrue(RewardRedemption.objects.filter(pk=kept_redemption.pk).exists())
        real_world.refresh_from_db()
        self.assertTrue(real_world.is_active)
        self.assertIsNone(real_world.item_definition_id)
        self.assertTrue(UserInventory.objects.filter(pk=safe_inventory.pk, quantity=4).exists())
        self.assertTrue(QuestRewardItem.objects.filter(pk=kept_link.pk).exists())
        self.assertIsNone(ItemDefinition.objects.get(slug="food-meat").food_species_id)
        quest.refresh_from_db()
        self.assertEqual(quest.reward_items_snapshot, [{"item_id": self.food.pk, "quantity": 2}])
        kept_expedition.refresh_from_db()
        self.assertEqual(kept_expedition.loot, {"coins": 7, "items": [{"item_id": self.food.pk, "quantity": 2}]})
        profile.refresh_from_db()
        self.assertIsNone(profile.active_pet_accessory_id)
        self.assertEqual(profile.pending_companion_growth, [{"pet_id": kept_pet.pk, "species_slug": "chick", "potion_slug": "fire"}])
        self.assertEqual(report["quest_snapshot_ids"], [quest.pk])
        self.assertEqual(report["expedition_loot_ids"], [kept_expedition.pk])
        goal.refresh_from_db()
        occurrence.refresh_from_db()
        self.assertEqual(goal.reward_items, [{"item_id": self.food.pk, "quantity": 2}])
        for snapshot in [occurrence.snapshot, occurrence.reward_receipt]:
            self.assertEqual(snapshot, {"coins": 12, "xp": 8, "items": [{"item_id": self.food.pk, "quantity": 2}]})
        self.assertEqual(occurrence.progress, 2)

    def test_supported_frozen_promise_survives_an_offer_that_later_changed_to_a_retired_item(self):
        self.legacy_catalog()
        offer = self.offer("Edited offer", self.food)
        promise = RewardRedemption.objects.create(user=self.user, reward=offer, coin_cost_snapshot=5)
        Reward.objects.filter(pk=offer.pk).update(item_definition=self.egg)
        retire_unused_catalog()
        promise.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(promise.item_definition_snapshot_id, self.food.pk)
        self.assertFalse(offer.is_active)
        self.assertIsNone(offer.item_definition_id)

    def test_exact_optional_accessories_retire_without_deleting_custom_namespaces(self):
        known = ItemDefinition.objects.create(slug="hs-prep-2026-accessory-backpack-charm", name="Lucky Backpack Charm", item_type="cosmetic_pet_accessory")
        custom = ItemDefinition.objects.create(slug="custom-accessory-backpack-charm", name="Lucky Backpack Charm", item_type="cosmetic_pet_accessory")
        arbitrary = PetSpecies.objects.create(slug="custom-fox", name="Custom Fox")
        retire_unused_catalog()
        self.assertFalse(ItemDefinition.objects.filter(pk=known.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=custom.pk).exists())
        self.assertTrue(PetSpecies.objects.filter(pk=arbitrary.pk).exists())
        self.assertEqual(set(PotionType.objects.values_list("slug", flat=True)), {"base", "fire", "ice"})

    def test_operator_dry_run_reports_the_same_cascades_without_writing_and_apply_is_idempotent(self):
        self.legacy_catalog()
        pet = UserPet.objects.create(user=self.user, species=self.wolf, potion=self.base)
        before_species = list(PetSpecies.objects.order_by("pk").values())
        before_items = list(ItemDefinition.objects.order_by("pk").values())
        stdout = StringIO()
        call_command("retire_unused_rpg_content", dry_run=True, json=True, stdout=stdout)
        preview = json.loads(stdout.getvalue())
        self.assertTrue(preview["dry_run"])
        self.assertEqual(preview["pet_ids"], [pet.pk])
        self.assertEqual(preview["deleted"]["pets.UserPet"], 1)
        self.assertEqual(list(PetSpecies.objects.order_by("pk").values()), before_species)
        self.assertEqual(list(ItemDefinition.objects.order_by("pk").values()), before_items)
        applied = retire_unused_catalog()
        self.assertEqual(preview["deleted"], applied["deleted"])
        repeated = retire_unused_catalog()
        self.assertEqual(repeated["deleted"], {})
        self.assertEqual(repeated["items"], [])

    def test_default_reload_retires_existing_rows_without_reseeding_and_dry_run_rolls_back(self):
        self.legacy_catalog()
        call_command("loadrpgcontent", dry_run=True, stdout=StringIO())
        self.assertTrue(PetSpecies.objects.filter(pk=self.wolf.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=self.egg.pk).exists())
        call_command("loadrpgcontent", stdout=StringIO())
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertFalse(PetSpecies.objects.filter(slug="wolf").exists())
        self.assertFalse(ItemDefinition.objects.filter(slug="wolf-egg").exists())
        self.assertEqual(PetSpecies.objects.count(), 15)

    def test_explicit_custom_pack_load_does_not_run_destructive_retirement(self):
        self.legacy_catalog()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "items.yaml").write_text("items:\n  - slug: custom-food\n    name: Custom food\n    item_type: food\n")
            call_command("loadrpgcontent", pack=directory, stdout=StringIO())
        self.assertTrue(PetSpecies.objects.filter(pk=self.wolf.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=self.egg.pk).exists())

    def test_a_later_bundled_load_failure_rolls_back_the_earlier_cleanup(self):
        self.legacy_catalog()
        with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", (("missing-retirement-test-pack", ""),)):
            with self.assertRaisesRegex(CommandError, "Pack directory not found"):
                call_command("loadrpgcontent", stdout=StringIO())
        self.assertTrue(PetSpecies.objects.filter(pk=self.wolf.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=self.egg.pk).exists())
        self.assertTrue(PotionType.objects.filter(pk=self.shadow.pk).exists())

    def test_collision_refuses_default_load_before_any_retirement(self):
        self.legacy_catalog()
        ItemDefinition.objects.filter(pk=self.accessory.pk).update(item_type="food")
        with self.assertRaisesRegex(RetiredCatalogCollision, "different identity"):
            retire_unused_catalog()
        with self.assertRaisesRegex(CommandError, "different identity"):
            call_command("loadrpgcontent", stdout=StringIO())
        self.assertTrue(PetSpecies.objects.filter(pk=self.wolf.pk).exists())
        self.assertTrue(PotionType.objects.filter(pk=self.shadow.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=self.egg.pk).exists())

    def test_replaced_artwork_on_an_old_species_identity_holds_cleanup(self):
        self.legacy_catalog()
        PetSpecies.objects.filter(pk=self.wolf.pk).update(sprite_key="custom-wolf-art")
        with self.assertRaisesRegex(RetiredCatalogCollision, "different artwork"):
            retire_unused_catalog()
        self.assertTrue(PetSpecies.objects.filter(pk=self.wolf.pk).exists())
        self.assertTrue(ItemDefinition.objects.filter(pk=self.egg.pk).exists())
