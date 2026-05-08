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


class BulkConsumableUseTests(TestCase):
    """Quantity > 1 path — stack-safe effects loop, stack-unsafe reject."""

    def setUp(self):
        self.user = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _make_item(self, slug, effect, qty=5, **meta):
        item = ItemDefinition.objects.create(
            slug=slug, name=slug, icon="🧪",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": effect, **meta},
        )
        UserInventory.objects.create(user=self.user, item=item, quantity=qty)
        return item

    def test_stack_safe_growth_tonic_applies_n_times(self):
        item = self._make_item("growth-tonic-test", "growth_tonic", feeds=2)
        resp = self.client.post(
            f"/api/inventory/{item.pk}/use/", {"quantity": 3}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["quantity_used"], 3)
        self.assertEqual(len(body["details"]), 3)
        # 3 × 2 feeds each = 6 stacked.
        from apps.rpg.models import CharacterProfile
        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.pet_growth_boost_remaining, 6)

        inv = UserInventory.objects.get(user=self.user, item=item)
        self.assertEqual(inv.quantity, 2)

    def test_stack_unsafe_xp_boost_rejects_quantity_above_one(self):
        item = self._make_item("xp-boost-test", "xp_boost", duration_hours=1)
        resp = self.client.post(
            f"/api/inventory/{item.pk}/use/", {"quantity": 2}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        # Inventory unchanged — atomic.
        inv = UserInventory.objects.get(user=self.user, item=item)
        self.assertEqual(inv.quantity, 5)

    def test_stack_unsafe_streak_freeze_rejects_quantity_above_one(self):
        item = self._make_item("freeze-test", "streak_freeze")
        resp = self.client.post(
            f"/api/inventory/{item.pk}/use/", {"quantity": 3}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_quantity_one_remains_default_behaviour(self):
        item = self._make_item("xp-boost-default", "xp_boost", duration_hours=1)
        resp = self.client.post(f"/api/inventory/{item.pk}/use/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["quantity_used"], 1)
        # Single-use call sites still get ``detail`` for back-compat.
        self.assertIn("detail", body)

    def test_quantity_exceeds_owned_returns_400(self):
        item = self._make_item("growth-tonic-low", "growth_tonic", qty=2)
        resp = self.client.post(
            f"/api/inventory/{item.pk}/use/", {"quantity": 3}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        # Nothing consumed.
        inv = UserInventory.objects.get(user=self.user, item=item)
        self.assertEqual(inv.quantity, 2)

    def test_quantity_zero_or_negative_returns_400(self):
        item = self._make_item("growth-tonic-test", "growth_tonic")
        for q in (0, -1, "abc"):
            resp = self.client.post(
                f"/api/inventory/{item.pk}/use/", {"quantity": q}, format="json",
            )
            self.assertEqual(resp.status_code, 400, f"quantity={q!r}")
