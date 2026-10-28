"""Real PostgreSQL capacity and archival fences, without holding compute locks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from apps.accounts.models import User
from apps.rpg.authoring_archive import AuthoringArchiveConflict, set_archived
from apps.rpg.content.loader import ContentPackError
from apps.rpg.models import AuthoringArchiveReceipt, ProgressionComparison, ProgressionExperiment
from apps.rpg.progression import experiments
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks.")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthoringArchiveConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "archive-concurrent", "is_staff": True}]).parents[0]
        self.data = {"name": "Concurrent notebook", "hypothesis": "Capacity remains bounded.",
                     "config": {"horizon_days": 30, "trials": 1}, "candidate_daily_coins": 100, "targets": []}

    def worker(self, operation):
        close_old_connections()
        try:
            return operation(User.objects.get(pk=self.actor.pk))
        finally:
            connection.close()

    def test_worker_closes_its_physical_connection_after_success(self):
        physical_connections = []
        expected = object()

        def succeed(actor):
            physical_connections.append(connection.connection)
            self.assertEqual(actor.pk, self.actor.pk)
            return expected

        # Keep the executor and driver connection alive through the assertion.
        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                self.assertIs(pool.submit(self.worker, succeed).result(timeout=15), expected)
                self.assertEqual(len(physical_connections), 1)
                self.assertTrue(physical_connections[0].closed)
            finally:
                pool.submit(lambda: connection.close()).result(timeout=15)

    def test_worker_closes_its_physical_connection_after_error(self):
        physical_connections = []
        expected = RuntimeError("Synthetic archive worker failure")

        def fail(actor):
            physical_connections.append(connection.connection)
            self.assertEqual(actor.pk, self.actor.pk)
            raise expected

        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                with self.assertRaises(RuntimeError) as raised:
                    pool.submit(self.worker, fail).result(timeout=15)
                self.assertIs(raised.exception, expected)
                self.assertEqual(len(physical_connections), 1)
                self.assertTrue(physical_connections[0].closed)
            finally:
                pool.submit(lambda: connection.close()).result(timeout=15)

    def test_concurrent_creates_cannot_exceed_active_capacity(self):
        for _ in range(19):
            experiments.create_experiment(self.actor, self.data)
        start = Barrier(2)

        def create(actor):
            start.wait(timeout=10)
            try:
                experiments.create_experiment(actor, self.data)
                return "created"
            except ContentPackError:
                return "full"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.worker(create), range(2)))
        self.assertCountEqual(results, ["created", "full"])
        self.assertEqual(ProgressionExperiment.objects.filter(actor=self.actor, is_archived=False).count(), 20)

    def test_concurrent_archive_requests_bump_revision_once(self):
        row = experiments.create_experiment(self.actor, self.data)
        start = Barrier(2)

        def archive(actor):
            start.wait(timeout=10)
            try:
                set_archived(actor, "experiment", row["id"], 1, True, uuid4(), confirmation=True)
                return "archived"
            except AuthoringArchiveConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.worker(archive), range(2)))
        self.assertCountEqual(results, ["archived", "conflict"])
        self.assertEqual(ProgressionExperiment.objects.get(pk=row["id"]).revision, 2)
        self.assertEqual(AuthoringArchiveReceipt.objects.count(), 1)

    def test_archive_completes_while_comparison_is_detached_and_save_then_conflicts(self):
        row = experiments.create_experiment(self.actor, self.data)
        prepared, resume = Event(), Event()

        def compare(actor):
            evidence = experiments.prepare_comparison(actor, row["id"], 1)
            prepared.set()
            self.assertTrue(resume.wait(timeout=15))
            try:
                experiments.record_comparison(actor, row["id"], 1, evidence)
                return "saved"
            except experiments.ExperimentConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.worker, compare)
            try:
                self.assertTrue(prepared.wait(timeout=15))
                result = set_archived(self.actor, "experiment", row["id"], 1, True, uuid4(), confirmation=True)
                self.assertTrue(result["is_archived"])
            finally:
                resume.set()
            self.assertEqual(future.result(timeout=15), "conflict")
        self.assertFalse(ProgressionComparison.objects.filter(experiment_id=row["id"]).exists())
