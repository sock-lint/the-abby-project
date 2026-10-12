"""Server-confirmed mount breeding cooldowns exposed to every client."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.pets.serializers import UserMountSerializer
from apps.pets.services import MOUNT_BREEDING_COOLDOWN_DAYS
from apps.projects.models import User


NOW = datetime(2026, 10, 10, 19, 0, tzinfo=datetime_timezone.utc)


@override_settings(
    TIME_ZONE="America/Phoenix",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class MountBreedingEligibilitySerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="breeding-fixture-child", role="child")
        self.species = PetSpecies.objects.create(name="Fixture Fox", slug="fixture-fox")
        self.potion = PotionType.objects.create(name="Fixture Ice", slug="fixture-ice")
        self.mount = UserMount.objects.create(user=self.user, species=self.species, potion=self.potion)

    def test_cooldown_rounds_up_and_expires_at_the_exact_server_boundary(self):
        cooldown = timedelta(days=MOUNT_BREEDING_COOLDOWN_DAYS)
        for last_bred_at, expected_seconds in (
            (None, 0),
            (NOW - cooldown - timedelta(microseconds=1), 0),
            (NOW - cooldown, 0),
            (NOW - cooldown + timedelta(microseconds=1), 1),
            (NOW - cooldown + timedelta(seconds=1, microseconds=100000), 2),
            (NOW + timedelta(seconds=1), int(cooldown.total_seconds()) + 1),
        ):
            with self.subTest(last_bred_at=last_bred_at), patch("django.utils.timezone.now", return_value=NOW):
                self.mount.last_bred_at = last_bred_at
                body = UserMountSerializer(self.mount).data
                self.assertIs(type(body["breeding_cooldown_seconds"]), int)
                self.assertIs(type(body["can_breed"]), bool)
                self.assertEqual(body["breeding_cooldown_seconds"], expected_seconds)
                self.assertEqual(body["can_breed"], expected_seconds == 0)

    def test_eligibility_fields_keep_one_snapshot_when_the_deadline_passes_during_serialization(self):
        self.mount.last_bred_at = NOW - timedelta(days=MOUNT_BREEDING_COOLDOWN_DAYS)
        instants = iter((NOW - timedelta(microseconds=500000), NOW + timedelta(microseconds=500000)))
        with patch("django.utils.timezone.now", side_effect=lambda: next(instants, NOW + timedelta(seconds=1))):
            body = UserMountSerializer(self.mount).data
        self.assertFalse(body["can_breed"])
        self.assertEqual(body["breeding_cooldown_seconds"], 1)

    def test_an_away_mount_retains_the_existing_cooldown_only_eligibility(self):
        expedition = MountExpedition.objects.create(
            mount=self.mount, tier="short", status="active",
            started_at=NOW - timedelta(hours=1), returns_at=NOW + timedelta(hours=1),
            loot={"coins": 15, "items": []},
        )
        self.mount.prefetched_active_expeditions = [expedition]
        with patch("django.utils.timezone.now", return_value=NOW):
            body = UserMountSerializer(self.mount).data
        self.assertEqual(body["active_expedition"]["id"], expedition.pk)
        self.assertEqual(body["active_expedition"]["status"], "active")
        self.assertTrue(body["can_breed"])
        self.assertEqual(body["breeding_cooldown_seconds"], 0)
        expedition.refresh_from_db()
        self.assertEqual(expedition.status, "active")

    def test_client_supplied_eligibility_cannot_change_the_server_cooldown(self):
        self.mount.last_bred_at = NOW
        serializer = UserMountSerializer(self.mount, data={"can_breed": True, "breeding_cooldown_seconds": 0})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {})
        with patch("django.utils.timezone.now", return_value=NOW):
            body = serializer.data
        self.assertFalse(body["can_breed"])
        self.assertEqual(body["breeding_cooldown_seconds"], MOUNT_BREEDING_COOLDOWN_DAYS * 86400)
