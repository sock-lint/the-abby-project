"""Retry admission fences raw binding edits without holding partial locks."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone as datetime_timezone
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib import admin
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, override_settings

from apps.pets.models import PetSpecies, PotionType
from apps.quests.availability import RetryCatalogBusy, lock_retry_reward_catalog
from apps.quests.controls import retry_challenge
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.quests.reference_locks import admit_snapshot_choices
from apps.rpg.content.publication import _catalog_lock
from apps.rpg.models import ItemDefinition
from config.tests.factories import make_family


POLICY = {"schema_version": 1, "potion_slugs": ["base", "fire"], "pets": [
    {"species_slug": "retry-lock-chick", "sprite_key": "retry-lock-chick", "potion_slugs": ["base", "fire"]},
]}


@skipUnless(connection.vendor == "postgresql", "PostgreSQL catalog table locks required")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=POLICY)
class RetryRewardAdmissionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "retry-lock-child"}]).children[0]
        self.child.family.timezone = "UTC"
        self.child.family.save(update_fields=["timezone"])
        self.species = PetSpecies.objects.create(slug="retry-lock-chick", name="Retry lock chick", sprite_key="retry-lock-chick")
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.fire = PotionType.objects.create(slug="fire", name="Fire")
        self.species.available_potions.set([self.base, self.fire])
        self.egg = ItemDefinition.objects.create(slug="retry-lock-egg", name="Retry egg", item_type="egg", pet_species=self.species)
        self.potion = ItemDefinition.objects.create(slug="fire-potion", name="Retry fire potion", item_type="potion", potion_type=self.fire)
        accepted = datetime(2026, 10, 1, 12, tzinfo=datetime_timezone.utc)
        self.now = accepted + timedelta(days=2)
        with patch("django.utils.timezone.now", return_value=accepted):
            definition = QuestDefinition.objects.create(name="Retry reward concurrency", is_system=True,
                quest_type="collection", target_value=1, duration_days=1,
                trigger_filter={"allowed_triggers": ["chore_complete"]})
            for item in (self.egg, self.potion):
                QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=1)
            list_goals(self.child)
            self.original = ChallengeOccurrence.objects.get(goal__catalog_definition=definition, goal__user=self.child)
        self.jobs = []

    def tearDown(self):
        for thread, release in self.jobs:
            release.set()
            thread.join(10)
            self.assertFalse(thread.is_alive(), "Retry review worker did not drain")
        connections.close_all()
        super().tearDown()

    def retry(self):
        with patch("django.utils.timezone.now", return_value=self.now):
            return retry_challenge(self.child, self.original.pk)

    def start(self, action, release):
        output, ready = {}, Event()

        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '8s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    output["pid"] = cursor.fetchone()[0]
                ready.set()
                output["value"] = action()
            except Exception as error:
                output["error"] = error
            finally:
                connections.close_all()

        thread = Thread(target=worker)
        thread.start()
        self.jobs.append((thread, release))
        self.assertTrue(ready.wait(5), "Retry worker never connected")
        return thread, output

    def join(self, thread, output):
        thread.join(10)
        self.assertFalse(thread.is_alive(), "Retry worker did not finish")
        if "error" in output:
            raise output["error"]
        return output.get("value")

    def test_conflict_releases_partial_fence_and_creates_no_successor(self):
        held, release = Event(), Event()

        def writer():
            with transaction.atomic():
                ItemDefinition.objects.filter(pk=self.potion.pk).update(description="Concurrent binding edit")
                held.set()
                self.assertTrue(release.wait(5), "Binding writer was not released")

        thread, output = self.start(writer, release)
        self.assertTrue(held.wait(5))
        try:
            # Conflict occurs on the final sorted table, after the three pet
            # tables were admitted. The savepoint must release those locks.
            with transaction.atomic():
                with self.assertRaises(RetryCatalogBusy):
                    lock_retry_reward_catalog()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT relation::regclass::text FROM pg_locks WHERE pid=pg_backend_pid() "
                                   "AND mode='ShareLock' AND locktype='relation'")
                    self.assertEqual(cursor.fetchall(), [])
                    cursor.execute("SELECT 1")
                    self.assertEqual(cursor.fetchone(), (1,))
            with self.assertRaises(RetryCatalogBusy):
                self.retry()
            self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=self.original).exists())
        finally:
            release.set()
        self.join(thread, output)

    def test_actual_admin_collector_finishes_and_retry_reads_deleted_binding(self):
        updated, release = Event(), Event()

        def writer():
            def pause(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if sql.startswith('UPDATE "rpg_itemdefinition"'):
                    updated.set()
                    self.assertTrue(release.wait(5), "Admin collector was not released")
                return result
            with connection.execute_wrapper(pause), transaction.atomic():
                admin.site._registry[PotionType].delete_model(SimpleNamespace(), PotionType.objects.get(pk=self.fire.pk))

        thread, output = self.start(writer, release)
        self.assertTrue(updated.wait(5))
        try:
            with self.assertRaises(RetryCatalogBusy):
                self.retry()
        finally:
            release.set()
        self.join(thread, output)
        with self.assertRaisesMessage(ValueError, "reward_unavailable"):
            self.retry()
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=self.original).exists())

    def test_publication_admission_conflicts_then_retry_checks_fresh_binding(self):
        held, release = Event(), Event()

        def writer():
            with transaction.atomic():
                _catalog_lock()
                ItemDefinition.objects.filter(pk=self.potion.pk).update(potion_type=None)
                held.set()
                self.assertTrue(release.wait(5), "Publication writer was not released")

        thread, output = self.start(writer, release)
        self.assertTrue(held.wait(5))
        try:
            with self.assertRaises(RetryCatalogBusy):
                self.retry()
        finally:
            release.set()
        self.join(thread, output)
        with self.assertRaisesMessage(ValueError, "reward_unavailable"):
            self.retry()
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=self.original).exists())

    def test_fence_blocks_compatibility_phantom_and_saved_replay_skips_admission(self):
        self.species.available_potions.clear()  # Existing empty relation is unrestricted.
        captured, release = Event(), Event()
        saved = deepcopy(self.original.snapshot)

        def paused_admission(*args, **kwargs):
            result = admit_snapshot_choices(*args, **kwargs)
            captured.set()
            self.assertTrue(release.wait(5), "Retry admission was not released")
            return result

        with patch("apps.quests.reference_locks.admit_snapshot_choices", side_effect=paused_admission):
            reader, read_output = self.start(self.retry, release)
            self.assertTrue(captured.wait(5))
            writer, write_output = self.start(lambda: self.species.available_potions.add(self.base), release)
            try:
                deadline = monotonic() + 3
                with connection.cursor() as cursor:
                    while monotonic() < deadline:
                        cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [read_output["pid"], write_output["pid"]])
                        if cursor.fetchone()[0]:
                            break
                        Event().wait(.01)
                    else:
                        self.fail("Compatibility insertion did not wait for retry's admission fence")
            finally:
                release.set()
            successor, created = self.join(reader, read_output)
            self.join(writer, write_output)
        self.assertTrue(created)
        self.assertEqual(successor.snapshot, {**saved, "_retry_after_activity_id": 0})
        with patch("apps.quests.controls.lock_retry_reward_catalog", side_effect=AssertionError("Replay reached fresh gate")):
            replay, replay_created = self.retry()
        self.assertFalse(replay_created)
        self.assertEqual(replay.pk, successor.pk)
