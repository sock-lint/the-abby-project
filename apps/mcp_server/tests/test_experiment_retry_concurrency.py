"""Real PostgreSQL locks serialize duplicate notebook and evidence requests."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.mcp_server.experiment_retries import experiment_mutation_once
from apps.mcp_server.models import MCPExperimentMutationReceipt
from apps.rpg.models import ProgressionComparison, ProgressionExperiment
from apps.rpg.progression import experiments
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks required")
class ExperimentRetryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = make_family("Concurrent experiments", parents=[{"username": "concurrent-designer", "is_staff": True}])
        self.actor = family.parents[0]
        self.body = {"name": "One hypothesis", "hypothesis": "Synthetic paired design",
                     "config": {"horizon_days": 30, "trials": 1, "seed": 123},
                     "candidate_daily_coins": 100, "targets": []}

    def _compete(self, operation, create, serialize):
        request_id, start = uuid4(), Barrier(2)

        def run():
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.actor.pk)
                start.wait(timeout=10)
                return experiment_mutation_once(
                    actor=actor, operation=operation, request_id=request_id,
                    payload=self.body, create=create, serialize=serialize,
                )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(MCPExperimentMutationReceipt.objects.count(), 1)
        return results[0]

    def test_concurrent_identical_creates_save_one_experiment(self):
        def create(actor):
            saved = experiments.create_experiment(actor, self.body, include_observations=False)
            experiment = ProgressionExperiment.objects.get(pk=saved["id"])
            return experiment, "experiment", experiment.pk

        result = self._compete("create_progression_experiment", create,
                               lambda actor, exp, kind, result_id: {"id": str(exp.pk)})
        self.assertEqual(ProgressionExperiment.objects.count(), 1)
        self.assertTrue(ProgressionExperiment.objects.filter(pk=result["id"]).exists())

    def test_concurrent_identical_comparisons_save_one_evidence_record(self):
        saved = experiments.create_experiment(self.actor, self.body)

        def create(actor):
            result = experiments.compare_experiment(actor, saved["id"], saved["revision"])
            return ProgressionExperiment.objects.get(pk=saved["id"]), "comparison", result["id"]

        result = self._compete("compare_progression_experiment", create,
                               lambda actor, exp, kind, result_id: {"id": str(result_id)})
        self.assertEqual(ProgressionComparison.objects.count(), 1)
        self.assertTrue(ProgressionComparison.objects.filter(pk=result["id"]).exists())
