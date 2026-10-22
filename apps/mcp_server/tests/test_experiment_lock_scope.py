"""Expensive MCP notebook evidence runs outside household locks (real PostgreSQL).

Comparison simulations and checkpoint aggregates take seconds. Holding the
Family/member locks through them stalled unrelated same-family activity such as
a child's reading page or a login. Identical retries must still wait for the
first attempt and replay it without another computation, quota, comparison or
checkpoint, and current authority is rechecked before anything is saved.
"""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Event
import time
from typing import get_type_hints
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import User
from apps.families.models import Family
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.models import MCPExperimentMutationReceipt
# Import before any patch so the tools module never binds a patched function.
from apps.mcp_server.tools import progression_experiments
from apps.reading.services import authorized_reading
from apps.rpg.models import ProgressionComparison, ProgressionExperiment, ProgressionObservation
from apps.rpg.progression import experiments
from config.tests.factories import make_family


SIMULATION = "apps.rpg.progression.experiments.simulate_progression"
AGGREGATE = "apps.rpg.progression.observations.economy_observations"
REPORT = "apps.rpg.progression.experiments.get_comparison"
NATIVE_DETAIL = "apps.rpg.progression.experiments._detail"
OBSERVATION_READ = "apps.mcp_server.tools.progression_experiments.economy_observations"
CATALOG = "apps.rpg.progression.experiments.load_catalog"
QUOTA = "apps.mcp_server.tools.progression_experiments._comparison_quota"
BOTH_GRANTS = ("mcp:author", "mcp:read")


def _paused(path):
    """Patch ``path`` so its first call waits until the test releases it."""
    module_path, name = path.rsplit(".", 1)
    original = getattr(import_module(module_path), name)
    entered, release, calls = Event(), Event(), []

    def wrapper(*args, **kwargs):
        calls.append(path)
        if len(calls) == 1:
            entered.set()
            if not release.wait(timeout=30):
                raise AssertionError("The test never released the paused computation.")
        return original(*args, **kwargs)

    return patch(path, side_effect=wrapper), entered, release, calls


def _counted(path):
    module_path, name = path.rsplit(".", 1)
    original = getattr(import_module(module_path), name)
    calls = []

    def wrapper(*args, **kwargs):
        calls.append(path)
        return original(*args, **kwargs)

    return patch(path, side_effect=wrapper), calls


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row and advisory locks required")
class ExperimentEvidenceLockScopeTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Lock scope experiments", parents=[
            {"username": "lock-scope-designer", "is_staff": True},
        ], children=[{"username": "lock-scope-reader"}])
        self.actor, self.child = family.parents[0], family.children[0]
        self.recipe = {
            "name": "Lock scope", "hypothesis": "Synthetic paired design",
            "config": {"horizon_days": 30, "trials": 1, "seed": 99}, "candidate_daily_coins": 100, "targets": [],
        }
        saved = experiments.create_experiment(self.actor, self.recipe)
        self.experiment_id, self.revision = saved["id"], saved["revision"]

    def body(self, **changes):
        return {"experiment_id": self.experiment_id, "revision": self.revision, "request_id": uuid4(), **changes}

    def invoke(self, name, params, *, scopes=("mcp:author",)):
        handler = getattr(progression_experiments, name)
        inputs = get_type_hints(handler)["params"]
        with override_user(User.objects.get(pk=self.actor.pk), scopes=frozenset(scopes)):
            return handler(inputs(**params))

    def submit(self, executor, name, params, **kwargs):
        def run():
            close_old_connections()
            try:
                return self.invoke(name, params, **kwargs)
            finally:
                connections.close_all()

        return executor.submit(run)

    def family_lock_is_free(self):
        try:
            with transaction.atomic():
                Family.objects.select_for_update(no_key=True, nowait=True).get(pk=self.actor.family_id)
        except DatabaseError:
            return False
        return True

    def child_reading_is_free(self):
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '1s'")
                with authorized_reading(self.child, self.child):
                    pass
        except DatabaseError:
            return False
        return True

    def wait_for_blocked_lock(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM pg_locks lock JOIN pg_stat_activity activity ON activity.pid = lock.pid "
                    "WHERE NOT lock.granted AND activity.datname = current_database()"
                )
                if cursor.fetchone()[0]:
                    return True
            time.sleep(0.05)
        return False

    def receipts(self, operation):
        return MCPExperimentMutationReceipt.objects.filter(operation=operation)

    def revoke_with_timeout(self):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '1s'")
            User.objects.filter(pk=self.actor.pk).update(is_staff=False)

    def held_request_locks(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()")
            return cursor.fetchone()[0]

    def test_comparison_simulation_leaves_unrelated_family_activity_unblocked(self):
        patcher, entered, release, _ = _paused(SIMULATION)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "compare_progression_experiment", self.body())
            try:
                self.assertTrue(entered.wait(timeout=30), "The comparison never reached its simulation.")
                family_free = self.family_lock_is_free()
                reading_free = self.child_reading_is_free()
            finally:
                release.set()
            result = future.result(timeout=60)
        self.assertTrue(family_free, "The family row stayed locked through the simulation.")
        self.assertTrue(reading_free, "A child's reading page waited for the simulation.")
        self.assertEqual(str(ProgressionComparison.objects.get().pk), result["id"])
        self.assertEqual(self.receipts("compare_progression_experiment").count(), 1)

    def test_checkpoint_aggregate_leaves_unrelated_family_activity_unblocked(self):
        patcher, entered, release, _ = _paused(AGGREGATE)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "capture_progression_observation", self.body(), scopes=BOTH_GRANTS)
            try:
                self.assertTrue(entered.wait(timeout=30), "The checkpoint never reached its aggregate.")
                family_free = self.family_lock_is_free()
                reading_free = self.child_reading_is_free()
            finally:
                release.set()
            result = future.result(timeout=60)
        self.assertTrue(family_free, "The family row stayed locked through the aggregate.")
        self.assertTrue(reading_free, "A child's reading page waited for the aggregate.")
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(ProgressionObservation.objects.count(), 1)
        self.assertEqual(self.receipts("capture_progression_observation").count(), 1)

    def test_saved_report_is_read_for_the_response_outside_household_locks(self):
        patcher, entered, release, _ = _paused(REPORT)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "compare_progression_experiment", self.body())
            try:
                self.assertTrue(entered.wait(timeout=30), "The comparison never read its saved report.")
                family_free = self.family_lock_is_free()
            finally:
                release.set()
            result = future.result(timeout=60)
        self.assertTrue(family_free, "The family row stayed locked while the large report was read.")
        self.assertEqual(result["freshness"], "current")

    def test_authority_revoked_while_reading_the_response_returns_nothing_and_retry_replays(self):
        body = self.body()
        patcher, entered, release, _ = _paused(REPORT)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "compare_progression_experiment", body)
            try:
                self.assertTrue(entered.wait(timeout=30))
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '1s'")
                    User.objects.filter(pk=self.actor.pk).update(is_staff=False)
            finally:
                release.set()
            with self.assertRaises(MCPPermissionDenied):
                future.result(timeout=60)
        # The committed result and its receipt remain for an authorized retry.
        self.assertEqual(ProgressionComparison.objects.count(), 1)
        self.assertEqual(self.receipts("compare_progression_experiment").count(), 1)
        User.objects.filter(pk=self.actor.pk).update(is_staff=True)
        simulations_patch, simulations = _counted(SIMULATION)
        quota_patch, quota_calls = _counted(QUOTA)
        with simulations_patch, quota_patch:
            replay = self.invoke("compare_progression_experiment", body)
        self.assertEqual(replay["id"], str(ProgressionComparison.objects.get().pk))
        self.assertEqual((simulations, quota_calls), ([], []))

    def test_observation_read_aggregate_leaves_unrelated_family_activity_unblocked(self):
        patcher, entered, release, _ = _paused(OBSERVATION_READ)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "get_progression_observations", {}, scopes=("mcp:read",))
            try:
                self.assertTrue(entered.wait(timeout=30), "The read never reached its aggregate.")
                family_free = self.family_lock_is_free()
                reading_free = self.child_reading_is_free()
            finally:
                release.set()
            result = future.result(timeout=60)
        self.assertTrue(family_free, "The family row stayed locked through the observation aggregate.")
        self.assertTrue(reading_free, "A child's reading page waited for the observation aggregate.")
        self.assertIn("automatic_sources", result)

    def test_authority_revoked_during_observation_read_returns_no_aggregate(self):
        patcher, entered, release, _ = _paused(OBSERVATION_READ)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "get_progression_observations", {}, scopes=("mcp:read",))
            try:
                self.assertTrue(entered.wait(timeout=30))
                self.revoke_with_timeout()
            finally:
                release.set()
            with self.assertRaises(MCPPermissionDenied):
                future.result(timeout=60)

    def test_replayed_report_is_read_outside_household_locks(self):
        body = self.body()
        first = self.invoke("compare_progression_experiment", body)
        patcher, entered, release, _ = _paused(REPORT)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "compare_progression_experiment", body)
            try:
                self.assertTrue(entered.wait(timeout=30), "The replay never read its saved report.")
                family_free = self.family_lock_is_free()
            finally:
                release.set()
            replay = future.result(timeout=60)
        self.assertTrue(family_free, "The family row stayed locked while the replayed report was read.")
        self.assertEqual(replay, first)
        self.assertEqual(ProgressionComparison.objects.count(), 1)

    def test_result_deleted_while_reading_the_response_returns_nothing_and_keeps_the_tombstone(self):
        body = self.body()
        patcher, entered, release, _ = _paused(REPORT)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "compare_progression_experiment", body)
            try:
                self.assertTrue(entered.wait(timeout=30))
                ProgressionComparison.objects.all().delete()
            finally:
                release.set()
            with self.assertRaises(MCPNotFoundError):
                future.result(timeout=60)
        self.assertEqual(self.receipts("compare_progression_experiment").count(), 1)
        simulations_patch, simulations = _counted(SIMULATION)
        with simulations_patch, self.assertRaises(MCPNotFoundError):
            self.invoke("compare_progression_experiment", body)
        self.assertEqual(simulations, [], "A deleted result's request UUID must not recompute it.")
        self.assertFalse(ProgressionComparison.objects.exists())

    def test_response_failure_after_commit_replays_without_more_work_and_releases_the_request_lock(self):
        body = self.body()
        with patch(REPORT, side_effect=RuntimeError("Synthetic response failure")), self.assertRaises(RuntimeError):
            self.invoke("compare_progression_experiment", body)
        self.assertEqual(self.held_request_locks(), 0, "A failed response left its request lock on a reused connection.")
        self.assertEqual(ProgressionComparison.objects.count(), 1)
        self.assertEqual(self.receipts("compare_progression_experiment").count(), 1)
        simulations_patch, simulations = _counted(SIMULATION)
        quota_patch, quota_calls = _counted(QUOTA)
        with simulations_patch, quota_patch:
            replay = self.invoke("compare_progression_experiment", body)
        self.assertEqual(replay["id"], str(ProgressionComparison.objects.get().pk))
        self.assertEqual((simulations, quota_calls), ([], []))
        self.assertEqual(self.held_request_locks(), 0)

    def test_native_checkpoint_detail_stays_inside_its_save_locks(self):
        patcher, entered, release, _ = _paused(NATIVE_DETAIL)

        def capture():
            close_old_connections()
            try:
                return experiments.capture_observation(User.objects.get(pk=self.actor.pk), self.experiment_id,
                                                       self.revision)
            finally:
                connections.close_all()

        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(capture)
            try:
                self.assertTrue(entered.wait(timeout=30), "Native capture never built its detail.")
                with self.assertRaises(DatabaseError, msg="Revocation interleaved with the native checkpoint detail."):
                    self.revoke_with_timeout()
            finally:
                release.set()
            detail = future.result(timeout=60)
        self.assertEqual(len(detail["observations"]), 1)

    def test_notebook_tools_snapshot_the_catalog_outside_household_locks(self):
        comparison = self.invoke("compare_progression_experiment", self.body())
        tools = {
            "get_progression_experiment": {"experiment_id": self.experiment_id},
            "get_progression_comparison": {"experiment_id": self.experiment_id, "comparison_id": comparison["id"]},
            "record_progression_decision": {
                **self.body(), "comparison_id": comparison["id"], "outcome": "keep_testing",
                "rationale": "Synthetic design note.", "next_action": "Review the paired report.", "review_on": "2099-01-01",
            },
            "save_progression_experiment": {**self.body(), **self.recipe, "candidate_daily_coins": 90},
        }
        for name, params in tools.items():
            with self.subTest(tool=name):
                patcher, entered, release, catalogs = _paused(CATALOG)
                with patcher, ThreadPoolExecutor(max_workers=1) as executor:
                    future = self.submit(executor, name, params)
                    try:
                        self.assertTrue(entered.wait(timeout=30), f"{name} never checked catalog freshness.")
                        family_free = self.family_lock_is_free()
                    finally:
                        release.set()
                    future.result(timeout=60)
                self.assertTrue(family_free, f"{name} rebuilt the catalog while holding the family row.")
                self.assertEqual(len(catalogs), 1, f"{name} should snapshot the catalog once per request.")

    def test_comparison_read_tool_reads_the_report_outside_household_locks(self):
        comparison = self.invoke("compare_progression_experiment", self.body())
        params = {"experiment_id": self.experiment_id, "comparison_id": comparison["id"]}
        patcher, entered, release, _ = _paused(REPORT)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "get_progression_comparison", params)
            try:
                self.assertTrue(entered.wait(timeout=30))
                family_free = self.family_lock_is_free()
            finally:
                release.set()
            report = future.result(timeout=60)
        self.assertTrue(family_free, "The family row stayed locked while the saved report was read.")
        self.assertEqual(report, comparison)

    def test_authority_revoked_during_comparison_read_returns_no_report(self):
        comparison = self.invoke("compare_progression_experiment", self.body())
        params = {"experiment_id": self.experiment_id, "comparison_id": comparison["id"]}
        patcher, entered, release, _ = _paused(REPORT)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "get_progression_comparison", params)
            try:
                self.assertTrue(entered.wait(timeout=30))
                self.revoke_with_timeout()
            finally:
                release.set()
            with self.assertRaises(MCPPermissionDenied):
                future.result(timeout=60)

    def test_receipt_checks_lock_saved_reports_without_loading_them(self):
        from apps.mcp_server.experiment_retries import _saved_result

        comparison = self.invoke("compare_progression_experiment", self.body())
        with transaction.atomic(), CaptureQueriesContext(connection) as queries:
            _saved_result(User.objects.get(pk=self.actor.pk), self.experiment_id, "comparison", comparison["id"])
        report_reads = [query["sql"] for query in queries.captured_queries if "rpg_progressioncomparison" in query["sql"]]
        self.assertEqual(len(report_reads), 1)
        self.assertNotIn('"control"', report_reads[0], "The existence check loaded the multi-MB report.")
        self.assertIn("FOR NO KEY UPDATE", report_reads[0])

    def test_identical_comparison_retry_waits_and_replays_without_more_work_or_quota(self):
        body = self.body()
        patcher, entered, release, simulations = _paused(SIMULATION)
        quota_patch, quota_calls = _counted(QUOTA)
        with patcher, quota_patch, ThreadPoolExecutor(max_workers=2) as executor:
            first = self.submit(executor, "compare_progression_experiment", body)
            try:
                self.assertTrue(entered.wait(timeout=30))
                second = self.submit(executor, "compare_progression_experiment", body)
                self.assertTrue(self.wait_for_blocked_lock(), "The identical retry did not wait for the first attempt.")
            finally:
                release.set()
            results = [first.result(timeout=60), second.result(timeout=60)]
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(simulations), 2, "Only the first attempt simulates its control and candidate.")
        self.assertEqual(len(quota_calls), 1, "The replay must not spend comparison quota.")
        self.assertEqual(ProgressionComparison.objects.count(), 1)
        self.assertEqual(self.receipts("compare_progression_experiment").count(), 1)

    def test_identical_checkpoint_retry_saves_one_observation(self):
        body = self.body()
        patcher, entered, release, aggregates = _paused(AGGREGATE)
        with patcher, ThreadPoolExecutor(max_workers=2) as executor:
            first = self.submit(executor, "capture_progression_observation", body, scopes=BOTH_GRANTS)
            try:
                self.assertTrue(entered.wait(timeout=30))
                second = self.submit(executor, "capture_progression_observation", body, scopes=BOTH_GRANTS)
                self.assertTrue(self.wait_for_blocked_lock())
            finally:
                release.set()
            results = [first.result(timeout=60), second.result(timeout=60)]
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(aggregates), 1)
        self.assertEqual(ProgressionObservation.objects.count(), 1)
        self.assertEqual(self.receipts("capture_progression_observation").count(), 1)

    def test_authority_revoked_during_simulation_saves_nothing(self):
        patcher, entered, release, _ = _paused(SIMULATION)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "compare_progression_experiment", self.body())
            try:
                self.assertTrue(entered.wait(timeout=30))
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '1s'")
                    User.objects.filter(pk=self.actor.pk).update(is_staff=False)
            finally:
                release.set()
            with self.assertRaises(MCPPermissionDenied):
                future.result(timeout=60)
        self.assertFalse(ProgressionComparison.objects.exists())
        self.assertFalse(self.receipts("compare_progression_experiment").exists())

    def test_revision_saved_during_simulation_conflicts_without_saving_stale_evidence(self):
        patcher, entered, release, _ = _paused(SIMULATION)
        with patcher, ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor, "compare_progression_experiment", self.body())
            try:
                self.assertTrue(entered.wait(timeout=30))
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '1s'")
                    experiments.save_experiment(self.actor, self.experiment_id, self.revision,
                                                {**self.recipe, "candidate_daily_coins": 75})
            finally:
                release.set()
            with self.assertRaises(MCPValidationError) as error:
                future.result(timeout=60)
        self.assertEqual(error.exception.code, "progression_experiment_conflict")
        self.assertEqual(ProgressionExperiment.objects.get().revision, self.revision + 1)
        self.assertFalse(ProgressionComparison.objects.exists())
        self.assertFalse(self.receipts("compare_progression_experiment").exists())

    def test_failed_computation_keeps_no_receipt_or_request_lock_and_a_retry_completes(self):
        body = self.body()
        with patch("apps.rpg.progression.experiments.load_catalog", side_effect=ValueError("Synthetic catalog outage")), \
                self.assertRaises(MCPValidationError) as error:
            self.invoke("compare_progression_experiment", body)
        self.assertEqual(error.exception.code, "progression_catalog_unavailable")
        self.assertFalse(self.receipts("compare_progression_experiment").exists())
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()")
            self.assertEqual(cursor.fetchone()[0], 0, "A failed attempt left its request lock on a reused connection.")
        retried = self.invoke("compare_progression_experiment", body)
        self.assertEqual(str(ProgressionComparison.objects.get().pk), retried["id"])
        self.assertEqual(self.receipts("compare_progression_experiment").count(), 1)
