"""The default waits a full day; saved egg deadlines survive later tuning."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserPet
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class DefaultPetIncubationTests(TestCase):
    """Use the configured production default, with no duration override."""

    def setUp(self):
        self.child = make_family("Default egg wait", children=[{"username": "default-egg-child"}]).children[0]
        species = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick", icon="C")
        potion_type = PotionType.objects.create(slug="base", name="Base")
        species.available_potions.add(potion_type)
        self.egg = ItemDefinition.objects.create(slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=species, metadata={"species": "chick"})
        self.potion = ItemDefinition.objects.create(slug="base-potion", name="Base Potion", item_type="potion", potion_type=potion_type, metadata={"variant": "base"})
        for item in (self.egg, self.potion):
            UserInventory.objects.create(user=self.child, item=item, quantity=2)
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        self.now = datetime(2026, 10, 18, 12, tzinfo=dt_timezone.utc)

    def start(self):
        with patch("django.utils.timezone.now", return_value=self.now):
            response = self.client.post("/api/pets/incubations/", {
                "egg_item_id": self.egg.pk, "potion_item_id": self.potion.pk, "request_id": str(uuid4()),
            }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["incubation"]

    def test_new_egg_default_is_24_hours_and_requires_an_explicit_ready_hatch(self):
        row = self.start()
        self.assertEqual(row["remaining_seconds"], 86400)
        self.assertEqual(datetime.fromisoformat(row["ready_at"]) - datetime.fromisoformat(row["started_at"]), timedelta(hours=24))
        path = f"/api/pets/incubations/{row['id']}/hatch/"
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=23, minutes=59, seconds=59)):
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 409)
            current = self.client.get("/api/pets/incubations/").json()
        self.assertEqual(current["duration_seconds"], 86400)
        self.assertEqual(current["incubation"]["remaining_seconds"], 1)
        self.assertFalse(current["incubation"]["is_ready"])
        self.assertFalse(UserPet.objects.exists())
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=24)):
            self.assertEqual(self.client.get("/api/pets/incubations/").json()["incubation"]["status"], "ready")
            self.assertFalse(UserPet.objects.exists())
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 201)
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 1)

    def test_saved_24_hour_deadline_survives_shorter_and_longer_new_egg_settings(self):
        row = self.start()
        saved = PetIncubation.objects.get(pk=row["id"])
        self.assertEqual(saved.ready_at, self.now + timedelta(hours=24))
        path = f"/api/pets/incubations/{row['id']}/hatch/"
        with override_settings(PET_INCUBATION_DURATION_SECONDS=60), patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=2)):
            current = self.client.get("/api/pets/incubations/").json()
            self.assertEqual(current["duration_seconds"], 60)
            self.assertEqual(current["incubation"]["remaining_seconds"], 22 * 3600)
            self.assertEqual(current["incubation"]["ready_at"], row["ready_at"])
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 409)
        with override_settings(PET_INCUBATION_DURATION_SECONDS=172800), patch("django.utils.timezone.now", return_value=saved.ready_at):
            current = self.client.get("/api/pets/incubations/").json()
            self.assertEqual(current["duration_seconds"], 172800)
            self.assertTrue(current["incubation"]["is_ready"])
            self.assertEqual(current["incubation"]["ready_at"], row["ready_at"])
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 201)
        saved.refresh_from_db()
        self.assertEqual(saved.ready_at, self.now + timedelta(hours=24))
        self.assertEqual(list(UserInventory.objects.filter(user=self.child).values_list("quantity", flat=True)), [1, 1])
