"""New shared trip limits and frozen salvage never reprice accepted rewards."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as datetime_timezone
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings

from apps.pets.expeditions import ExpeditionError, ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.pets.serializers import UserMountSerializer
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


NOW = datetime(2026, 10, 23, 18, tzinfo=datetime_timezone.utc)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PassiveExpeditionPolicyTests(TestCase):
    def setUp(self):
        family = make_family("Passive policy", children=[{"username": "child"}, {"username": "sibling"}])
        self.user, self.sibling = family.children
        self.potion = PotionType.objects.create(slug="base", name="Base")
        self.species = [PetSpecies.objects.create(slug=f"species-{number}", name=f"Species {number}") for number in range(3)]
        self.mounts = [UserMount.objects.create(user=self.user, species=species, potion=self.potion) for species in self.species]

    def start(self, mount, *, now=NOW, tier="short"):
        with patch("django.utils.timezone.now", return_value=now):
            return ExpeditionService.start(mount.user, mount.pk, tier)

    def test_two_trips_share_the_child_allowance_across_species_and_statuses(self):
        for mount, status in zip(self.mounts[:2], ("claimed", "expired"), strict=True):
            trip = self.start(mount)
            trip.status = status
            trip.save(update_fields=["status"])
        with self.assertRaisesMessage(ExpeditionError, "2 expedition"):
            self.start(self.mounts[2])
        self.assertEqual(MountExpedition.objects.filter(mount__user=self.user).count(), 2)
        sibling_mount = UserMount.objects.create(user=self.sibling, species=self.species[2], potion=self.potion)
        self.assertEqual(self.start(sibling_mount).mount_id, sibling_mount.pk)

    def test_allowance_uses_family_midnight_and_mount_projection_matches(self):
        self.user.family.timezone = "Asia/Tokyo"
        self.user.family.save(update_fields=["timezone"])
        before_midnight = datetime(2026, 10, 23, 14, 59, tzinfo=datetime_timezone.utc)
        for mount in self.mounts[:2]:
            self.start(mount, now=before_midnight)
        with patch("django.utils.timezone.now", return_value=before_midnight):
            projected = UserMountSerializer(self.mounts[2]).data
            self.assertFalse(projected["expedition_available"])
            self.assertEqual(projected["expedition_available_in_seconds"], 60)
        self.assertEqual(self.start(self.mounts[2], now=before_midnight + timedelta(minutes=1)).mount_id, self.mounts[2].pk)

    def test_legacy_launch_history_uses_allowance_without_rewriting_saved_loot(self):
        legacy_loot = {"coins": 75, "items": []}
        saved = [MountExpedition.objects.create(
            mount=mount, tier="long", status="claimed", started_at=NOW,
            returns_at=NOW + timedelta(hours=8), loot=legacy_loot,
        ) for mount in self.mounts[:2]]
        with self.assertRaisesMessage(ExpeditionError, "2 expedition"):
            self.start(self.mounts[2])
        for trip in saved:
            trip.refresh_from_db()
            self.assertEqual(trip.loot, legacy_loot)
        self.assertFalse(CoinLedger.objects.filter(user=self.user).exists())

    def cosmetic(self):
        item = ItemDefinition.objects.create(slug="saved-frame", name="Saved Frame", item_type="cosmetic_frame", rarity="common", coin_value=100)
        UserInventory.objects.create(user=self.user, item=item, quantity=1)
        return item

    def test_new_expedition_freezes_ten_coin_salvage_before_later_catalog_edits(self):
        item = self.cosmetic()
        DropTable.objects.create(trigger_type="expedition_returned", item=item, weight=1)
        trip = self.start(self.mounts[0], tier="long")
        self.assertEqual([slot["salvage_coins_snapshot"] for slot in trip.loot["items"]], [10, 10, 10])
        item.coin_value = 999
        item.save(update_fields=["coin_value"])
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)):
            first = ExpeditionService.claim(self.user, trip.pk)
            again = ExpeditionService.claim(self.user, trip.pk)
        self.assertTrue(first["freshly_claimed"])
        self.assertFalse(again["freshly_claimed"])
        salvage = CoinLedger.objects.filter(user=self.user, source="expedition_salvage")
        self.assertEqual(list(salvage.values_list("amount", flat=True)), [10, 10, 10])

    def test_legacy_pending_trips_keep_full_salvage_and_direct_coins(self):
        item = self.cosmetic()
        trip = MountExpedition.objects.create(
            mount=self.mounts[0], tier="long", status="active", started_at=NOW - timedelta(days=1),
            returns_at=NOW - timedelta(hours=1), loot={"coins": 75, "items": [{"item_id": item.pk, "quantity": 1}]},
        )
        with patch("django.utils.timezone.now", return_value=NOW):
            result = ExpeditionService.claim(self.user, trip.pk)
        self.assertEqual(result["coins_awarded"], 75)
        self.assertEqual(CoinLedger.objects.get(user=self.user, source="expedition_salvage").amount, 100)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PassiveExpeditionConcurrencyTests(TransactionTestCase):
    setUp = PassiveExpeditionPolicyTests.setUp
    start = PassiveExpeditionPolicyTests.start

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

    def test_two_species_race_for_one_remaining_child_slot(self):
        first = self.start(self.mounts[0])
        first.status = "claimed"
        first.save(update_fields=["status"])
        held, release, second_ready = Event(), Event(), Event()
        pids = {}

        def pause_loot(user, tier):
            held.set()
            if not release.wait(10):
                raise TimeoutError("First shared-quota launch was not released")
            return {"coins": 3, "items": []}

        with patch("django.utils.timezone.now", return_value=NOW), patch.object(ExpeditionService, "_roll_loot", side_effect=pause_loot) as loot:
            with ThreadPoolExecutor(max_workers=2) as pool:
                winner = pool.submit(self.worker, lambda: ExpeditionService.start(self.user, self.mounts[1].pk, "short"), Event(), pids, "first")
                second = None
                try:
                    self.assertTrue(held.wait(5))
                    second = pool.submit(self.worker, lambda: ExpeditionService.start(self.user, self.mounts[2].pk, "short"), second_ready, pids, "second")
                    self.assertTrue(second_ready.wait(5))
                    deadline, tick = monotonic() + 4, Event()
                    while monotonic() < deadline:
                        self.assertFalse(second.done(), "Concurrent species bypassed the shared user gate")
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_blocking_pids(%s)", [pids["second"]])
                            if pids["first"] in cursor.fetchone()[0]:
                                break
                        tick.wait(0.01)
                    else:
                        self.fail("Concurrent species never waited for the shared quota lock")
                finally:
                    release.set()
                self.assertIsInstance(winner.result(timeout=15), MountExpedition)
                self.assertIsNotNone(second)
                self.assertIsInstance(second.result(timeout=15), ExpeditionError)
        self.assertEqual(loot.call_count, 1)
        self.assertEqual(MountExpedition.objects.filter(mount__user=self.user).count(), 2)
