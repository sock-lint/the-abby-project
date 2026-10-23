"""Potion appearances share their owner's species expedition allowance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as datetime_timezone
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.expeditions import ExpeditionError, ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.pets.serializers import UserMountSerializer
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


NOW = datetime(2026, 10, 20, 18, tzinfo=datetime_timezone.utc)
TOMORROW = NOW + timedelta(days=1)


class SharedAllowanceSetup:
    species_identity = ("chick", "Chick", "cute-chick")

    def setUp(self):
        household = make_family(
            "Elemental expeditions",
            children=[{"username": "element-child"}, {"username": "element-sibling"}],
        )
        self.user, self.sibling = household.children
        slug, name, sprite_key = self.species_identity
        self.species = PetSpecies.objects.create(slug=slug, name=name, sprite_key=sprite_key)
        self.other_species = PetSpecies.objects.create(slug="meshtint-wolf", name="Wolf")
        self.base, self.fire, self.ice = [
            PotionType.objects.create(slug=slug, name=slug.title()) for slug in ("base", "fire", "ice")
        ]
        self.mounts = [
            UserMount.objects.create(user=self.user, species=self.species, potion=potion)
            for potion in (self.base, self.fire, self.ice)
        ]
        self.base_mount, self.fire_mount, self.ice_mount = self.mounts

    def trip(self, *, mount=None, status="claimed", started_at=NOW, returns_at=None, loot=None):
        return MountExpedition.objects.create(
            mount=mount or self.base_mount, tier="short", status=status,
            started_at=started_at, returns_at=returns_at or started_at + timedelta(hours=2),
            loot=loot or {"coins": 15, "items": []},
        )


@override_settings(TIME_ZONE="America/Phoenix", USE_TZ=True,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SharedExpeditionAllowanceTests(SharedAllowanceSetup, TestCase):
    def test_claimed_and_expired_trip_use_every_appearance_allowance(self):
        for status in ("claimed", "expired"):
            with self.subTest(status=status):
                self.trip(status=status)
                try:
                    with patch("django.utils.timezone.now", return_value=NOW):
                        for mount in (self.fire_mount, self.ice_mount):
                            with self.assertRaisesMessage(ExpeditionError, "already been out today"):
                                ExpeditionService.start(self.user, mount.pk, "short")
                    self.assertEqual(MountExpedition.objects.count(), 1)
                finally:
                    MountExpedition.objects.all().delete()

    def test_unclaimed_other_appearance_blocks_next_day_before_and_after_return(self):
        for returns_at in (TOMORROW - timedelta(seconds=1), TOMORROW + timedelta(hours=1)):
            with self.subTest(returns_at=returns_at):
                self.trip(status="active", returns_at=returns_at)
                try:
                    with patch("django.utils.timezone.now", return_value=TOMORROW):
                        with self.assertRaisesMessage(ExpeditionError, "already out"):
                            ExpeditionService.start(self.user, self.fire_mount.pk, "short")
                finally:
                    MountExpedition.objects.all().delete()

    def test_next_day_claimed_trip_allows_different_appearance(self):
        self.trip()
        with patch("django.utils.timezone.now", return_value=TOMORROW):
            expedition = ExpeditionService.start(self.user, self.ice_mount.pk, "standard")
        self.assertEqual(expedition.mount_id, self.ice_mount.pk)
        self.assertEqual(expedition.started_at, TOMORROW)
        self.assertEqual(expedition.returns_at, TOMORROW + timedelta(hours=4))

    def test_other_species_sibling_and_other_family_have_separate_allowances(self):
        self.trip(status="active")
        other_child = make_family("Other expedition family", children=[{"username": "other-child"}]).children[0]
        independent_mounts = [
            UserMount.objects.create(user=self.user, species=self.other_species, potion=self.fire),
            UserMount.objects.create(user=self.sibling, species=self.species, potion=self.fire),
            UserMount.objects.create(user=other_child, species=self.species, potion=self.fire),
        ]
        with patch("django.utils.timezone.now", return_value=NOW):
            for mount in independent_mounts:
                with self.subTest(mount=mount.pk):
                    self.assertTrue(UserMountSerializer(mount).data["expedition_available"])
                    expedition = ExpeditionService.start(mount.user, mount.pk, "short")
                    self.assertEqual(expedition.mount_id, mount.pk)
                    self.assertTrue(UserMountSerializer(mount).data["active_expedition"])
            self.assertEqual(MountExpedition.objects.count(), 4)

    def test_stable_serializes_shared_daily_reset_for_all_appearances(self):
        trip = self.trip()
        client = APIClient()
        client.force_authenticate(self.user)
        with patch("django.utils.timezone.now", return_value=NOW):
            response = client.get("/api/pets/stable/")
        self.assertEqual(response.status_code, 200)
        mounts = response.json()["mounts"]
        self.assertEqual({mount["id"] for mount in mounts}, {mount.pk for mount in self.mounts})
        for mount in mounts:
            self.assertFalse(mount["expedition_available"])
            self.assertEqual(mount["expedition_available_at"], "2026-10-21T00:00:00-07:00")
            self.assertEqual(mount["expedition_available_in_seconds"], 13 * 3600)
        trip.refresh_from_db()
        self.assertEqual(trip.status, "claimed")

    def test_other_appearance_unclaimed_trip_has_no_promised_reset_time(self):
        self.trip(status="active")
        with patch("django.utils.timezone.now", return_value=TOMORROW):
            for mount in (self.fire_mount, self.ice_mount):
                body = UserMountSerializer(mount).data
                self.assertIsNone(body["active_expedition"])
                self.assertFalse(body["expedition_available"])
                self.assertIsNone(body["expedition_available_at"])
                self.assertIsNone(body["expedition_available_in_seconds"])

    def test_saved_overlapping_trips_keep_their_locked_rewards_and_claims(self):
        # Runs accepted before the shared allowance change are not canceled,
        # retimed or rerolled. Each exact receipt remains independently payable.
        trips = [
            self.trip(mount=mount, status="active", returns_at=NOW + timedelta(hours=2),
                      loot={"coins": coins, "items": []})
            for mount, coins in zip(self.mounts, (15, 21, 35), strict=True)
        ]
        with patch("django.utils.timezone.now", return_value=TOMORROW):
            for trip, coins in zip(trips, (15, 21, 35), strict=True):
                claimed = ExpeditionService.claim(self.user, trip.pk)
                self.assertTrue(claimed["freshly_claimed"])
                self.assertEqual(claimed["coins_awarded"], coins)
                self.assertEqual(claimed["mount"]["id"], trip.mount_id)
                self.assertFalse(ExpeditionService.claim(self.user, trip.pk)["freshly_claimed"])
                trip.refresh_from_db()
                self.assertEqual(trip.started_at, NOW)
                self.assertEqual(trip.returns_at, NOW + timedelta(hours=2))
                self.assertEqual(trip.loot, {"coins": coins, "items": []})
            ExpeditionService.start(self.user, self.fire_mount.pk, "short")
        self.assertEqual(sum(CoinLedger.objects.filter(user=self.user).values_list("amount", flat=True)), 71)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SharedExpeditionConcurrencyTests(SharedAllowanceSetup, TransactionTestCase):
    @staticmethod
    def worker(callback, ready, pids, label):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[label] = cursor.fetchone()[0]
            ready.set()
            try:
                return callback()
            except ExpeditionError as exc:
                return exc
        finally:
            connection.close()

    def test_two_different_appearance_starts_serialize_before_rolling_rewards(self):
        held, release, second_ready = Event(), Event(), Event()
        pids = {}

        def pause_loot(user, tier):
            held.set()
            if not release.wait(10):
                raise TimeoutError("First launch was not released")
            return {"coins": 15, "items": []}

        with patch.object(ExpeditionService, "_roll_loot", side_effect=pause_loot) as loot:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.worker, lambda: ExpeditionService.start(self.user, self.fire_mount.pk, "short"),
                                    Event(), pids, "first")
                second = None
                try:
                    self.assertTrue(held.wait(5), "First launch never rolled loot")
                    second = pool.submit(self.worker, lambda: ExpeditionService.start(self.user, self.ice_mount.pk, "short"),
                                         second_ready, pids, "second")
                    self.assertTrue(second_ready.wait(5))
                    deadline, tick = monotonic() + 4, Event()
                    while monotonic() < deadline:
                        self.assertFalse(second.done(), "Second appearance bypassed the shared allowance lock")
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_blocking_pids(%s)", [pids["second"]])
                            if pids["first"] in cursor.fetchone()[0]:
                                break
                        tick.wait(0.01)
                    else:
                        self.fail("Second appearance did not wait for the shared user gate")
                finally:
                    release.set()
                first_result = first.result(timeout=15)
                self.assertIsNotNone(second)
                second_result = second.result(timeout=15)
        self.assertIsInstance(first_result, MountExpedition)
        self.assertIsInstance(second_result, ExpeditionError)
        self.assertEqual(loot.call_count, 1)
        self.assertEqual(MountExpedition.objects.count(), 1)


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class DragonSharedExpeditionAllowanceTests(SharedExpeditionAllowanceTests):
    species_identity = ("meshtint-dragon", "Dragon", "meshtint-dragon")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class MushroomSharedExpeditionAllowanceTests(SharedExpeditionAllowanceTests):
    species_identity = ("meshtint-mushroom", "Mushroom", "meshtint-mushroom")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class DragonSharedExpeditionConcurrencyTests(SharedExpeditionConcurrencyTests):
    species_identity = ("meshtint-dragon", "Dragon", "meshtint-dragon")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class MushroomSharedExpeditionConcurrencyTests(SharedExpeditionConcurrencyTests):
    species_identity = ("meshtint-mushroom", "Mushroom", "meshtint-mushroom")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class BeeSharedExpeditionAllowanceTests(SharedExpeditionAllowanceTests):
    species_identity = ("meshtint-bee", "Bee", "meshtint-bee")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class BatSharedExpeditionAllowanceTests(SharedExpeditionAllowanceTests):
    species_identity = ("meshtint-bat", "Bat", "meshtint-bat")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class BeeSharedExpeditionConcurrencyTests(SharedExpeditionConcurrencyTests):
    species_identity = ("meshtint-bee", "Bee", "meshtint-bee")


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class BatSharedExpeditionConcurrencyTests(SharedExpeditionConcurrencyTests):
    species_identity = ("meshtint-bat", "Bat", "meshtint-bat")
