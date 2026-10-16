"""Real current-policy responses, including preserved unsupported ownership."""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None)
class CatalogApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture
    pin_next_mount_identity = shared.SharedApiResponseFixtureTests.pin_next_mount_identity

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.child = make_family("Supported catalog", family_id=31, children=[{"id": 7, "username": "fixture-catalog-child"}]).children[0]
        self.client.force_authenticate(self.child)
        self.base = PotionType.objects.create(id=41, slug="base", name="Base", color_hex="#8B7355")
        self.chick = PetSpecies.objects.create(id=42, slug="chick", name="Chick", icon="C", sprite_key="cute-chick")
        self.chick.available_potions.add(self.base)
        self.cat = PetSpecies.objects.create(id=43, slug="cat", name="Cat", icon="K", sprite_key="cat")
        self.cat.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(id=51, slug="cat-egg", name="Cat Egg", icon="E", item_type="egg", pet_species=self.cat)
        self.potion = ItemDefinition.objects.create(id=52, slug="base-potion", name="Base Potion", icon="P", item_type="potion", potion_type=self.base)
        self.accessory = ItemDefinition.objects.create(id=53, slug="accessory-crown", name="Crown", icon="A", item_type="cosmetic_pet_accessory")
        self.frame = ItemDefinition.objects.create(id=54, slug="frame-gold", name="Gold Frame", icon="G", item_type="cosmetic_frame", metadata={"border_color": "#abcdef"})
        UserPet.objects.create(id=61, user=self.child, species=self.chick, potion=self.base, name="Peep", is_active=True)
        UserPet.objects.create(id=62, user=self.child, species=self.cat, potion=self.base, name="Kit", growth_points=30)
        for pk, item in enumerate((self.egg, self.potion, self.accessory, self.frame), 71):
            UserInventory.objects.create(id=pk, user=self.child, item=item, quantity=1)

    def test_current_catalog_and_preserved_collection_responses(self):
        self.assert_response_fixture(self.client.get("/api/pets/codex/"), "pets-supported-catalog.json")
        self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-preserved-collection.json")
        self.assert_response_fixture(self.client.get("/api/cosmetics/catalog/"), "cosmetics-supported-catalog.json")
        self.assert_response_fixture(self.client.get("/api/inventory/"), "items-preserved-inventory.json")

    def test_bird_stages_retain_saved_species_inventory_and_legacy_collection(self):
        UserPet.objects.filter(pk=61).update(growth_points=35)
        # The older Cat mount stays owned and rendered by its own family.
        UserMount.objects.create(id=61, user=self.child, species=self.cat, potion=self.base)
        self.pin_next_mount_identity()
        food = ItemDefinition.objects.create(
            id=55, slug="food-birdseed", name="Birdseed", item_type="food", food_species=self.chick,
        )
        inventory = UserInventory.objects.create(id=81, user=self.child, item=food, quantity=5)
        fledgling = self.assert_response_fixture(self.client.post(
            "/api/pets/61/feed/", {"food_item_id": food.pk}, format="json",
        ), "pet-feed-fledgling.json")
        self.assertEqual(fledgling["evolution_stage"], "fledgling")
        self.assertFalse(fledgling["evolved"])
        self.assert_response_fixture(
            self.client.get("/api/pets/stable/"), "pets-stable-fledgling.json",
        )
        for _ in range(4):
            grown = self.client.post("/api/pets/61/feed/", {"food_item_id": food.pk}, format="json")
            self.assertEqual(grown.status_code, 200)
        bird = self.assert_response_fixture(grown, "pet-feed-bird.json")
        self.assertEqual(bird["evolution_stage"], "bird")
        self.assertTrue(bird["evolved"])
        stable = self.assert_response_fixture(
            self.client.get("/api/pets/stable/"), "pets-stable-bird.json",
        )
        self.assertEqual({row["id"] for row in stable["pets"]}, {61, 62})
        self.assertEqual({row["id"] for row in stable["mounts"]}, {61, bird["mount_id"]})
        self.assertFalse(UserInventory.objects.filter(pk=inventory.pk).exists())
        # Loading and repeated reads retain the confirmed stage; rendering has no writes.
        before = list(UserPet.objects.filter(user=self.child).values())
        self.assertEqual(self.client.get("/api/pets/stable/").json(), stable)
        self.assertEqual(list(UserPet.objects.filter(user=self.child).values()), before)

    def test_owned_appearance_inventory_routes_to_each_features_editor(self):
        cover = ItemDefinition.objects.create(
            id=55, slug="cover-vigil", name="Night Vigil", icon="T",
            item_type="cosmetic_theme", metadata={"theme": "vigil"},
        )
        UserInventory.objects.filter(user=self.child).exclude(item=self.frame).delete()
        UserInventory.objects.create(id=75, user=self.child, item=cover, quantity=1)
        body = self.assert_response_fixture(self.client.get("/api/inventory/"), "inventory-appearance.json")
        by_type = {row["item"]["item_type"]: row for row in body}
        self.assertEqual(by_type["cosmetic_frame"]["available_actions"][0]["to"], "/sigil")
        self.assertEqual(by_type["cosmetic_theme"]["available_actions"], [{
            "id": "equip", "label": "Change color theme", "to": "/settings#appearance",
        }])

    def test_unavailable_mutations_have_no_consumption_or_loss(self):
        self.assert_response_fixture(self.client.post("/api/pets/hatch/", {"egg_item_id": self.egg.pk, "potion_item_id": self.potion.pk}, format="json"), "pet-hatch-unavailable.json", status=400)
        self.assert_response_fixture(self.client.post("/api/character/equip/", {"item_id": self.accessory.pk}, format="json"), "cosmetic-equip-unavailable.json", status=400)
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 2)
        self.assertEqual(list(UserInventory.objects.filter(user=self.child).values_list("quantity", flat=True)), [1, 1, 1, 1])
