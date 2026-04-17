"""Tests for POST /api/inventory/<item_id>/use/."""
from __future__ import annotations

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.rpg.models import ItemDefinition, UserInventory


class UseConsumableViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="c", password="pw", role="child")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.item = ItemDefinition.objects.create(
            slug="streak-freeze-test",
            name="Streak Freeze",
            icon="❄️",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "streak_freeze", "duration_days": 1},
        )
        UserInventory.objects.create(user=self.user, item=self.item, quantity=2)

    def test_uses_consumable_and_decrements_inventory(self):
        response = self.client.post(f"/api/inventory/{self.item.pk}/use/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["effect"], "streak_freeze")

        inv = UserInventory.objects.get(user=self.user, item=self.item)
        self.assertEqual(inv.quantity, 1)

    def test_unowned_item_returns_400(self):
        other_item = ItemDefinition.objects.create(
            name="Other", icon="x",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "streak_freeze"},
        )
        response = self.client.post(f"/api/inventory/{other_item.pk}/use/")
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_returns_401(self):
        anon = APIClient()
        response = anon.post(f"/api/inventory/{self.item.pk}/use/")
        self.assertIn(response.status_code, (401, 403))
