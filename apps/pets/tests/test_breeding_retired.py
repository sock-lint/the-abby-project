"""Retired breeding stays unavailable without changing saved companions."""
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.serializers import UserMountSerializer
from apps.pets.services import PetService
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class RetiredBreedingTests(APITestCase):
    def setUp(self):
        self.child = make_family("Retired breeding", children=[{"username": "retired-breeding-child"}]).children[0]
        self.client.force_authenticate(self.child)
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.mounts = []
        for slug, sprite, name in (("chick", "cute-chick", "Chick"), ("meshtint-bat", "meshtint-bat", "Bat")):
            species = PetSpecies.objects.create(slug=slug, sprite_key=sprite, name=name, icon="P")
            species.available_potions.add(self.base)
            egg = ItemDefinition.objects.create(
                slug=f"{slug}-egg", name=f"{name} Egg", item_type="egg",
                pet_species=species, metadata={"species": slug},
            )
            UserInventory.objects.create(user=self.child, item=egg, quantity=2)
            self.mounts.append(UserMount.objects.create(user=self.child, species=species, potion=self.base))
        potion = ItemDefinition.objects.create(
            slug="base-potion", name="Base Potion", item_type="potion",
            potion_type=self.base, metadata={"variant": "base"},
        )
        UserInventory.objects.create(user=self.child, item=potion, quantity=3)

    def saved_state(self):
        return {
            "mounts": list(UserMount.objects.order_by("pk").values()),
            "pets": list(UserPet.objects.order_by("pk").values()),
            "inventory": list(UserInventory.objects.order_by("pk").values()),
            "notifications": list(Notification.objects.order_by("pk").values()),
        }

    def test_supported_ready_parents_never_advertise_breeding(self):
        stable = PetService.get_stable(self.child)
        self.assertFalse(stable["breeding_available"])
        response = self.client.get("/api/pets/stable/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["breeding_available"])
        for mount in response.data["mounts"]:
            self.assertTrue(mount["catalog_available"])
            self.assertIs(mount["can_breed"], False)
            self.assertEqual(mount["breeding_cooldown_seconds"], 0)
            self.assertTrue(mount["expedition_available"])

    def test_retired_post_leaves_inventory_ownership_and_historical_cooldowns_untouched(self):
        historical = timezone.now() - timedelta(days=30)
        UserMount.objects.filter(pk=self.mounts[0].pk).update(last_bred_at=historical)
        before = self.saved_state()
        for body in (
            {"mount_a_id": self.mounts[0].pk, "mount_b_id": self.mounts[1].pk},
            {},
            {"mount_a_id": "invalid", "mount_b_id": 999999},
        ):
            with self.subTest(body=body):
                response = self.client.post("/api/mounts/breed/", body, format="json")
                self.assertEqual(response.status_code, 410)
                self.assertEqual(response.json(), {"error": "Pet breeding has been removed."})
                self.assertEqual(self.saved_state(), before)

    def test_historical_breeding_dates_do_not_enable_or_calculate_a_cooldown(self):
        for historical in (None, timezone.now(), timezone.now() - timedelta(days=30)):
            with self.subTest(last_bred_at=historical):
                self.mounts[0].last_bred_at = historical
                body = UserMountSerializer(self.mounts[0]).data
                self.assertIs(body["can_breed"], False)
                self.assertEqual(body["breeding_cooldown_seconds"], 0)
                self.assertEqual(body["last_bred_at"] is None, historical is None)

    def test_retired_route_still_requires_authentication(self):
        self.client.force_authenticate(None)
        before = self.saved_state()
        response = self.client.post("/api/mounts/breed/", {}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.saved_state(), before)

    def test_mount_list_and_activation_keep_historical_date_but_disable_breeding(self):
        historical = timezone.now() - timedelta(days=2)
        UserMount.objects.filter(pk=self.mounts[0].pk).update(last_bred_at=historical)
        for response in (
            self.client.get("/api/mounts/"),
            self.client.post(f"/api/mounts/{self.mounts[0].pk}/activate/", {}, format="json"),
        ):
            self.assertEqual(response.status_code, 200)
            rows = response.data if isinstance(response.data, list) else [response.data]
            for row in rows:
                self.assertIs(row["can_breed"], False)
                self.assertEqual(row["breeding_cooldown_seconds"], 0)
        self.mounts[0].refresh_from_db()
        self.assertEqual(self.mounts[0].last_bred_at, historical)

    def test_an_active_expedition_is_preserved_when_breeding_is_retired(self):
        now = timezone.now()
        expedition = MountExpedition.objects.create(
            mount=self.mounts[0], tier="short", status="active",
            started_at=now - timedelta(hours=1), returns_at=now + timedelta(hours=1),
            loot={"coins": 15, "items": []},
        )
        before = MountExpedition.objects.values().get(pk=expedition.pk)

        response = self.client.get("/api/pets/stable/")

        self.assertEqual(response.status_code, 200)
        mount = next(row for row in response.data["mounts"] if row["id"] == self.mounts[0].pk)
        self.assertEqual(mount["active_expedition"]["id"], expedition.pk)
        self.assertEqual(mount["active_expedition"]["status"], "active")
        self.assertIs(mount["can_breed"], False)
        self.assertEqual(mount["breeding_cooldown_seconds"], 0)
        self.assertFalse(mount["expedition_available"])
        self.assertEqual(MountExpedition.objects.values().get(pk=expedition.pk), before)
