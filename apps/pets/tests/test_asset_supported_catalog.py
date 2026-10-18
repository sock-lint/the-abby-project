"""New acquisitions use prepared art; saved companions remain fully owned."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount, UserPet
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class AssetSupportedAcquisitionTests(APITestCase):
    def setUp(self):
        household = make_family("Supported art", parents=[{"username": "art-parent"}],
                                children=[{"username": "art-child"}, {"username": "art-sibling"}])
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick", icon="C")
        self.fox = PetSpecies.objects.create(slug="fox", name="Fox", sprite_key="fox", icon="F")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.fire = PotionType.objects.create(slug="fire", name="Fire")
        self.chick.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(slug="chick-egg", name="Chick egg", item_type="egg", pet_species=self.chick, metadata={"species": "chick"})
        self.old_egg = ItemDefinition.objects.create(slug="fox-egg", name="Fox egg", item_type="egg", pet_species=self.fox)
        self.potion = ItemDefinition.objects.create(slug="base-potion", name="Base potion", item_type="potion", potion_type=self.base, metadata={"variant": "base"})
        self.old_potion = ItemDefinition.objects.create(slug="fire-potion", name="Fire potion", item_type="potion", potion_type=self.fire)
        self.food = ItemDefinition.objects.create(slug="food-birdseed", name="Birdseed", item_type="food", food_species=self.chick)
        self.accessory = ItemDefinition.objects.create(slug="accessory-party-hat", name="Party hat", item_type="cosmetic_pet_accessory", coin_value=0)
        token = Token.objects.create(user=self.child)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def give(self, item, count=2):
        return UserInventory.objects.create(user=self.child, item=item, quantity=count)

    def state(self):
        return {
            "pets": list(UserPet.objects.order_by("id").values()),
            "mounts": list(UserMount.objects.order_by("id").values()),
            "inventory": list(UserInventory.objects.order_by("id").values()),
            "profiles": list(CharacterProfile.objects.order_by("id").values()),
            "drops": list(DropLog.objects.order_by("id").values()),
        }

    def test_hatch_rejects_saved_unsupported_ingredients_before_consuming_anything(self):
        for item in (self.egg, self.old_egg, self.potion, self.old_potion):
            self.give(item)
        before = self.state()
        for egg, potion in ((self.old_egg, self.potion), (self.egg, self.old_potion), (self.old_egg, self.old_potion)):
            response = self.client.post("/api/pets/hatch/", {"egg_item_id": egg.pk, "potion_item_id": potion.pk}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.state(), before)
        response = self.client.post("/api/pets/hatch/", {"egg_item_id": self.egg.pk, "potion_item_id": self.potion.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["catalog_available"])
        self.assertTrue(response.data["species"]["catalog_available"])
        self.assertTrue(response.data["potion"]["catalog_available"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.egg).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.potion).quantity, 1)

    def test_catalog_only_offers_supported_variants_but_stable_and_inventory_retain_legacy_ownership(self):
        chick = UserPet.objects.create(user=self.child, species=self.chick, potion=self.base, is_active=True)
        old = UserPet.objects.create(user=self.child, species=self.fox, potion=self.fire)
        saved = UserMount.objects.create(user=self.child, species=self.fox, potion=self.fire)
        for item in (self.egg, self.old_egg, self.potion, self.old_potion, self.accessory, self.food):
            self.give(item)
        stable = self.client.get("/api/pets/stable/").data
        self.assertEqual({row["id"] for row in stable["pets"]}, {chick.pk, old.pk})
        self.assertEqual({row["id"] for row in stable["mounts"]}, {saved.pk})
        self.assertEqual({row["id"]: row["catalog_available"] for row in stable["pets"]}, {chick.pk: True, old.pk: False})
        self.assertFalse(stable["mounts"][0]["catalog_available"])
        self.assertFalse(stable["mounts"][0]["can_breed"])
        self.assertFalse(stable["breeding_available"])
        self.assertEqual(stable["total_possible"], 1)
        inventory = self.client.get("/api/inventory/").data
        self.assertEqual(len(inventory), 6)
        flags = {row["item"]["id"]: row["item"]["catalog_available"] for row in inventory}
        self.assertEqual(flags, {self.egg.pk: True, self.old_egg.pk: False, self.potion.pk: True,
                                 self.old_potion.pk: False, self.accessory.pk: False, self.food.pk: True})
        self.assertTrue(all(row["available_actions"] == [] for row in inventory if not row["item"]["catalog_available"]))
        codex = self.client.get("/api/pets/codex/").data
        self.assertEqual([row["slug"] for row in codex["species"]], ["chick"])
        self.assertEqual([row["slug"] for row in codex["potions"]], ["base"])
        self.assertEqual([row["name"] for row in codex["species"][0]["available_potions"]], ["Base"])
        self.assertEqual(codex["totals"]["mounts_owned"], 0)

    def test_an_unsupported_owned_chick_variant_does_not_claim_the_supported_codex_entry(self):
        UserPet.objects.create(user=self.child, species=self.chick, potion=self.fire)
        UserMount.objects.create(user=self.child, species=self.chick, potion=self.fire)
        codex = self.client.get("/api/pets/codex/").data
        self.assertFalse(codex["species"][0]["discovered"])
        self.assertEqual(codex["species"][0]["owned_pet_ids"], [])
        self.assertEqual(codex["species"][0]["owned_mount_potion_ids"], [])

    def test_saved_unsupported_pet_can_still_feed_evolve_activate_and_explore(self):
        pet = UserPet.objects.create(user=self.child, species=self.fox, potion=self.fire, growth_points=95)
        self.give(self.food)
        response = self.client.post(f"/api/pets/{pet.pk}/feed/", {"food_item_id": self.food.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["evolved"])
        mount = UserMount.objects.get(pk=response.data["mount_id"])
        self.assertEqual(mount.species_id, self.fox.pk)
        self.assertEqual(self.client.post(f"/api/pets/{pet.pk}/activate/", {}, format="json").status_code, 200)
        active = self.client.post(f"/api/mounts/{mount.pk}/activate/", {}, format="json")
        self.assertEqual(active.status_code, 200)
        self.assertFalse(active.data["catalog_available"])
        self.assertFalse(active.data["can_breed"])
        self.assertEqual(self.client.post(f"/api/mounts/{mount.pk}/expedition/", {"tier": "short"}, format="json").status_code, 201)

    def test_legacy_mount_breeding_is_rejected_without_cooldowns_or_item_changes(self):
        first = UserMount.objects.create(user=self.child, species=self.chick, potion=self.base)
        second = UserMount.objects.create(user=self.child, species=self.fox, potion=self.fire)
        before = self.state()
        response = self.client.post("/api/mounts/breed/", {"mount_a_id": first.pk, "mount_b_id": second.pk}, format="json")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json(), {"error": "Pet breeding has been removed."})
        self.assertEqual(self.state(), before)
        self.assertFalse(self.client.get("/api/pets/stable/").data["breeding_available"])

    def test_new_expedition_loot_filters_unsupported_tables_but_honors_previously_locked_loot(self):
        mount = UserMount.objects.create(user=self.child, species=self.fox, potion=self.fire)
        DropTable.objects.create(trigger_type="expedition_returned", item=self.accessory)
        DropTable.objects.create(trigger_type="clock_out", item=self.food)
        loot = ExpeditionService._roll_loot(self.child, "short")
        self.assertEqual([item["item_id"] for item in loot["items"]], [self.food.pk])
        now = timezone.now()
        locked = MountExpedition.objects.create(mount=mount, tier="short", status="active",
            started_at=now - timedelta(hours=3), returns_at=now - timedelta(hours=1),
            loot={"coins": 15, "items": [{"item_id": self.accessory.pk, "quantity": 1, "name": self.accessory.name, "icon": "H", "rarity": "common", "item_type": "cosmetic_pet_accessory", "sprite_key": "hat"}]})
        response = self.client.post(f"/api/expeditions/{locked.pk}/claim/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["freshly_claimed"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.accessory).quantity, 1)
        repeated = self.client.post(f"/api/expeditions/{locked.pk}/claim/", {}, format="json")
        self.assertFalse(repeated.data["freshly_claimed"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.accessory).quantity, 1)
