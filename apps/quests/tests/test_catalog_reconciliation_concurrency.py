"""Real acceptance/publication interleavings on PostgreSQL, with bounded waits."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.quests import reference_locks
from apps.quests.goals import _occurrence, ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, QuestDefinition
from apps.rewards.models import CoinLedger
from apps.rpg.content import publication
from apps.rpg.content.loader import ContentPack, ContentPackError
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row/advisory locks")
class CatalogReconciliationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = make_family("Reconciliation races", parents=[{"username": "race-author", "is_staff": True}],
                             children=[{"username": "race-child"}])
        self.actor, self.child = family.parents[0], family.children[0]
        self.values = dict(name="In-flight legacy root", description="Preserve this promise", quest_type="collection",
                           target_value=1, duration_days=7, is_system=True, coin_reward=5,
                           trigger_filter={"allowed_triggers": ["habit_log"]})
        self.source = QuestDefinition.objects.create(**self.values, created_by=self.actor)
        self.service = import_module("apps.quests.reconciliation")

    @staticmethod
    def worker(action, pids=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '6s'")
                cursor.execute("SET statement_timeout = '12s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            if pids is not None:
                pids.append(pid)
            return action()
        finally:
            connection.close()

    def wait_for_lock(self, pids, future):
        until = monotonic() + 4
        while monotonic() < until and not future.done():
            if pids:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", [pids[0]])
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    return
            sleep(.01)
        self.fail("The real service did not wait on its expected admission lock")

    def load_duplicate(self):
        # Actual supported bundled lookup excludes creator-owned legacy roots.
        ContentPack(".", namespace="", parsed_content={"quests": {"quests": [self.values]}}).load()
        return QuestDefinition.objects.get(name=self.source.name, created_by=None)

    def publish(self, canonical):
        preview = self.service.preview_reconciliation(self.actor, self.source.pk, canonical.pk, uuid4())
        return self.service.publish_reconciliation(self.actor, preview["preview_id"], preview["content_digest"])

    def test_loader_then_publication_cannot_leave_a_cached_first_enrollment_on_alias(self):
        ready, release = Event(), Event()
        original = reference_locks.admit_definition_choices

        def pause_before_admission(definition):
            if definition.pk == self.source.pk:
                ready.set()
                if not release.wait(8):
                    raise TimeoutError("Cached enrollment was not released")
            return original(definition)

        with patch.object(reference_locks, "admit_definition_choices", side_effect=pause_before_admission), \
                ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.worker, lambda: list_goals(self.child))
            try:
                self.assertTrue(ready.wait(4))
                canonical = self.load_duplicate()
                self.publish(canonical)
            finally:
                release.set()
            future.result(timeout=12)
        list_goals(self.child)
        self.assertEqual(list(ChallengeGoal.objects.filter(user=self.child).values_list(
            "catalog_definition_id", flat=True)), [canonical.pk])
        self.assertFalse(CoinLedger.objects.exists())

    def test_definition_share_finishes_before_preview_and_unlocked_new_member_forces_repreview(self):
        ready, release = Event(), Event()
        create = ChallengeGoal.objects.get_or_create
        pids = []

        def pause_before_insert(*args, **kwargs):
            ready.set()
            if not release.wait(8):
                raise TimeoutError("Admitted first enrollment was not released")
            return create(*args, **kwargs)

        with patch.object(ChallengeGoal.objects, "get_or_create", side_effect=pause_before_insert), \
                ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(self.worker, lambda: list_goals(self.child))
            preview = None
            try:
                self.assertTrue(ready.wait(4))
                canonical = self.load_duplicate()
                preview = pool.submit(self.worker, lambda: self.service.preview_reconciliation(
                    self.actor, self.source.pk, canonical.pk, uuid4()), pids)
                self.wait_for_lock(pids, preview)
            finally:
                release.set()
            reader.result(timeout=12)
            with self.assertRaises(self.service.ReconciliationConflict):
                preview.result(timeout=12)
        goal = ChallengeGoal.objects.get(user=self.child)
        anchor = goal.starts_at
        self.source.refresh_from_db()
        self.assertIsNone(self.source.superseded_by_id)
        self.publish(canonical)
        goal.refresh_from_db()
        self.assertEqual((goal.catalog_definition_id, goal.starts_at), (canonical.pk, anchor))

    def test_completion_waits_for_identity_publication_then_pays_saved_promise_once(self):
        at = timezone.now()
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=self.source, is_catalog=True,
            name=self.source.name, metric="count", target=1, unit="actions", trigger_filter=self.source.trigger_filter,
            timezone_name="America/Phoenix", starts_at=at-timedelta(hours=1), ends_at=at+timedelta(days=1),
            coin_reward=5,
        )
        occurrence = _occurrence(goal, at)
        canonical = self.load_duplicate()
        preview = self.service.preview_reconciliation(self.actor, self.source.pk, canonical.pk, uuid4())
        ready, release, pids = Event(), Event(), []
        catalog_lock = self.service._catalog_lock

        def pause_under_account_locks():
            ready.set()
            if not release.wait(8):
                raise TimeoutError("Identity publication was not released")
            catalog_lock()

        with patch.object(self.service, "_catalog_lock", side_effect=pause_under_account_locks), \
                ThreadPoolExecutor(max_workers=2) as pool:
            publisher = pool.submit(self.worker, lambda: self.service.publish_reconciliation(
                self.actor, preview["preview_id"], preview["content_digest"]))
            source = None
            try:
                self.assertTrue(ready.wait(4))
                source = pool.submit(self.worker, lambda: ingest_activity(
                    self.child, "habit_log", "same-source", "habit_log", occurred_at=at), pids)
                self.wait_for_lock(pids, source)
            finally:
                release.set()
            publisher.result(timeout=12)
            source.result(timeout=12)
        ingest_activity(self.child, "habit_log", "same-source", "habit_log", occurred_at=at)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.status, occurrence.progress), ("completed", 1))
        self.assertEqual(list(CoinLedger.objects.values_list("amount", flat=True)), [5])

    def test_two_household_authors_with_overlapping_members_finish_without_lock_cycle(self):
        own = make_family("Other race author", parents=[{"username": "second-race-author", "is_staff": True}],
                          children=[{"username": "second-race-child"}])
        other_actor, other_child = own.parents[0], own.children[0]
        canonical = self.load_duplicate()
        second_source = QuestDefinition.objects.create(**{**self.values, "name": "Second pair"}, created_by=other_actor)
        second_canonical = QuestDefinition.objects.create(**{**self.values, "name": "Second pair"})
        at = timezone.now()
        for child in (self.child, other_child):
            for definition in (self.source, second_source):
                ChallengeGoal.objects.create(user=child, family=child.family, catalog_definition=definition,
                    is_catalog=True, name=definition.name, metric="count", target=1, timezone_name="America/Phoenix",
                    starts_at=at, ends_at=at+timedelta(days=7))
        first = self.service.preview_reconciliation(self.actor, self.source.pk, canonical.pk, uuid4())
        second = self.service.preview_reconciliation(other_actor, second_source.pk, second_canonical.pk, uuid4())
        barrier = Barrier(2)

        def publish(actor, preview):
            barrier.wait(timeout=4)
            return self.service.publish_reconciliation(actor, preview["preview_id"], preview["content_digest"])

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, lambda actor=actor, preview=preview: publish(actor, preview))
                       for actor, preview in ((self.actor, first), (other_actor, second))]
            self.assertTrue(all(future.result(timeout=15)["published_at"] for future in futures))
        self.assertEqual(set(ChallengeGoal.objects.values_list("catalog_definition_id", flat=True)),
                         {canonical.pk, second_canonical.pk})

    def test_ordinary_publisher_cannot_invert_catalog_and_reconciliation_receipt_locks(self):
        canonical = self.load_duplicate()
        preview = self.service.preview_reconciliation(self.actor, self.source.pk, canonical.pk, uuid4())
        catalog_held, reconciliation_waiting = Event(), Event()
        catalog_lock = publication._catalog_lock

        def ordinary_catalog_lock():
            catalog_lock()
            catalog_held.set()
            if not reconciliation_waiting.wait(5):
                raise TimeoutError("Reconciliation did not request catalog admission")

        def reconciliation_catalog_lock():
            reconciliation_waiting.set()
            catalog_lock()

        with TemporaryDirectory(prefix="abby-identity-lock-") as directory:
            Path(directory, "items.yaml").write_text("items: []\n")
            with patch.object(publication, "_catalog_lock", side_effect=ordinary_catalog_lock), \
                    patch.object(self.service, "_catalog_lock", side_effect=reconciliation_catalog_lock), \
                    ThreadPoolExecutor(max_workers=2) as pool:
                ordinary = pool.submit(self.worker, lambda: publication.publish_content_pack(
                    directory, "qa-" + preview["preview_id"].replace("-", ""), self.actor,
                    preview["preview_id"], preview["content_digest"]))
                canonical_publish = None
                try:
                    self.assertTrue(catalog_held.wait(4))
                    canonical_publish = pool.submit(self.worker, lambda: self.service.publish_reconciliation(
                        self.actor, preview["preview_id"], preview["content_digest"]))
                    # A different operation cannot adopt this receipt. It must
                    # reject safely, rather than wait in an inverse lock cycle.
                    with self.assertRaises(ContentPackError):
                        ordinary.result(timeout=15)
                    self.assertTrue(canonical_publish.result(timeout=15)["published_at"])
                finally:
                    reconciliation_waiting.set()
                    if canonical_publish is not None:
                        # Drain even when the original lock-order regression fails.
                        try:
                            canonical_publish.result(timeout=15)
                        except Exception:
                            pass
