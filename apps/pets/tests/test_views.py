"""Tests for pet views — stable, hatch, feed, activate, mounts."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.projects.models import User
from apps.rpg.models import ItemDefinition, UserInventory


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()
        self.species = PetSpecies.objects.create(name="Dragon", icon="🐉")
        self.potion = PotionType.objects.create(name="Fire", color_hex="#FF0000")
        self.egg_item = ItemDefinition.objects.create(
            name="Dragon Egg", icon="🥚", item_type="egg",
            pet_species=self.species,
        )
        self.potion_item = ItemDefinition.objects.create(
            name="Fire Potion", icon="🧪", item_type="potion",
            potion_type=self.potion,
        )
        self.food_item = ItemDefinition.objects.create(
            name="Dragon Food", icon="🍖", item_type="food",
            food_species=self.species,
        )


class StableViewTests(_Fixture):
    def test_empty_stable(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/stable/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_pets"], 0)

    def test_stable_with_pet(self):
        UserPet.objects.create(
            user=self.child, species=self.species, potion=self.potion,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/stable/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total_pets"], 1)


class HatchPetTests(_Fixture):
    def test_hatch_pet_success(self):
        UserInventory.objects.create(user=self.child, item=self.egg_item, quantity=1)
        UserInventory.objects.create(user=self.child, item=self.potion_item, quantity=1)
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/pets/hatch/", {
            "egg_item_id": self.egg_item.pk,
            "potion_item_id": self.potion_item.pk,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(
            UserPet.objects.filter(user=self.child, species=self.species).exists()
        )

    def test_hatch_without_inventory_fails(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/pets/hatch/", {
            "egg_item_id": self.egg_item.pk,
            "potion_item_id": self.potion_item.pk,
        }, format="json")
        self.assertIn(resp.status_code, (400, 409))


class FeedPetTests(_Fixture):
    def test_feed_pet_increases_growth(self):
        pet = UserPet.objects.create(
            user=self.child, species=self.species, potion=self.potion,
            growth_points=10,
        )
        UserInventory.objects.create(user=self.child, item=self.food_item, quantity=1)
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/pets/{pet.pk}/feed/", {
            "food_item_id": self.food_item.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        pet.refresh_from_db()
        self.assertGreater(pet.growth_points, 10)


class ActivatePetTests(_Fixture):
    def test_activate_pet(self):
        pet = UserPet.objects.create(
            user=self.child, species=self.species, potion=self.potion,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/pets/{pet.pk}/activate/")
        self.assertEqual(resp.status_code, 200)
        pet.refresh_from_db()
        self.assertTrue(pet.is_active)

    def test_activate_deactivates_previous(self):
        pet1 = UserPet.objects.create(
            user=self.child, species=self.species, potion=self.potion,
            is_active=True,
        )
        species2 = PetSpecies.objects.create(name="Phoenix", icon="🔥")
        pet2 = UserPet.objects.create(
            user=self.child, species=species2, potion=self.potion,
        )
        self.client.force_authenticate(self.child)
        self.client.post(f"/api/pets/{pet2.pk}/activate/")
        pet1.refresh_from_db()
        pet2.refresh_from_db()
        self.assertFalse(pet1.is_active)
        self.assertTrue(pet2.is_active)


class PetCodexTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.species_b = PetSpecies.objects.create(
            name="Phoenix", icon="🔥", slug="phoenix",
            description="Reborn from ashes.",
        )
        self.potion_b = PotionType.objects.create(name="Ice", color_hex="#00BBFF")
        self.species.available_potions.add(self.potion, self.potion_b)
        self.species_b.available_potions.add(self.potion)

    def test_codex_is_child_readable(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/codex/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("species", data)
        self.assertIn("potions", data)
        self.assertIn("totals", data)

    def test_codex_marks_undiscovered_until_owned(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/codex/")
        species = {s["name"]: s for s in resp.json()["species"]}
        self.assertFalse(species["Dragon"]["discovered"])
        self.assertFalse(species["Phoenix"]["discovered"])
        self.assertEqual(resp.json()["totals"]["discovered_species"], 0)

    def test_codex_discovers_species_after_hatch(self):
        UserPet.objects.create(user=self.child, species=self.species, potion=self.potion)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/codex/")
        species = {s["name"]: s for s in resp.json()["species"]}
        self.assertTrue(species["Dragon"]["discovered"])
        self.assertFalse(species["Phoenix"]["discovered"])
        self.assertEqual(resp.json()["totals"]["discovered_species"], 1)

    def test_codex_owned_mount_potion_ids_match(self):
        UserMount.objects.create(user=self.child, species=self.species, potion=self.potion)
        UserMount.objects.create(user=self.child, species=self.species, potion=self.potion_b)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/codex/")
        dragon = next(s for s in resp.json()["species"] if s["name"] == "Dragon")
        self.assertCountEqual(
            dragon["owned_mount_potion_ids"],
            [self.potion.id, self.potion_b.id],
        )
        self.assertEqual(resp.json()["totals"]["mounts_owned"], 2)

    def test_codex_excludes_other_users_data(self):
        UserPet.objects.create(user=self.parent, species=self.species, potion=self.potion)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/codex/")
        dragon = next(s for s in resp.json()["species"] if s["name"] == "Dragon")
        self.assertFalse(dragon["discovered"])

    def test_codex_includes_available_potions(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/pets/codex/")
        dragon = next(s for s in resp.json()["species"] if s["name"] == "Dragon")
        potion_ids = {p["id"] for p in dragon["available_potions"]}
        self.assertEqual(potion_ids, {self.potion.id, self.potion_b.id})


class MountsTests(_Fixture):
    def test_list_mounts(self):
        UserMount.objects.create(
            user=self.child, species=self.species, potion=self.potion,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/mounts/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_activate_mount(self):
        mount = UserMount.objects.create(
            user=self.child, species=self.species, potion=self.potion,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/mounts/{mount.pk}/activate/")
        self.assertEqual(resp.status_code, 200)
        mount.refresh_from_db()
        self.assertTrue(mount.is_active)
