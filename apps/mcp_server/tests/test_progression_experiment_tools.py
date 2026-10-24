"""Saved Lab evidence has an author-scoped, retry-safe MCP lifecycle."""
import json
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import patch
from uuid import UUID, uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError

from apps.accounts.models import User
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.server import mcp
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.experiment_views import ComparisonThrottle
from apps.rpg.models import (
    ProgressionComparison, ProgressionDecision, ProgressionExperiment, ProgressionObservation, UserInventory,
)
from config.tests.factories import make_family


EXPERIMENT_TOOLS = {
    "list_progression_experiments", "get_progression_experiment", "create_progression_experiment",
    "save_progression_experiment", "compare_progression_experiment", "get_progression_comparison",
    "record_progression_decision", "capture_progression_observation", "get_progression_observations",
}


class ProgressionExperimentRegistryTests(SimpleTestCase):
    def test_saved_notebook_workflow_is_exposed_with_explicit_results(self):
        registered = {entry.name: entry for entry in mcp._tool_manager.list_tools()}
        self.assertFalse(EXPERIMENT_TOOLS - registered.keys(),
                         f"Missing MCP workflows: {EXPERIMENT_TOOLS - registered.keys()}")
        for name in EXPERIMENT_TOOLS:
            with self.subTest(name=name):
                self.assertIsNotNone(registered[name].output_schema)

    def test_outputs_explain_saved_evidence_and_grant_redaction(self):
        for name, field in (
            ("list_progression_experiments", "experiments"),
            ("get_progression_experiment", "observations_redacted"),
            ("create_progression_experiment", "revision"),
            ("save_progression_experiment", "comparisons"),
            ("compare_progression_experiment", "freshness"),
            ("get_progression_comparison", "control"),
            ("record_progression_decision", "decisions"),
            ("capture_progression_observation", "observations"),
            ("get_progression_observations", "automatic_sources"),
        ):
            with self.subTest(tool=name):
                entry = mcp._tool_manager.get_tool(name)
                self.assertIsNotNone(entry)
                self.assertIn(field, entry.fn_metadata.output_schema["properties"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProgressionExperimentToolTests(TestCase):
    def setUp(self):
        cache.clear()
        own = make_family("MCP experiment family", parents=[
            {"username": "experiment-author", "is_staff": True},
            {"username": "experiment-coparent", "is_staff": True},
            {"username": "experiment-nonstaff"},
        ], children=[{"username": "experiment-child", "is_staff": True}])
        self.actor, self.coparent, self.nonstaff = own.parents
        self.child = own.children[0]
        foreign = make_family("Foreign MCP experiment family", parents=[
            {"username": "experiment-foreign", "is_staff": True},
        ], children=[{"username": "experiment-foreign-child"}])
        self.foreign, self.foreign_child = foreign.parents[0], foreign.children[0]
        self.body = {
            "request_id": uuid4(), "name": "Preserve the first reward",
            "hypothesis": "A bounded income policy keeps a regular routine useful.",
            "config": {"horizon_days": 30, "trials": 1, "seed": 4321},
            "candidate_daily_coins": 100,
            "targets": [{"metric": "closing_coins_p50", "min": 0}],
        }

    def invoke(self, name, params=None, *, actor=None, scopes=("mcp:author",)):
        from apps.mcp_server.tools import progression_experiments

        handler = getattr(progression_experiments, name)
        inputs = get_type_hints(handler)["params"]
        with override_user(actor or self.actor, scopes=frozenset(scopes)):
            return handler(inputs(**(params or {})))

    def wire(self, name, params=None, *, scopes=("mcp:author",), **arguments):
        with override_user(self.actor, scopes=frozenset(scopes)):
            result = async_to_sync(mcp.call_tool)(name, {"params": params or {}, **arguments})
        if isinstance(result, tuple):
            return SimpleNamespace(isError=False, structuredContent=result[1])
        return result

    def create(self, **changes):
        return self.invoke("create_progression_experiment", {**self.body, "request_id": uuid4(), **changes})

    def compare(self, experiment, **changes):
        return self.invoke("compare_progression_experiment", {
            "experiment_id": experiment["id"], "revision": experiment["revision"], "request_id": uuid4(), **changes,
        })

    def decision(self, experiment, comparison, **changes):
        return {"experiment_id": experiment["id"], "revision": experiment["revision"],
                "comparison_id": comparison["id"], "request_id": uuid4(), "outcome": "keep_testing",
                "rationale": "The observed results need more design work.", "next_action": "Review promised rewards.",
                "review_on": "2099-01-01", **changes}

    def test_complete_saved_workflow_survives_reload_and_has_no_live_reward_writes(self):
        before = (User.objects.count(), CoinLedger.objects.count(), UserInventory.objects.count())
        experiment = self.create()
        comparison = self.compare(experiment)
        saved = self.invoke("record_progression_decision", self.decision(experiment, comparison))
        reopened = self.invoke("get_progression_experiment", {"experiment_id": experiment["id"]})
        report = self.invoke("get_progression_comparison", {
            "experiment_id": experiment["id"], "comparison_id": comparison["id"],
        })
        self.assertEqual(reopened, saved)
        self.assertEqual(report, comparison)
        self.assertEqual(saved["decisions"][0]["comparison_id"], comparison["id"])
        self.assertEqual(comparison["control"]["config"]["seed"], comparison["candidate"]["config"]["seed"])
        self.assertEqual(comparison["control"]["catalog"], comparison["candidate"]["catalog"])
        self.assertEqual(comparison["candidate"]["config"]["reward_budget"], {"daily_coins": 100})
        self.assertEqual(before, (User.objects.count(), CoinLedger.objects.count(), UserInventory.objects.count()))

    def test_wire_lifecycle_validates_concrete_results_and_save_confirmation(self):
        created = self.wire("create_progression_experiment", {**self.body, "request_id": str(uuid4())})
        self.assertFalse(created.isError, created)
        experiment = created.structuredContent
        compared = self.wire("compare_progression_experiment", {
            "experiment_id": experiment["id"], "revision": 1, "request_id": str(uuid4()),
        })
        self.assertFalse(compared.isError, compared)
        self.assertEqual(compared.structuredContent["freshness"], "current")
        decision_body = self.decision(experiment, compared.structuredContent, request_id=str(uuid4()))
        decided = self.wire("record_progression_decision", decision_body)
        self.assertFalse(decided.isError, decided)
        self.assertEqual(len(decided.structuredContent["decisions"]), 1)
        save = {**self.body, "request_id": str(uuid4()), "experiment_id": experiment["id"], "revision": 1}
        denied = self.wire("save_progression_experiment", save)
        self.assertEqual(denied.structuredContent["error"]["code"], "confirmation_required")
        saved = self.wire("save_progression_experiment", save, confirmation=True)
        self.assertFalse(saved.isError, saved)
        self.assertEqual(saved.structuredContent["revision"], 2)

    def test_create_and_save_retries_reuse_current_record_without_revisions_or_duplicates(self):
        first = self.invoke("create_progression_experiment", self.body)
        again = self.invoke("create_progression_experiment", self.body)
        self.assertEqual(again, first)
        updated_body = {**self.body, "request_id": uuid4(), "experiment_id": first["id"],
                        "revision": first["revision"], "candidate_daily_coins": 75}
        saved = self.invoke("save_progression_experiment", updated_body)
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(self.invoke("save_progression_experiment", updated_body), saved)
        self.assertEqual(self.invoke("create_progression_experiment", self.body), saved)
        self.assertEqual(ProgressionExperiment.objects.count(), 1)
        self.assertEqual(ProgressionExperiment.objects.get().revision, 2)
        for name, body in (("create_progression_experiment", self.body), ("save_progression_experiment", updated_body)):
            with self.subTest(tool=name), self.assertRaises(MCPValidationError) as error:
                self.invoke(name, {**body, "name": "Changed details"})
            self.assertEqual(error.exception.code, "idempotency_conflict")

    def test_omitted_optional_policy_fields_preserve_a_saved_quota_candidate(self):
        budget = {"daily_launches": 2, "daily_items": 3}
        experiment = self.create(candidate_daily_coins=None, candidate_policy="expedition_limits",
                                 candidate_expedition_budget=budget)
        saved = self.invoke("save_progression_experiment", {
            **self.body, "request_id": uuid4(), "experiment_id": experiment["id"], "revision": 1,
            "candidate_daily_coins": None,
        })
        self.assertEqual(saved["candidate_policy"], "expedition_limits")
        self.assertEqual(saved["candidate_expedition_budget"], budget)

    def test_comparison_retries_skip_native_work_and_shared_throttle(self):
        experiment = self.create()
        body = {"experiment_id": experiment["id"], "revision": 1, "request_id": uuid4()}
        first = self.invoke("compare_progression_experiment", body)
        with patch("apps.rpg.progression.experiments.compare_experiment", side_effect=AssertionError("Comparison replayed")), patch(
            "apps.rpg.progression.experiments.prepare_comparison", side_effect=AssertionError("Comparison replayed"),
        ), patch(
            "apps.rpg.progression.experiments.record_comparison", side_effect=AssertionError("Comparison saved again"),
        ), patch(
            "apps.mcp_server.tools.progression_experiments._comparison_quota", side_effect=AssertionError("Replay consumed quota"),
        ):
            self.assertEqual(self.invoke("compare_progression_experiment", body), first)
        self.assertEqual(ProgressionComparison.objects.count(), 1)

    def test_native_comparison_throttle_is_shared_and_rate_error_is_retryable(self):
        experiment = self.create()
        with patch.object(ComparisonThrottle, "rate", "1/min"):
            self.assertTrue(ComparisonThrottle().allow_request(SimpleNamespace(user=self.actor), None))
            with self.assertRaises(MCPValidationError) as error:
                self.compare(experiment)
        self.assertEqual(error.exception.code, "rate_limited")
        self.assertTrue(error.exception.retryable)
        self.assertEqual(ProgressionComparison.objects.count(), 0)

    def test_large_native_comparison_is_retry_safe_without_generic_response_cap(self):
        experiment = self.create(config={"horizon_days": 365, "trials": 1, "seed": 4321})
        body = {"experiment_id": experiment["id"], "revision": 1, "request_id": uuid4()}
        report = self.invoke("compare_progression_experiment", body)
        self.assertGreater(len(json.dumps(report).encode()), 256 * 1024)
        self.assertEqual(self.invoke("compare_progression_experiment", body), report)
        self.assertEqual(ProgressionComparison.objects.count(), 1)

    def test_native_evidence_size_limit_rolls_back_comparison_and_retry_receipt(self):
        from apps.mcp_server.models import MCPExperimentMutationReceipt

        experiment = self.create()
        with patch("apps.rpg.progression.experiments.MAX_EVIDENCE_BYTES", 1), self.assertRaises(MCPValidationError):
            self.compare(experiment)
        self.assertEqual(ProgressionComparison.objects.count(), 0)
        self.assertEqual(MCPExperimentMutationReceipt.objects.filter(operation="compare_progression_experiment").count(), 0)

    def test_decision_reads_saved_reports_without_loading_their_json(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        with CaptureQueriesContext(connection) as queries:
            self.invoke("record_progression_decision", self.decision(experiment, comparison))
        report_reads = [query["sql"] for query in queries.captured_queries
                        if "rpg_progressioncomparison" in query["sql"] and query["sql"].lstrip().upper().startswith("SELECT")]
        self.assertTrue(report_reads)
        self.assertFalse([sql for sql in report_reads if '"control"' in sql],
                         "Recording a decision loaded the multi-MB saved report.")

    def test_decision_retries_append_once_and_changed_details_conflict(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        body = self.decision(experiment, comparison)
        first = self.invoke("record_progression_decision", body)
        self.assertEqual(self.invoke("record_progression_decision", body), first)
        self.assertEqual(ProgressionDecision.objects.count(), 1)
        with self.assertRaises(MCPValidationError) as error:
            self.invoke("record_progression_decision", {**body, "outcome": "revise"})
        self.assertEqual(error.exception.code, "idempotency_conflict")

    def test_revision_edit_retains_history_and_blocks_new_stale_evidence_decisions(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        self.invoke("save_progression_experiment", {**self.body, "request_id": uuid4(),
                    "experiment_id": experiment["id"], "revision": 1, "candidate_daily_coins": 75})
        old = self.invoke("get_progression_comparison", {
            "experiment_id": experiment["id"], "comparison_id": comparison["id"],
        })
        self.assertTrue(old["stale"])
        self.assertEqual(old["candidate"], comparison["candidate"])
        with self.assertRaises(MCPValidationError) as error:
            self.invoke("record_progression_decision", self.decision(experiment, comparison, revision=2))
        self.assertEqual(error.exception.code, "progression_experiment_conflict")
        self.assertEqual(ProgressionDecision.objects.count(), 0)

    def test_catalog_drift_and_unavailable_history_retain_explicit_freshness(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        with patch("apps.rpg.progression.experiments.rules_fingerprint", return_value="changed"):
            result = self.wire("record_progression_decision", self.decision(experiment, comparison))
            self.assertEqual(result.structuredContent["error"]["code"], "progression_experiment_conflict")
        with patch("apps.rpg.progression.experiments.load_catalog", side_effect=ValueError("Catalog is too large.")):
            history = self.invoke("get_progression_comparison", {
                "experiment_id": experiment["id"], "comparison_id": comparison["id"],
            })
            self.assertEqual(history["freshness"], "unavailable")
            self.assertEqual(history["control"], comparison["control"])
            result = self.wire("record_progression_decision", self.decision(experiment, comparison))
        self.assertEqual(result.structuredContent["error"]["code"], "progression_catalog_unavailable")
        self.assertTrue(result.structuredContent["error"]["retryable"])

    def test_notebook_is_private_to_actor_and_family_with_indistinguishable_misses(self):
        experiment = self.create()
        for actor in (self.coparent, self.foreign):
            with self.subTest(actor=actor.pk):
                self.assertEqual(self.invoke("list_progression_experiments", actor=actor)["experiments"], [])
                for identifier in (experiment["id"], uuid4()):
                    with self.assertRaisesRegex(MCPNotFoundError, "Experiment not found"):
                        self.invoke("get_progression_experiment", {"experiment_id": identifier}, actor=actor)

    def test_summaries_have_bounded_pagination_and_no_observation_payloads(self):
        expected = {self.create(name=f"Hypothesis {index}")["id"] for index in range(4)}
        first = self.invoke("list_progression_experiments", {"limit": 2})
        second = self.invoke("list_progression_experiments", {"limit": 2, "after": first["next_after"]})
        self.assertEqual({row["id"] for row in first["experiments"] + second["experiments"]}, expected)
        self.assertEqual((first["total"], second["total"]), (4, 4))
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertIsNone(second["next_after"])
        self.assertTrue(all("observations" not in row for row in first["experiments"] + second["experiments"]))

    def test_author_only_details_and_mutations_never_query_household_checkpoints(self):
        experiment = self.create()
        self.invoke("capture_progression_observation", {
            "experiment_id": experiment["id"], "revision": 1, "request_id": uuid4(),
        }, scopes=("mcp:author", "mcp:read"))
        comparison = self.compare(experiment)
        with CaptureQueriesContext(connection) as queries:
            detail = self.invoke("get_progression_experiment", {"experiment_id": experiment["id"]})
            decision = self.invoke("record_progression_decision", self.decision(experiment, comparison))
            saved = self.invoke("save_progression_experiment", {**self.body, "request_id": uuid4(),
                "experiment_id": experiment["id"], "revision": 1})
        self.assertTrue(all(result["observations_redacted"] for result in (detail, decision, saved)))
        self.assertTrue(all(result["observations"] == [] for result in (detail, decision, saved)))
        self.assertFalse(any("rpg_progressionobservation" in query["sql"].lower() for query in queries))
        readable = self.invoke("get_progression_experiment", {"experiment_id": experiment["id"]},
                               scopes=("mcp:author", "mcp:read"))
        self.assertFalse(readable["observations_redacted"])
        self.assertEqual(len(readable["observations"]), 1)

    def test_observation_checkpoint_retries_preserve_old_snapshot_after_ledger_changes(self):
        self.child.is_staff = False
        self.child.save(update_fields=["is_staff"])
        experiment = self.create()
        body = {"experiment_id": experiment["id"], "revision": 1, "request_id": uuid4()}
        first = self.invoke("capture_progression_observation", body, scopes=("mcp:author", "mcp:read"))
        self.assertEqual(first["observations"][0]["status"], "insufficient_evidence")
        CoinService.award_coins(self.child, 37, CoinLedger.Reason.ADJUSTMENT, source=CoinLedger.Source.COIN_POUCH)
        replay = self.invoke("capture_progression_observation", body, scopes=("mcp:author", "mcp:read"))
        self.assertEqual(replay["observations"], first["observations"])
        current = self.invoke("get_progression_observations", scopes=("mcp:read",))
        self.assertEqual(current["automatic_sources"]["coins"], 37)
        self.assertFalse(current["policy"]["is_live_experiment"])
        self.assertEqual(ProgressionObservation.objects.count(), 1)
        self.assertEqual(CoinLedger.objects.count(), 1)

    def test_household_observations_never_include_other_family_activity(self):
        self.child.is_staff = False
        self.child.save(update_fields=["is_staff"])
        CoinService.award_coins(self.child, 11, CoinLedger.Reason.ADJUSTMENT, source=CoinLedger.Source.COIN_POUCH)
        CoinService.award_coins(self.foreign_child, 999, CoinLedger.Reason.ADJUSTMENT, source=CoinLedger.Source.COIN_POUCH)
        observed = self.invoke("get_progression_observations", scopes=("mcp:read",))
        self.assertEqual(observed["automatic_sources"]["coins"], 11)
        self.assertNotIn("experiment-child", json.dumps(observed))
        self.assertNotIn("experiment-foreign-child", json.dumps(observed))

    def test_deleted_results_leave_request_tombstones_without_recreation(self):
        body = {**self.body, "request_id": uuid4()}
        experiment = self.invoke("create_progression_experiment", body)
        ProgressionExperiment.objects.get(pk=experiment["id"]).delete()
        with self.assertRaises(MCPNotFoundError):
            self.invoke("create_progression_experiment", body)
        self.assertEqual(ProgressionExperiment.objects.count(), 0)

    def test_deleted_comparison_decision_and_observation_cannot_be_recreated_by_replay(self):
        experiment = self.create()
        comparison_body = {"experiment_id": experiment["id"], "revision": 1, "request_id": uuid4()}
        comparison = self.invoke("compare_progression_experiment", comparison_body)
        decision_body = self.decision(experiment, comparison)
        self.invoke("record_progression_decision", decision_body)
        ProgressionDecision.objects.all().delete()
        with self.assertRaises(MCPNotFoundError):
            self.invoke("record_progression_decision", decision_body)
        observation_body = {"experiment_id": experiment["id"], "revision": 1, "request_id": uuid4()}
        self.invoke("capture_progression_observation", observation_body, scopes=("mcp:author", "mcp:read"))
        ProgressionObservation.objects.all().delete()
        with self.assertRaises(MCPNotFoundError):
            self.invoke("capture_progression_observation", observation_body, scopes=("mcp:author", "mcp:read"))
        ProgressionComparison.objects.all().delete()
        with self.assertRaises(MCPNotFoundError):
            self.invoke("compare_progression_experiment", comparison_body)

    def test_staff_parent_and_current_permissions_are_required_even_with_stale_objects(self):
        experiment = self.create()
        for actor in (self.nonstaff, self.child):
            with self.subTest(actor=actor.pk), self.assertRaises(MCPPermissionDenied):
                self.invoke("get_progression_experiment", {"experiment_id": experiment["id"]}, actor=actor)
        users = User.objects.filter(pk=self.actor.pk)
        original = {"role": "parent", "is_staff": True, "is_active": True, "family_id": self.actor.family_id}
        for revoked in ({"role": "child"}, {"is_staff": False}, {"is_active": False}, {"family_id": self.foreign.family_id}):
            users.update(**revoked)
            try:
                with self.subTest(revoked=revoked), patch(
                    "apps.rpg.progression.experiments.get_experiment", side_effect=AssertionError("Stale actor reached service"),
                ) as service, self.assertRaises(MCPPermissionDenied):
                    self.invoke("get_progression_experiment", {"experiment_id": experiment["id"]})
                service.assert_not_called()
            finally:
                users.update(**original)

    def test_scopes_and_explicit_checkpoint_read_grant_are_enforced_on_wire(self):
        experiment = self.create()
        for scopes in (("mcp:catalog",), ("mcp:read",), ("mcp:publish",)):
            with self.subTest(scopes=scopes):
                result = self.wire("get_progression_experiment", {"experiment_id": experiment["id"]}, scopes=scopes)
                self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")
        result = self.wire("capture_progression_observation", {
            "experiment_id": experiment["id"], "revision": 1, "request_id": str(uuid4()),
        })
        self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")
        self.assertEqual(ProgressionObservation.objects.count(), 0)
        result = self.wire("get_progression_observations", scopes=("mcp:author",))
        self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")

    def test_input_selectors_client_evidence_boolean_limits_and_unknown_fields_are_rejected(self):
        for changes in ({"user_id": self.child.pk}, {"family_id": self.actor.family_id},
                        {"candidate_daily_coins": True}, {"config": {"user_id": self.child.pk}},
                        {"config": {"trials": True}}, {"targets": [{"metric": "journal_body", "min": 0}]},
                        {"report": {}}, {"config": {"horizon_days": 365, "trials": 40}}):
            with self.subTest(changes=changes), self.assertRaises((ValidationError, MCPValidationError)):
                self.invoke("create_progression_experiment", {**self.body, **changes})
        for params in ({"limit": True}, {"limit": 21}):
            with self.subTest(params=params), self.assertRaises(ValidationError):
                self.invoke("list_progression_experiments", params)
        with self.assertRaises(ValidationError):
            self.invoke("get_progression_observations", {"family_id": self.foreign.family_id}, scopes=("mcp:read",))

    def test_comparison_detail_requires_evidence_from_selected_experiment(self):
        experiment = self.create()
        other = self.create()
        comparison = self.compare(experiment)
        with self.assertRaises(MCPNotFoundError):
            self.invoke("get_progression_comparison", {"experiment_id": other["id"], "comparison_id": comparison["id"]})
        with self.assertRaises(MCPNotFoundError):
            self.invoke("record_progression_decision", self.decision(other, comparison))

    def test_receipts_contain_result_identity_without_hypotheses_or_observation_payloads(self):
        from apps.mcp_server.models import MCPExperimentMutationReceipt

        experiment = self.create()
        self.compare(experiment)
        receipts = list(MCPExperimentMutationReceipt.objects.values())
        self.assertEqual(len(receipts), 2)
        encoded = json.dumps(receipts, default=str)
        self.assertNotIn(self.body["hypothesis"], encoded)
        self.assertNotIn("payload", receipts[0])
        self.assertNotIn("response", receipts[0])
        self.assertEqual({row["experiment_id"] for row in receipts}, {UUID(experiment["id"])})
