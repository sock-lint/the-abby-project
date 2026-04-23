"""Tests for GET /api/cosmetics/catalog/ — the child-accessible cosmetic catalog."""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.rpg.models import ItemDefinition


class CosmeticCatalogViewTests(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.client = APIClient()

        self.frame = ItemDefinition.objects.create(
            name="Bronze Frame",
            icon="\U0001f7eb",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=5,
        )
        self.title = ItemDefinition.objects.create(
            name="Apprentice",
            icon="\U0001f393",
            item_type=ItemDefinition.ItemType.COSMETIC_TITLE,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=5,
        )
        self.theme = ItemDefinition.objects.create(
            name="Ocean Theme",
            icon="\U0001f30a",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.UNCOMMON,
            coin_value=20,
        )
        self.accessory = ItemDefinition.objects.create(
            name="Saddle",
            icon="\U0001fa7a",
            item_type=ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
            rarity=ItemDefinition.Rarity.RARE,
            coin_value=40,
        )
        # Non-cosmetic content should NOT appear in the response.
        self.egg = ItemDefinition.objects.create(
            name="Dragon Egg",
            icon="\U0001f95a",
            item_type=ItemDefinition.ItemType.EGG,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=10,
        )

    def test_requires_auth(self):
        resp = self.client.get(reverse("cosmetics-catalog"))
        self.assertIn(resp.status_code, (401, 403))

    def test_child_can_browse_catalog(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get(reverse("cosmetics-catalog"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(
            set(body.keys()),
            {"active_frame", "active_title", "active_theme", "active_pet_accessory"},
        )
        self.assertEqual([x["id"] for x in body["active_frame"]], [self.frame.id])
        self.assertEqual([x["id"] for x in body["active_title"]], [self.title.id])
        self.assertEqual([x["id"] for x in body["active_theme"]], [self.theme.id])
        self.assertEqual(
            [x["id"] for x in body["active_pet_accessory"]], [self.accessory.id],
        )

    def test_non_cosmetic_items_are_excluded(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get(reverse("cosmetics-catalog"))
        ids_in_response = {
            item["id"]
            for slot_items in resp.json().values()
            for item in slot_items
        }
        self.assertNotIn(self.egg.id, ids_in_response)

    def test_parent_also_has_access(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(reverse("cosmetics-catalog"))
        self.assertEqual(resp.status_code, 200)
