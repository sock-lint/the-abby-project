"""Owned Cute Series content uses real RPG identities and lifecycle rules."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import PetService
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
        return PetService.hatch_pet(self.child, self.egg.pk, self.base_potion.pk)

    def test_catalog_wires_ingredients_and_existing_drop_macros(self):
        self.assertEqual(list(self.chick.available_potions.values_list("slug", flat=True)), ["base"])
        self.assertEqual(self.egg.pet_species, self.chick)
        self.assertEqual(self.egg.sprite_key, "big-egg")
        self.assertEqual(self.birdseed.food_species, self.chick)
        self.assertEqual(self.chick.food_preference, "birdseed")
        self.assertEqual(self.birdseed.sprite_key, "")
        self.assertTrue(DropTable.objects.filter(item=self.egg, trigger_type="chore_complete").exists())
        self.assertTrue(DropTable.objects.filter(item=self.birdseed, trigger_type="chore_complete").exists())

    def test_stable_total_counts_authored_compatible_variants(self):
        self.assertEqual(PetSpecies.objects.count(), 18)
        self.assertEqual(PetService.get_stable(self.child)["total_possible"], 94)

    def test_stable_total_includes_unrestricted_legacy_species(self):
        PetSpecies.objects.create(slug="legacy-bird", name="Legacy Bird", icon="🐦")

        self.assertEqual(PetService.get_stable(self.child)["total_possible"], 100)
        self.assertEqual(self.chick.available_potions.count(), 1)

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
        self.assertEqual(list(self.chick.available_potions.values_list("slug", flat=True)), ["base"])

    def test_hatch_base_chick_consumes_one_of_each_ingredient(self):
        egg_inventory = self.give(self.egg, quantity=2)
        potion_inventory = self.give(self.base_potion, quantity=2)

        pet = PetService.hatch_pet(self.child, self.egg.pk, self.base_potion.pk)

        self.assertEqual((pet.user, pet.species, pet.potion), (self.child, self.chick, self.base))
        self.assertEqual(pet.growth_points, 0)
        self.assertFalse(pet.is_active)
        egg_inventory.refresh_from_db()
        potion_inventory.refresh_from_db()
        self.assertEqual((egg_inventory.quantity, potion_inventory.quantity), (1, 1))

    def test_unsupported_potion_leaves_both_ingredients_intact(self):
        egg_inventory = self.give(self.egg, quantity=2)
        potion_inventory = self.give(self.fire_potion, quantity=3)

        with self.assertRaisesMessage(ValueError, "Chick cannot hatch with a Fire potion"):
            PetService.hatch_pet(self.child, self.egg.pk, self.fire_potion.pk)

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

    def breed_chick_with_fire_wolf(self, *, chick_potion=None, roll=0.5):
        chick_mount = UserMount.objects.create(
            user=self.child, species=self.chick, potion=chick_potion or self.base,
        )
        wolf_mount = UserMount.objects.create(
            user=self.child, species=PetSpecies.objects.get(slug="wolf"), potion=self.fire,
        )
        # Select Chick, then the final potion candidate. An unfiltered
        # parental list would choose Fire and produce an unsupported pair.
        with patch("apps.pets.services.random.random", return_value=roll), patch(
            "apps.pets.services.random.choice",
            side_effect=lambda options: self.chick if isinstance(options[0], PetSpecies) else options[-1],
        ):
            result = PetService.breed_mounts(self.child, chick_mount.pk, wolf_mount.pk)
        return result

    def assert_hatchable_base_chick_breed(self, result):
        self.assertEqual(result["picked_species_slug"], "chick")
        self.assertEqual(result["picked_potion_slug"], "base")
        self.assertFalse(result["chromatic"])
        pet = PetService.hatch_pet(self.child, result["egg_item_id"], result["potion_item_id"])
        self.assertEqual((pet.species, pet.potion), (self.chick, self.base))

    def test_mixed_breed_chooses_compatible_parental_potion(self):
        self.assert_hatchable_base_chick_breed(self.breed_chick_with_fire_wolf())

    def test_chromatic_roll_does_not_grant_unsupported_chick_variant(self):
        self.assert_hatchable_base_chick_breed(self.breed_chick_with_fire_wolf(roll=0.001))

    def test_breed_falls_back_to_registered_compatible_potion_for_legacy_mount(self):
        self.assert_hatchable_base_chick_breed(self.breed_chick_with_fire_wolf(chick_potion=self.fire))

    def test_no_compatible_breeding_item_leaves_inventory_and_cooldowns_unchanged(self):
        self.base_potion.delete()

        with self.assertRaisesMessage(ValueError, "No compatible potion item registered for Chick"):
            self.breed_chick_with_fire_wolf(chick_potion=self.fire)

        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(UserMount.objects.filter(user=self.child, last_bred_at__isnull=False).exists())

    def test_empty_legacy_compatibility_allows_chromatic_breed_and_hatch(self):
        self.chick.available_potions.clear()
        cosmic = PotionType.objects.get(slug="cosmic")

        result = self.breed_chick_with_fire_wolf(roll=0.001)

        self.assertTrue(result["chromatic"])
        self.assertEqual(result["picked_potion_slug"], "cosmic")
        pet = PetService.hatch_pet(self.child, result["egg_item_id"], result["potion_item_id"])
        self.assertEqual((pet.species, pet.potion), (self.chick, cosmic))
