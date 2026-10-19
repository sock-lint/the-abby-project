"""Annual notebook evidence retains the complete native report within its cap."""
from io import StringIO
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.rpg.content.loader import ContentPack
from apps.rpg.models import ProgressionComparison
from apps.rpg.progression.engine import simulate_progression
from apps.rpg.progression.experiments import ExperimentUnavailable, MAX_EVIDENCE_BYTES, _compact_report, _restore_report
from config.tests.factories import make_family


class EvidenceStorageCompatibilityTests(SimpleTestCase):
    def test_legacy_and_unrecognized_report_shapes_are_not_rewritten(self):
        for report in (None, [], "old evidence", {}, {"trace": []},
                       {"trace": [{"day": 1}, {"day": 2, "later_metric": 0}]},
                       {"trace": [{"day": 1}, None]}, {"trace": [{1: 2}]},
                       {"trace": {"storage_format": "unknown"}}):
            with self.subTest(report=report):
                self.assertIs(_compact_report(report), report)
                self.assertIs(_restore_report(report), report)

    def test_invalid_columnar_evidence_fails_closed_without_losing_values(self):
        for changes in ({"columns": None}, {"columns": ["day", "day"]}, {"columns": [None]},
                        {"rows": None}, {"rows": [[1, 2]]}, {"rows": [False]}, {"unexpected": 1}):
            trace = {"storage_format": "trace_columns_v1", "columns": ["day"], "rows": [[1]], **changes}
            with self.subTest(changes=changes), self.assertRaises(ExperimentUnavailable):
                _restore_report({"trace": trace})


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None)
class AnnualProgressionEvidenceTests(APITestCase):
    url = "/api/rpg/progression-lab/experiments/"

    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def setUp(self):
        cache.clear()
        parent = make_family(parents=[{"username": "annual-designer", "is_staff": True}]).parents[0]
        self.client.force_authenticate(parent)

    def test_annual_commitment_and_launch_comparisons_preserve_complete_native_evidence(self):
        for policy in ("commitment100", "expedition_limits"):
            with self.subTest(policy=policy):
                cache.clear()
                config = {
                    "horizon_days": 365, "trials": 1, "seed": 123,
                    "economy": {"enabled": True, "offers": [{
                        "key": "outing", "label": "An outing", "kind": "real_world",
                        "coin_price": 100, "repeat_every_days": 7,
                        "family_cost_cents": 500,
                    }]},
                }
                if policy == "expedition_limits":
                    config["reward_commitment"] = {"enabled": True}
                created = self.client.post(self.url, {
                    "name": "Annual purchasing comparison", "hypothesis": "Audit a full year without discarding evidence.",
                    "config": config, "candidate_policy": policy,
                    "candidate_daily_coins": 100 if policy == "commitment100" else None,
                    "candidate_expedition_budget": {} if policy == "commitment100" else {"daily_launches": 3},
                    "targets": [{"metric": "closing_coins_p50", "min": 0}],
                }, format="json")
                self.assertEqual(created.status_code, 201, created.content)
                detail = f"{self.url}{created.json()['id']}/"
                reports = []

                def capture_report(*args, **kwargs):
                    report = simulate_progression(*args, **kwargs)
                    reports.append(report)
                    return report

                with patch("apps.rpg.progression.experiments.simulate_progression", side_effect=capture_report):
                    response = self.client.post(detail + "compare/", {"revision": 1}, format="json")
                self.assertEqual(len(reports), 2)
                self.assertGreater(len(json.dumps(reports).encode()), MAX_EVIDENCE_BYTES)
                self.assertEqual(response.status_code, 201, response.content)
                comparison = response.json()
                # Native coverage includes tuple skill weights; JSON responses
                # have always represented those as arrays, independently of storage.
                self.assertEqual([comparison["control"], comparison["candidate"]], json.loads(json.dumps(reports)))
                for report in reports:
                    self.assertEqual(len(report["trace"]), 365)
                    self.assertEqual(len(report["economy"]["months"]), 12)
                    self.assertTrue(report["journey"]["events"])
                    self.assertTrue(report["audit"])

                saved = ProgressionComparison.objects.get(pk=comparison["id"])
                stored = {key: getattr(saved, key) for key in ("inputs", "control", "candidate", "evaluation", "binding")}
                self.assertLessEqual(len(json.dumps(stored).encode()), MAX_EVIDENCE_BYTES)
                reopened = self.client.get(detail + f"comparisons/{comparison['id']}/")
                self.assertEqual(reopened.status_code, 200, reopened.content)
                self.assertEqual(reopened.json(), comparison)
                with patch("apps.rpg.progression.experiments.load_catalog", side_effect=ValueError("Catalog unavailable")):
                    historical = self.client.get(detail + f"comparisons/{comparison['id']}/")
                self.assertEqual(historical.status_code, 200, historical.content)
                self.assertEqual(historical.json()["control"], comparison["control"])
                self.assertEqual(historical.json()["candidate"], comparison["candidate"])
                self.assertEqual(historical.json()["freshness"], "unavailable")
                decision = self.client.post(detail + "decisions/", {
                    "revision": 1, "comparison_id": comparison["id"], "outcome": "keep_testing",
                    "rationale": "All annual evidence is available for review.",
                    "next_action": "Review full-year rewards and purchasing before changing live rules.",
                    "review_on": "2099-01-01",
                }, format="json")
                self.assertEqual(decision.status_code, 201, decision.content)
