"""Owned Cute Series content uses real RPG identities and lifecycle rules."""
from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import PetService
from apps.pets.tests.helpers import hatch_ready_pet
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


class CuteChickCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        cls.child = make_family("Chick catalog", children=[{"username": "chick-child"}]).children[0]
        cls.chick = PetSpecies.objects.get(slug="chick")
        cls.base = PotionType.objects.get(slug="base")
        cls.fire = PotionType.objects.get(slug="fire")
        cls.egg = ItemDefinition.objects.get(slug="chick-egg")
        cls.base_potion = ItemDefinition.objects.get(slug="base-potion")
        cls.fire_potion = ItemDefinition.objects.get(slug="fire-potion")
        cls.birdseed = ItemDefinition.objects.get(slug="food-birdseed")

    def give(self, item, quantity=1):
        return UserInventory.objects.create(user=self.child, item=item, quantity=quantity)

    def hatch(self):
        self.give(self.egg)
        self.give(self.base_potion)
        return hatch_ready_pet(self.child, self.egg.pk, self.base_potion.pk)

    def test_catalog_wires_ingredients_and_existing_drop_macros(self):
        self.assertEqual(set(self.chick.available_potions.values_list("slug", flat=True)), {"base", "fire", "ice"})
        self.assertEqual(self.egg.pet_species, self.chick)
        self.assertEqual(self.egg.sprite_key, "big-egg")
        self.assertEqual(self.birdseed.food_species, self.chick)
        self.assertEqual(self.chick.food_preference, "birdseed")
        self.assertEqual(self.birdseed.sprite_key, "")
        self.assertTrue(DropTable.objects.filter(item=self.egg, trigger_type="chore_complete").exists())
        self.assertTrue(DropTable.objects.filter(item=self.birdseed, trigger_type="chore_complete").exists())

    def test_stable_total_counts_only_art_supported_authored_variants(self):
        self.assertEqual(PetSpecies.objects.count(), 32)
        self.assertEqual(PetService.get_stable(self.child)["total_possible"], 19)

    def test_unprepared_legacy_species_does_not_expand_available_completion_total(self):
        PetSpecies.objects.create(slug="legacy-bird", name="Legacy Bird", icon="🐦")

        self.assertEqual(PetService.get_stable(self.child)["total_possible"], 19)
        self.assertEqual(self.chick.available_potions.count(), 3)

    def test_reload_keeps_existing_pet_mount_and_inventory(self):
        wolf = PetSpecies.objects.get(slug="wolf")
        pet = UserPet.objects.create(
            user=self.child, species=wolf, potion=self.fire,
            name="Pip", growth_points=100, evolved_to_mount=True,
        )
        mount = UserMount.objects.create(user=self.child, species=wolf, potion=self.fire, is_active=True)
        inventory = self.give(ItemDefinition.objects.get(slug="wolf-egg"), quantity=4)
        pet_before = UserPet.objects.values().get(pk=pet.pk)
        mount_before = UserMount.objects.values().get(pk=mount.pk)
        inventory_before = UserInventory.objects.values().get(pk=inventory.pk)
        species_before = dict(PetSpecies.objects.values_list("slug", "pk"))
        item_ids_before = dict(ItemDefinition.objects.values_list("slug", "pk"))
        drop_count = DropTable.objects.count()

        call_command("loadrpgcontent", stdout=StringIO())
        call_command("loadrpgcontent", stdout=StringIO())

        self.assertEqual(UserPet.objects.values().get(pk=pet.pk), pet_before)
        self.assertEqual(UserMount.objects.values().get(pk=mount.pk), mount_before)
        self.assertEqual(UserInventory.objects.values().get(pk=inventory.pk), inventory_before)
        self.assertEqual(dict(PetSpecies.objects.values_list("slug", "pk")), species_before)
        self.assertEqual(dict(ItemDefinition.objects.values_list("slug", "pk")), item_ids_before)
        self.assertEqual(DropTable.objects.count(), drop_count)
        self.assertEqual(set(self.chick.available_potions.values_list("slug", flat=True)), {"base", "fire", "ice"})

    def test_hatch_base_chick_consumes_one_of_each_ingredient(self):
        egg_inventory = self.give(self.egg, quantity=2)
        potion_inventory = self.give(self.base_potion, quantity=2)

        pet = hatch_ready_pet(self.child, self.egg.pk, self.base_potion.pk)

        self.assertEqual((pet.user, pet.species, pet.potion), (self.child, self.chick, self.base))
        self.assertEqual(pet.growth_points, 0)
        self.assertFalse(pet.is_active)
        egg_inventory.refresh_from_db()
        potion_inventory.refresh_from_db()
        self.assertEqual((egg_inventory.quantity, potion_inventory.quantity), (1, 1))

    def test_owned_chick_endpoints_preserve_exact_identity_through_evolution(self):
        """Real API bodies must carry the identity required by owned 3D bindings."""
        self.give(self.egg)
        self.give(self.base_potion)
        self.give(self.birdseed)
        client = APIClient()
        client.force_authenticate(self.child)

        def assert_chick_identity(body, stage="chick"):
            self.assertEqual(body["species"]["id"], self.chick.pk)
            self.assertEqual(body["species"]["slug"], "chick")
            self.assertEqual(body["species"]["sprite_key"], "cute-chick")
            self.assertEqual(body["potion"]["slug"], "base")
            self.assertEqual(body["evolution_stage"], stage)

        start = client.post("/api/pets/incubations/", {
            "egg_item_id": self.egg.pk,
            "potion_item_id": self.base_potion.pk,
            "request_id": str(uuid4()),
        }, format="json")
        self.assertEqual(start.status_code, 201)
        incubation_id = start.json()["incubation"]["id"]
        PetIncubation.objects.filter(pk=incubation_id).update(ready_at=timezone.now())
        hatch = client.post(f"/api/pets/incubations/{incubation_id}/hatch/", {}, format="json")
        self.assertEqual(hatch.status_code, 201)
        assert_chick_identity(hatch.json()["pet"])
        pet_id = hatch.json()["pet"]["id"]
        activate = client.post(f"/api/pets/{pet_id}/activate/")
        self.assertEqual(activate.status_code, 200)
        assert_chick_identity(activate.json())

        stable = client.get("/api/pets/stable/")
        self.assertEqual(stable.status_code, 200)
        before = stable.json()["pets"][0]
        assert_chick_identity(before)
        self.assertTrue(before["is_active"])
        self.assertFalse(before["evolved_to_mount"])
        UserPet.objects.filter(pk=pet_id).update(growth_points=85)

        feed = client.post(f"/api/pets/{pet_id}/feed/", {
            "food_item_id": self.birdseed.pk,
        }, format="json")
        self.assertEqual(feed.status_code, 200)
        self.assertTrue(feed.json()["evolved"])
        after = client.get("/api/pets/stable/")
        self.assertEqual(after.status_code, 200)
        evolved = after.json()["pets"][0]
        assert_chick_identity(evolved, "bird")
        self.assertEqual(evolved["id"], pet_id)
        self.assertTrue(evolved["evolved_to_mount"])
        mount = after.json()["mounts"][0]
        assert_chick_identity(mount, "bird")
        self.assertEqual(mount["id"], feed.json()["mount_id"])

        mounts = client.get("/api/mounts/")
        self.assertEqual(mounts.status_code, 200)
        assert_chick_identity(mounts.json()[0], "bird")
        activate_mount = client.post(f"/api/mounts/{mount['id']}/activate/")
        self.assertEqual(activate_mount.status_code, 200)
        assert_chick_identity(activate_mount.json(), "bird")

    def test_unsupported_potion_leaves_both_ingredients_intact(self):
        unsupported_potion = ItemDefinition.objects.get(slug="cosmic-potion")
        egg_inventory = self.give(self.egg, quantity=2)
        potion_inventory = self.give(unsupported_potion, quantity=3)

        with self.assertRaisesMessage(ValueError, "Chick cannot hatch with a Cosmic potion"):
            hatch_ready_pet(self.child, self.egg.pk, unsupported_potion.pk)

        egg_inventory.refresh_from_db()
        potion_inventory.refresh_from_db()
        self.assertEqual((egg_inventory.quantity, potion_inventory.quantity), (2, 3))
        self.assertFalse(UserPet.objects.filter(user=self.child, species=self.chick).exists())

    def test_birdseed_feeds_chick_and_evolves_without_changing_species(self):
        pet = self.hatch()
        food_inventory = self.give(self.birdseed, quantity=2)

        first = PetService.feed_pet(self.child, pet.pk, self.birdseed.pk)

        self.assertEqual(first["growth_added"], 15)
        self.assertEqual(first["new_growth"], 15)
        self.assertFalse(first["evolved"])
        food_inventory.refresh_from_db()
        self.assertEqual(food_inventory.quantity, 1)
        pet.growth_points = 90
        pet.save(update_fields=["growth_points"])

        evolved = PetService.feed_pet(self.child, pet.pk, self.birdseed.pk)

        self.assertTrue(evolved["evolved"])
        self.assertEqual(evolved["new_growth"], 100)
        self.assertFalse(UserInventory.objects.filter(pk=food_inventory.pk).exists())
        pet.refresh_from_db()
        self.assertTrue(pet.evolved_to_mount)
        self.assertEqual(pet.species, self.chick)
        mount = UserMount.objects.get(pk=evolved["mount_id"])
        self.assertEqual((mount.user, mount.species, mount.potion), (self.child, self.chick, self.base))

    @override_settings(RPG_ASSET_SUPPORT_POLICY={
        "schema_version": 1,
        "pets": [{"species_slug": "chick", "sprite_key": "cute-chick", "potion_slugs": ["cosmic"]}],
        "potion_slugs": ["cosmic"],
    })
    def test_empty_compatibility_still_allows_an_explicitly_supported_hatch(self):
        self.chick.available_potions.clear()
        cosmic = PotionType.objects.get(slug="cosmic")
        cosmic_item = ItemDefinition.objects.get(slug="cosmic-potion")
        self.give(self.egg)
        self.give(cosmic_item)

        pet = hatch_ready_pet(self.child, self.egg.pk, cosmic_item.pk)

        self.assertEqual((pet.species, pet.potion), (self.chick, cosmic))
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
