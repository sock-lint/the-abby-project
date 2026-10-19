"""PostgreSQL regressions for expedition, activation and companion-care locks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import PetService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row and foreign-key locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CareLockOrderTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family(
            "Care lock family", children=[{"username": "care-lock-child"}],
        ).children[0]
        self.species = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.notify = patch("apps.notifications.services.notify").start()
        self.notify_parents = patch("apps.notifications.services.notify_parents").start()
        self.game_loop = patch("apps.rpg.services.GameLoopService.on_task_completed").start()
        self.addCleanup(patch.stopall)

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
            return callback()
        finally:
            connection.close()

    def overlap(self, first, second, held, release):
        """Release the first operation after observing the second's real row wait."""
        pids, second_ready = {}, Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(self.worker, first, Event(), pids, "first")
            second_future = None
            try:
                self.assertTrue(held.wait(5), "First operation never reached its held write")
                second_future = pool.submit(self.worker, second, second_ready, pids, "second")
                self.assertTrue(second_ready.wait(5), "Competing connection never started")
                deadline, tick = monotonic() + 4, Event()
                while monotonic() < deadline:
                    if second_future.done():
                        second_future.result()
                        self.fail("Competing operation finished instead of waiting for the held transaction")
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids["second"]])
                        if pids["first"] in cursor.fetchone()[0]:
                            break
                    tick.wait(0.01)
                else:
                    self.fail("Competing operation never waited for the held transaction")
            finally:
                release.set()
            first_result = first_future.result(timeout=15)
            self.assertIsNotNone(second_future)
            return first_result, second_future.result(timeout=15)

    def make_expedition(self, *, item=None):
        mount = UserMount.objects.create(user=self.child, species=self.species, potion=self.base)
        return MountExpedition.objects.create(
            mount=mount, tier="short", started_at=timezone.now() - timedelta(hours=3),
            returns_at=timezone.now() - timedelta(seconds=1),
            loot={"coins": 15, "items": ([{"item_id": item.pk, "quantity": 1}] if item else [])},
        )

    def test_evolving_feed_and_expedition_claim_preserve_both_rewards_without_deadlock(self):
        # A different species still shares the expedition mount's Base potion.
        fox = PetSpecies.objects.create(slug="saved-fox", name="Saved Fox")
        pet = UserPet.objects.create(user=self.child, species=fox, potion=self.base, growth_points=95)
        food = ItemDefinition.objects.create(name="Care lock food", item_type="food")
        inventory = UserInventory.objects.create(user=self.child, item=food, quantity=2)
        expedition = self.make_expedition(item=food)
        held, release = Event(), Event()
        original = PetService._save_growth

        def pause_evolution(locked_pet, **kwargs):
            if locked_pet.pk == pet.pk:
                held.set()
                if not release.wait(10):
                    raise TimeoutError("Held evolution was not released")
            return original(locked_pet, **kwargs)

        # Feeding already owns its food stack when the claim begins. A claim
        # that locks joined catalog rows first creates a Base-potion FK cycle
        # when this feed evolves, causing PostgreSQL to abort one real service.
        with patch.object(PetService, "_save_growth", pause_evolution):
            fed, claimed = self.overlap(
                lambda: PetService.feed_pet(self.child, pet.pk, food.pk),
                lambda: ExpeditionService.claim(self.child, expedition.pk), held, release,
            )

        self.assertTrue(fed["evolved"])
        self.assertTrue(claimed["freshly_claimed"])
        pet.refresh_from_db()
        inventory.refresh_from_db()
        expedition.refresh_from_db()
        self.assertTrue(pet.evolved_to_mount)
        self.assertEqual(UserMount.objects.filter(user=self.child, species=fox, potion=self.base).count(), 1)
        self.assertEqual(inventory.quantity, 2)
        self.assertEqual(expedition.status, MountExpedition.Status.CLAIMED)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [15])
        self.assertFalse(ExpeditionService.claim(self.child, expedition.pk)["freshly_claimed"])
        self.assertEqual(UserInventory.objects.get(pk=inventory.pk).quantity, 2)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_claim_does_not_lock_shared_catalog_or_mount_rows(self):
        expedition = self.make_expedition()
        held, release, pids = Event(), Event(), {}
        original = ExpeditionService._materialize_loot

        def pause_claim(user, locked_expedition):
            held.set()
            if not release.wait(10):
                raise TimeoutError("Held expedition claim was not released")
            return original(user, locked_expedition)

        with patch.object(ExpeditionService, "_materialize_loot", pause_claim):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self.worker, lambda: ExpeditionService.claim(self.child, expedition.pk), Event(), pids, "claim",
                )
                try:
                    self.assertTrue(held.wait(5))
                    with transaction.atomic():
                        # Shared species/potion locks block unrelated families'
                        # ownership inserts. Claim only needs its receipt row.
                        PetSpecies.objects.select_for_update(nowait=True).get(pk=self.species.pk)
                        PotionType.objects.select_for_update(nowait=True).get(pk=self.base.pk)
                        UserMount.objects.select_for_update(nowait=True).get(pk=expedition.mount_id)
                finally:
                    release.set()
                self.assertTrue(future.result(timeout=15)["freshly_claimed"])

    def test_activation_and_feast_preserve_active_choice_and_all_growth_without_deadlock(self):
        target = UserPet.objects.create(user=self.child, species=self.species, potion=self.base)
        fox = PetSpecies.objects.create(slug="saved-fox", name="Saved Fox")
        previous = UserPet.objects.create(user=self.child, species=fox, potion=self.base, is_active=True)
        feast = ItemDefinition.objects.create(
            name="Care lock feast", item_type="consumable", metadata={"effect": "feast_platter", "growth": 10},
        )
        UserInventory.objects.create(user=self.child, item=feast, quantity=1)
        held, release = Event(), Event()
        original = UserPet.save

        def pause_activation(pet, *args, **kwargs):
            if pet.pk == target.pk and "is_active" in (kwargs.get("update_fields") or []):
                held.set()
                if not release.wait(10):
                    raise TimeoutError("Held pet activation was not released")
            return original(pet, *args, **kwargs)

        # Activation has deactivated the newer pet before saving the older
        # target. Feast scans oldest first; both must acquire the user gate
        # before either can own those pet locks in the opposite order.
        with patch.object(UserPet, "save", pause_activation):
            activated, used = self.overlap(
                lambda: PetService.set_active_pet(self.child, target.pk),
                lambda: ConsumableService.use(self.child, feast.pk), held, release,
            )

        self.assertEqual(activated.pk, target.pk)
        self.assertEqual(used["detail"]["growth_per_pet_applied"], [10, 10])
        target.refresh_from_db()
        previous.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertFalse(previous.is_active)
        self.assertEqual((target.growth_points, previous.growth_points), (10, 10))
        self.assertEqual((target.consumable_growth_today, previous.consumable_growth_today), (10, 10))
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=feast).exists())
