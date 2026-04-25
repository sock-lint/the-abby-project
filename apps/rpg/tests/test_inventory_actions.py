from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.rewards.services import CoinService
from apps.rpg.models import ItemDefinition, UserInventory


class InventoryActionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="c", password="pw", role="child")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_inventory_entries_include_available_actions(self):
        pouch = ItemDefinition.objects.create(
            name="Small Pouch",
            icon="p",
            item_type=ItemDefinition.ItemType.COIN_POUCH,
            metadata={"coins": 5},
        )
        UserInventory.objects.create(user=self.user, item=pouch, quantity=1)

        response = self.client.get("/api/inventory/")

        self.assertEqual(response.status_code, 200)
        actions = response.json()[0]["available_actions"]
        self.assertEqual(actions[0]["id"], "open")
        self.assertEqual(actions[0]["endpoint"], f"/api/inventory/{pouch.pk}/open/")

    def test_open_coin_pouch_awards_coins_and_decrements_inventory(self):
        pouch = ItemDefinition.objects.create(
            name="Small Pouch",
            icon="p",
            item_type=ItemDefinition.ItemType.COIN_POUCH,
            metadata={"coins": 5},
        )
        UserInventory.objects.create(user=self.user, item=pouch, quantity=2)

        response = self.client.post(f"/api/inventory/{pouch.pk}/open/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["coins_awarded"], 5)
        self.assertEqual(CoinService.get_balance(self.user), 5)
        inv = UserInventory.objects.get(user=self.user, item=pouch)
        self.assertEqual(inv.quantity, 1)

    def test_open_non_pouch_returns_400(self):
        food = ItemDefinition.objects.create(
            name="Snack",
            icon="s",
            item_type=ItemDefinition.ItemType.FOOD,
        )
        UserInventory.objects.create(user=self.user, item=food, quantity=1)

        response = self.client.post(f"/api/inventory/{food.pk}/open/")

        self.assertEqual(response.status_code, 400)
