"""Real PostgreSQL overlap checks for consumables sharing saved progression."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.achievements.services import _lock_award_user
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.pets.services import PetService
from apps.projects.models import User
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row serialization")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConsumableConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="concurrent-consumable-child", role="child")

    def worker(self, callback, ready, pids, label):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[label] = cursor.fetchone()[0]
            ready.set()
            return callback()
        finally:
            connection.close()

    def wait_for_block_or_finish(self, future, pid):
        """Observe a real lock wait or completed call rather than racing a sleep."""
        deadline = monotonic() + 4
        tick = Event()
        while monotonic() < deadline:
            if future.done():
                future.result()
                return "finished"
            with connection.cursor() as cursor:
                cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [pid])
                if cursor.fetchone()[0]:
                    return "blocked"
            tick.wait(0.01)
        self.fail("Competing operation neither finished nor entered a database lock wait")

    def test_feed_and_growth_surge_preserve_both_consumed_items_growth(self):
        chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        base = PotionType.objects.create(slug="base", name="Base")
        pet = UserPet.objects.create(user=self.child, species=chick, potion=base, is_active=True)
        food = ItemDefinition.objects.create(name="Birdseed", item_type="food", food_species=chick)
        surge = ItemDefinition.objects.create(
            name="Accelerator", item_type="consumable", metadata={"effect": "growth_surge", "growth": 30},
        )
        for item in (food, surge):
            UserInventory.objects.create(user=self.child, item=item, quantity=1)

        surge_has_pet, release_surge = Event(), Event()
        original = UserPet.apply_consumable_growth

        def pause_after_surge_read(locked_pet, amount):
            surge_has_pet.set()
            if not release_surge.wait(5):
                raise AssertionError("Surge was not released within the bounded overlap")
            return original(locked_pet, amount)

        pids = {}
        surge_ready, feed_ready = Event(), Event()
        with patch.object(UserPet, "apply_consumable_growth", pause_after_surge_read):
            with ThreadPoolExecutor(max_workers=2) as executor:
                surge_future = executor.submit(
                    self.worker, lambda: ConsumableService.use(self.child, surge.pk), surge_ready, pids, "surge",
                )
                try:
                    self.assertTrue(surge_has_pet.wait(5))
                    feed_future = executor.submit(
                        self.worker, lambda: PetService.feed_pet(self.child, pet.pk, food.pk), feed_ready, pids, "feed",
                    )
                    self.assertTrue(feed_ready.wait(5))
                    self.wait_for_block_or_finish(feed_future, pids["feed"])
                finally:
                    release_surge.set()
                surge_result = surge_future.result(timeout=10)
                feed_result = feed_future.result(timeout=10)
        pet.refresh_from_db()
        self.assertEqual((surge_result["detail"]["growth_added"], feed_result["growth_added"]), (30, 15))
        self.assertEqual(pet.growth_points, 45)
        self.assertEqual(pet.consumable_growth_today, 30)
        self.assertIsNotNone(pet.last_fed_at)
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_skill_tonic_takes_user_gate_before_inventory_profile_or_progress(self):
        category = SkillCategory.objects.create(name="Concurrent tonic skills")
        skill = Skill.objects.create(category=category, name="Practice")
        progress = SkillProgress.objects.create(user=self.child, skill=skill, xp_points=90)
        tonic = ItemDefinition.objects.create(
            name="Skill tonic", item_type="consumable", metadata={"effect": "skill_tonic", "xp": 50},
        )
        inventory = UserInventory.objects.create(user=self.child, item=tonic, quantity=1)
        ready, pids = Event(), {}
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                _lock_award_user(self.child)
                future = executor.submit(
                    self.worker, lambda: ConsumableService.use(self.child, tonic.pk), ready, pids, "tonic",
                )
                self.assertTrue(ready.wait(5))
                outcome = self.wait_for_block_or_finish(future, pids["tonic"])
                self.assertEqual(outcome, "blocked")
                # A caller holding the shared user gate can safely take these
                # downstream locks. The tonic cannot take them in reverse order.
                CharacterProfile.objects.select_for_update(nowait=True).get(user=self.child)
                UserInventory.objects.select_for_update(nowait=True).get(pk=inventory.pk)
                SkillProgress.objects.select_for_update(nowait=True).get(pk=progress.pk)
            future.result(timeout=10)
        progress.refresh_from_db()
        self.assertEqual(progress.xp_points, 140)
