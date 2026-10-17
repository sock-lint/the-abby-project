"""Real PostgreSQL acceptance for competing supported pet acquisitions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class SupportedPetConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family("Supported concurrent pets", children=[{"username": "concurrent-pet-child"}]).children[0]
        self.chick = PetSpecies.objects.create(slug="chick", sprite_key="cute-chick", name="Chick", icon="C")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.chick.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(slug="chick-egg", name="Chick egg", item_type="egg", pet_species=self.chick, metadata={"species": "chick"})
        self.potion = ItemDefinition.objects.create(slug="base-potion", name="Base potion", item_type="potion", potion_type=self.base, metadata={"variant": "base"})
        self.food = ItemDefinition.objects.create(name="Birdseed", item_type="food", food_species=self.chick)

    def post(self, path, body, start):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
            client = APIClient()
            client.force_authenticate(self.child)
            start.wait(timeout=5)
            response = client.post(path, body, format="json")
            return response.status_code, response.json()
        finally:
            connection.close()

    def competing_posts(self, path, body):
        start = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.post, path, body, start) for _ in range(2)]
            return [future.result(timeout=15) for future in futures]

    def test_two_same_companion_hatches_create_one_pet_and_consume_one_pair(self):
        for item in (self.egg, self.potion):
            UserInventory.objects.create(user=self.child, item=item, quantity=2)
        results = self.competing_posts("/api/pets/hatch/", {
            "egg_item_id": self.egg.pk, "potion_item_id": self.potion.pk,
        })
        self.assertEqual(sorted(status for status, _ in results), [201, 400])
        self.assertEqual(UserPet.objects.filter(user=self.child, species=self.chick, potion=self.base).count(), 1)
        for item in (self.egg, self.potion):
            self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)
        success = next(body for status, body in results if status == 201)
        self.assertTrue(success["catalog_available"])
        self.assertEqual(success["growth_points"], 0)

    def test_competing_final_feeds_consume_once_and_create_one_confirmed_mount(self):
        pet = UserPet.objects.create(user=self.child, species=self.chick, potion=self.base, growth_points=85)
        inventory = UserInventory.objects.create(user=self.child, item=self.food, quantity=1)
        results = self.competing_posts(f"/api/pets/{pet.pk}/feed/", {"food_item_id": self.food.pk})
        self.assertEqual(sorted(status for status, _ in results), [200, 400])
        pet.refresh_from_db()
        self.assertEqual(pet.growth_points, 100)
        self.assertTrue(pet.evolved_to_mount)
        self.assertFalse(UserInventory.objects.filter(pk=inventory.pk).exists())
        self.assertEqual(UserMount.objects.filter(user=self.child, species=self.chick, potion=self.base).count(), 1)
        success = next(body for status, body in results if status == 200)
        self.assertTrue(success["evolved"])
        self.assertEqual(success["mount_id"], UserMount.objects.get(user=self.child).pk)
