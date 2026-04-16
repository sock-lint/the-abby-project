"""Tests for RPG views — character, inventory, drops, cosmetics."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        CharacterProfile.objects.get_or_create(user=self.child)
        self.client = APIClient()


class CharacterViewTests(_Fixture):
    def test_get_character_profile(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/character/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("level", data)
        self.assertIn("login_streak", data)

    def test_creates_profile_if_missing(self):
        CharacterProfile.objects.filter(user=self.child).delete()
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/character/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(CharacterProfile.objects.filter(user=self.child).exists())


class StreakViewTests(_Fixture):
    def test_get_streaks(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/streaks/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("login_streak", data)
        self.assertIn("longest_login_streak", data)


class InventoryViewTests(_Fixture):
    def test_empty_inventory(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/inventory/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)

    def test_inventory_with_items(self):
        item = ItemDefinition.objects.create(
            name="Sword", icon="⚔️", item_type="cosmetic_frame",
        )
        UserInventory.objects.create(user=self.child, item=item, quantity=2)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/inventory/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["quantity"], 2)


class ItemCatalogTests(_Fixture):
    def test_parent_sees_catalog(self):
        ItemDefinition.objects.create(name="Egg", icon="🥚", item_type="egg")
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/items/catalog/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_child_denied(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/items/catalog/")
        self.assertEqual(resp.status_code, 403)


class RecentDropsTests(_Fixture):
    def test_empty_drops(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/drops/recent/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)


class CosmeticsTests(_Fixture):
    def test_list_cosmetics(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/cosmetics/")
        self.assertEqual(resp.status_code, 200)

    def test_equip_cosmetic(self):
        frame = ItemDefinition.objects.create(
            name="Gold Frame", icon="🖼️", item_type="cosmetic_frame",
        )
        UserInventory.objects.create(user=self.child, item=frame, quantity=1)
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/character/equip/", {
            "item_id": frame.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        profile = CharacterProfile.objects.get(user=self.child)
        self.assertEqual(profile.active_frame, frame)

    def test_unequip_cosmetic(self):
        frame = ItemDefinition.objects.create(
            name="Gold Frame", icon="🖼️", item_type="cosmetic_frame",
        )
        UserInventory.objects.create(user=self.child, item=frame, quantity=1)
        profile = CharacterProfile.objects.get(user=self.child)
        profile.active_frame = frame
        profile.save()
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/character/unequip/", {
            "slot": "active_frame",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        self.assertIsNone(profile.active_frame)

    def test_equip_without_ownership_fails(self):
        frame = ItemDefinition.objects.create(
            name="Rare Frame", icon="🖼️", item_type="cosmetic_frame",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/character/equip/", {
            "item_id": frame.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 400)
