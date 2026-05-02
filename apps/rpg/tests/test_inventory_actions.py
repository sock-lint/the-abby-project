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


class AvailableActionsByItemTypeTests(TestCase):
    """Pin the per-item-type action mapping in
    ``UserInventorySerializer.get_available_actions``.

    The frontend Inventory + Satchel pages branch on these action shapes
    (``id``, plus either ``endpoint`` for a same-page POST or ``to`` for a
    SPA route hand-off). A serializer change that drops a branch would
    silently break every Inventory tile of that type — these tests are
    the cheap pin against that.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="c", password="pw", role="child")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _entry_for(self, item_type, **extra):
        item = ItemDefinition.objects.create(
            name=f"Test {item_type}",
            icon="i",
            item_type=item_type,
            **extra,
        )
        UserInventory.objects.create(user=self.user, item=item, quantity=1)
        return item

    def _actions_for(self, item):
        response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 200)
        for entry in response.json():
            if entry["item"]["id"] == item.pk:
                return entry["available_actions"]
        self.fail(f"item {item.pk} not present in inventory response")

    def test_consumable_offers_use_action(self):
        item = self._entry_for(
            ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "streak_freeze", "duration_days": 1},
        )
        actions = self._actions_for(item)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "use")
        self.assertEqual(actions[0]["endpoint"], f"/api/inventory/{item.pk}/use/")

    def test_coin_pouch_offers_open_action(self):
        item = self._entry_for(
            ItemDefinition.ItemType.COIN_POUCH,
            metadata={"coins": 5},
        )
        actions = self._actions_for(item)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "open")
        self.assertEqual(actions[0]["endpoint"], f"/api/inventory/{item.pk}/open/")

    def test_egg_routes_to_hatchery(self):
        item = self._entry_for(ItemDefinition.ItemType.EGG)
        actions = self._actions_for(item)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "hatch")
        self.assertEqual(actions[0]["to"], "/bestiary?tab=hatchery")

    def test_potion_routes_to_hatchery(self):
        item = self._entry_for(ItemDefinition.ItemType.POTION)
        actions = self._actions_for(item)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "hatch")
        self.assertEqual(actions[0]["to"], "/bestiary?tab=hatchery")

    def test_food_routes_to_companions(self):
        item = self._entry_for(ItemDefinition.ItemType.FOOD)
        actions = self._actions_for(item)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "feed")
        self.assertEqual(actions[0]["to"], "/bestiary?tab=companions")

    def test_quest_scroll_routes_to_trials_with_scroll_id(self):
        item = self._entry_for(ItemDefinition.ItemType.QUEST_SCROLL)
        actions = self._actions_for(item)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "start_quest")
        self.assertEqual(actions[0]["to"], f"/trials?scroll_item={item.pk}")

    def test_each_cosmetic_slot_routes_to_sigil_for_equip(self):
        # All four cosmetic slots share the same equip action — the slot
        # itself is dispatched server-side by ``CosmeticService.equip`` based
        # on the item's ``item_type``.
        for slot in (
            ItemDefinition.ItemType.COSMETIC_FRAME,
            ItemDefinition.ItemType.COSMETIC_TITLE,
            ItemDefinition.ItemType.COSMETIC_THEME,
            ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
        ):
            with self.subTest(slot=slot):
                item = self._entry_for(slot)
                actions = self._actions_for(item)
                self.assertEqual(len(actions), 1)
                self.assertEqual(actions[0]["id"], "equip")
                self.assertEqual(actions[0]["to"], "/sigil")


class UseConsumableViewTests(TestCase):
    """Pin inventory state transitions for the consumable use endpoint.

    The effect dispatch (timer-gated boosts, streak freeze, etc.) is
    pinned by ``apps.rpg.tests.test_boost_multipliers`` and
    ``test_new_consumable_effects``. This class only asserts the shared
    inventory-decrement contract that wraps every effect — if it
    regresses, a child can use a consumable forever.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="c", password="pw", role="child")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_use_consumable_decrements_inventory(self):
        # streak_freeze is the simplest effect to assert against — it only
        # writes a date field on CharacterProfile and doesn't depend on
        # external content packs (boost effects need timer windows, etc.).
        item = ItemDefinition.objects.create(
            name="Streak Freeze",
            icon="❄",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "streak_freeze", "duration_days": 1},
        )
        UserInventory.objects.create(user=self.user, item=item, quantity=2)

        response = self.client.post(f"/api/inventory/{item.pk}/use/")

        self.assertEqual(response.status_code, 200, response.content)
        inv = UserInventory.objects.get(user=self.user, item=item)
        self.assertEqual(inv.quantity, 1, "use must decrement inventory by 1")

    def test_use_when_quantity_zero_returns_400(self):
        item = ItemDefinition.objects.create(
            name="Streak Freeze",
            icon="❄",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "streak_freeze", "duration_days": 1},
        )
        UserInventory.objects.create(user=self.user, item=item, quantity=0)

        response = self.client.post(f"/api/inventory/{item.pk}/use/")

        self.assertEqual(response.status_code, 400)
