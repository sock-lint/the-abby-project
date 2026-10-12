"""Every random grant pool observes the prepared-art acquisition policy."""

from unittest.mock import patch

from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.pets.models import PetSpecies, PotionType
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import DropService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class SupportedRandomGrantTests(APITestCase):
    def setUp(self):
        self.child = make_family("Supported grants", children=[{"username": "grant-child"}]).children[0]
        self.fox = PetSpecies.objects.create(slug="fox", name="Fox", sprite_key="fox", icon="F")
        self.fire = PotionType.objects.create(slug="fire", name="Fire")
        self.egg = ItemDefinition.objects.create(name="Unsupported egg", item_type="egg", pet_species=self.fox)
        self.potion = ItemDefinition.objects.create(name="Unsupported potion", item_type="potion", potion_type=self.fire)
        self.accessory = ItemDefinition.objects.create(name="Unsupported hat", item_type="cosmetic_pet_accessory", rarity="uncommon")
        self.food = ItemDefinition.objects.create(name="Berries", item_type="food")
        token = Token.objects.create(user=self.child)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def consumable(self, effect):
        item = ItemDefinition.objects.create(name=effect, item_type="consumable", metadata={"effect": effect})
        inventory = UserInventory.objects.create(user=self.child, item=item, quantity=1)
        return item, inventory

    def test_direct_drops_ignore_unsupported_entries_without_logging_a_reward(self):
        for item in (self.egg, self.potion, self.accessory):
            DropTable.objects.create(trigger_type="clock_out", item=item)
        with patch("apps.rpg.services.random.random", return_value=0):
            self.assertEqual(DropService.process_drops(self.child, "clock_out"), [])
        self.assertFalse(DropLog.objects.exists())
        self.assertFalse(UserInventory.objects.exists())
        DropTable.objects.create(trigger_type="clock_out", item=self.food)
        with patch("apps.rpg.services.random.random", return_value=0):
            result = DropService.process_drops(self.child, "clock_out")
        self.assertEqual(result[0]["item_id"], self.food.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 1)

    def test_mystery_box_pool_never_includes_unprepared_species_or_potions(self):
        item, _inventory = self.consumable("mystery_box")
        response = self.client.post(f"/api/inventory/{item.pk}/use/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"]["granted_item_id"], self.food.pk)
        self.assertFalse(UserInventory.objects.filter(item__in=[self.egg, self.potion, self.accessory]).exists())

    def test_lucky_dip_with_no_supported_cosmetics_does_not_consume_itself(self):
        item, inventory = self.consumable("lucky_dip")
        response = self.client.post(f"/api/inventory/{item.pk}/use/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity, 1)
        self.assertFalse(UserInventory.objects.filter(item=self.accessory).exists())
        title = ItemDefinition.objects.create(name="Useful title", item_type="cosmetic_title", rarity="uncommon", metadata={"text": "Kind"})
        response = self.client.post(f"/api/inventory/{item.pk}/use/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"]["granted_item_id"], title.pk)

    def test_food_basket_retains_its_functional_food_rewards(self):
        item, _inventory = self.consumable("food_basket")
        response = self.client.post(f"/api/inventory/{item.pk}/use/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([entry["item_id"] for entry in response.data["detail"]["granted"]], [self.food.pk, self.food.pk])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 2)

    def test_saved_accessory_is_retained_cannot_be_equipped_and_can_be_unequipped(self):
        entry = UserInventory.objects.create(user=self.child, item=self.accessory, quantity=1)
        profile = CharacterProfile.objects.get(user=self.child)
        profile.active_pet_accessory = self.accessory
        profile.save(update_fields=["active_pet_accessory"])
        updated = profile.updated_at
        response = self.client.post("/api/character/equip/", {"item_id": self.accessory.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        profile.refresh_from_db()
        self.assertEqual(profile.active_pet_accessory_id, self.accessory.pk)
        self.assertEqual(profile.updated_at, updated)
        entry.refresh_from_db()
        self.assertEqual(entry.quantity, 1)
        cosmetics = self.client.get("/api/cosmetics/").data
        self.assertFalse(cosmetics["active_pet_accessory"][0]["catalog_available"])
        catalog = self.client.get("/api/cosmetics/catalog/").data
        self.assertEqual(catalog["active_pet_accessory"], [])
        response = self.client.post("/api/character/unequip/", {"slot": "active_pet_accessory"}, format="json")
        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertIsNone(profile.active_pet_accessory_id)
        self.assertTrue(UserInventory.objects.filter(pk=entry.pk).exists())
