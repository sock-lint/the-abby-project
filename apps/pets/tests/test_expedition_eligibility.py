"""Daily expedition presentation follows the same clock and owner as start."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.expeditions import ExpeditionError, ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.pets.serializers import UserMountSerializer
from config.tests.factories import make_family


NOW = datetime(2026, 10, 11, 10, 59, 59, tzinfo=datetime_timezone.utc)
MIDNIGHT = datetime(2026, 10, 11, 11, 0, tzinfo=datetime_timezone.utc)
SERVER_MIDNIGHT = datetime(2026, 10, 11, 7, 0, tzinfo=datetime_timezone.utc)


@override_settings(TIME_ZONE="America/Phoenix", USE_TZ=True)
class ExpeditionEligibilityTests(TestCase):
    def setUp(self):
        household = make_family("Daily adventure", children=[{"username": "daily-child"}, {"username": "daily-sibling"}])
        self.user, self.sibling = household.children
        # Family midnight differs from the server's response display timezone.
        household.family.timezone = "Pacific/Auckland"
        household.family.save(update_fields=["timezone"])
        self.species = PetSpecies.objects.create(name="Chick", slug="chick", sprite_key="cute-chick")
        self.potion = PotionType.objects.create(name="Base", slug="base")
        self.mount = UserMount.objects.create(user=self.user, species=self.species, potion=self.potion)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def trip(self, *, status="claimed", started_at=None, mount=None):
        return MountExpedition.objects.create(
            mount=mount or self.mount, tier="short", status=status,
            started_at=started_at or NOW - timedelta(hours=3),
            returns_at=NOW - timedelta(hours=1), loot={"coins": 15, "items": []},
        )

    def body(self, now=NOW):
        with patch("django.utils.timezone.now", return_value=now):
            return UserMountSerializer(self.mount).data

    def test_ready_for_first_trip_without_writing_rewards(self):
        body = self.body()
        self.assertTrue(body["expedition_available"])
        self.assertIsNone(body["expedition_available_at"])
        self.assertEqual(body["expedition_available_in_seconds"], 0)
        self.assertFalse(MountExpedition.objects.exists())

    def test_claimed_and_expired_today_wait_for_family_midnight(self):
        for status in ("claimed", "expired"):
            with self.subTest(status=status):
                self.trip(status=status)
                body = self.body()
                self.assertFalse(body["expedition_available"])
                self.assertEqual(body["expedition_available_at"], "2026-10-11T04:00:00-07:00")
                self.assertEqual(body["expedition_available_in_seconds"], 1)
                MountExpedition.objects.all().delete()

    def test_exact_family_midnight_opens_next_day(self):
        self.trip()
        self.assertFalse(self.body(NOW)["expedition_available"])
        body = self.body(MIDNIGHT)
        self.assertTrue(body["expedition_available"])
        self.assertIsNone(body["expedition_available_at"])
        self.assertEqual(body["expedition_available_in_seconds"], 0)

    def test_family_midnight_resets_species_and_shared_limits_not_server_midnight(self):
        other_species = [PetSpecies.objects.create(name=f"Species {number}", slug=f"species-{number}") for number in (2, 3)]
        other_mount, unused_mount = [UserMount.objects.create(user=self.user, species=species, potion=self.potion)
                                     for species in other_species]
        earlier = SERVER_MIDNIGHT - timedelta(hours=3)
        self.trip(started_at=earlier)
        self.trip(mount=other_mount, status="expired", started_at=earlier)

        for instant, seconds in ((SERVER_MIDNIGHT, 4 * 60 * 60), (NOW, 1)):
            with self.subTest(instant=instant), patch("django.utils.timezone.now", return_value=instant):
                for mount in (self.mount, unused_mount):
                    projected = UserMountSerializer(mount).data
                    self.assertFalse(projected["expedition_available"])
                    self.assertEqual(projected["expedition_available_at"], "2026-10-11T04:00:00-07:00")
                    self.assertEqual(projected["expedition_available_in_seconds"], seconds)
                with self.assertRaisesMessage(ExpeditionError, "already been out today"):
                    ExpeditionService.start(self.user, self.mount.pk, "short")
                with self.assertRaisesMessage(ExpeditionError, "2 expedition starts"):
                    ExpeditionService.start(self.user, unused_mount.pk, "short")
        self.assertEqual(MountExpedition.objects.count(), 2)

        with patch("django.utils.timezone.now", return_value=MIDNIGHT), patch.object(
            ExpeditionService, "_roll_loot", return_value={"coins": 3, "items": []},
        ):
            for mount in (self.mount, unused_mount):
                projected = UserMountSerializer(mount).data
                self.assertTrue(projected["expedition_available"])
                self.assertIsNone(projected["expedition_available_at"])
                self.assertEqual(projected["expedition_available_in_seconds"], 0)
            for mount in (self.mount, unused_mount):
                self.assertEqual(ExpeditionService.start(self.user, mount.pk, "short").started_at, MIDNIGHT)
            with self.assertRaisesMessage(ExpeditionError, "2 expedition starts"):
                ExpeditionService.start(self.user, other_mount.pk, "short")
        self.assertEqual(MountExpedition.objects.count(), 4)

    def test_active_trip_requires_claim_even_after_next_day_and_return(self):
        trip = self.trip(status="active")
        body = self.body(MIDNIGHT)
        self.assertTrue(body["active_expedition"]["is_ready"])
        self.assertFalse(body["expedition_available"])
        self.assertIsNone(body["expedition_available_at"])
        self.assertIsNone(body["expedition_available_in_seconds"])
        trip.refresh_from_db()
        self.assertEqual(trip.status, "active")

    def test_active_readiness_and_seconds_use_one_clock_snapshot(self):
        trip = self.trip(status="active")
        trip.returns_at = MIDNIGHT
        trip.save(update_fields=["returns_at"])
        instants = iter((NOW, MIDNIGHT))
        with patch("django.utils.timezone.now", side_effect=lambda: next(instants, MIDNIGHT)):
            body = UserMountSerializer(self.mount).data
        self.assertFalse(body["active_expedition"]["is_ready"])
        self.assertEqual(body["active_expedition"]["seconds_remaining"], 1)

    def test_daily_fields_share_snapshot_across_midnight(self):
        self.trip()
        instants = iter((NOW, MIDNIGHT))
        with patch("django.utils.timezone.now", side_effect=lambda: next(instants, MIDNIGHT)):
            serializer = UserMountSerializer(self.mount)
            # Daily fields must retain this pre-midnight snapshot even if a
            # later serializer field samples the clock after the boundary.
            self.assertFalse(serializer.get_expedition_available(self.mount))
            self.assertEqual(serializer.get_expedition_available_at(self.mount), "2026-10-11T04:00:00-07:00")

    def test_sibling_trip_does_not_limit_or_enter_owned_stable(self):
        sibling_mount = UserMount.objects.create(user=self.sibling, species=self.species, potion=self.potion)
        MountExpedition.objects.create(
            mount=sibling_mount, tier="short", status="claimed",
            started_at=NOW - timedelta(hours=3), returns_at=NOW - timedelta(hours=1), loot={},
        )
        with patch("django.utils.timezone.now", return_value=NOW):
            body = self.client.get("/api/pets/stable/").json()
        self.assertEqual([mount["id"] for mount in body["mounts"]], [self.mount.pk])
        self.assertTrue(body["mounts"][0]["expedition_available"])

    def test_client_fields_are_read_only(self):
        self.trip()
        serializer = UserMountSerializer(self.mount, data={"expedition_available": True, "expedition_available_at": None})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data, {})
        with patch("django.utils.timezone.now", return_value=NOW):
            self.assertFalse(serializer.data["expedition_available"])
