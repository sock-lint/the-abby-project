"""A saved comparison binds both arms to one installed incubation snapshot."""
from copy import deepcopy
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.rpg.models import ProgressionComparison, ProgressionDecision
from apps.rpg.progression import engine, experiments
from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"], PET_INCUBATION_DURATION_SECONDS=86400)
class IncubationExperimentTests(APITestCase):
    url = "/api/rpg/progression-lab/experiments/"

    def setUp(self):
        cache.clear()
        parent = make_family(parents=[{"username": "incubation-designer", "is_staff": True}]).parents[0]
        self.client.force_authenticate(parent)
        response = self.client.post(self.url, {
            "name": "Stable care rules", "hypothesis": "Compare Coin rules under the same installed care policy.",
            "config": {"horizon_days": 30, "trials": 1, "seed": 123},
            "candidate_daily_coins": 100, "candidate_policy": "commitment100", "targets": [],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.detail = f"{self.url}{response.json()['id']}/"

    def compare(self):
        response = self.client.post(self.detail + "compare/", {"revision": 1}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_one_frozen_incubation_snapshot_binds_both_arms_despite_settings_changing_between_them(self):
        captured = []
        actual_simulate = engine.simulate_progression

        def change_between_arms(*args, **kwargs):
            captured.append(kwargs.get("incubation_policy"))
            if len(captured) == 2:
                with override_settings(PET_INCUBATION_DURATION_SECONDS=60):
                    return actual_simulate(*args, **kwargs)
            return actual_simulate(*args, **kwargs)

        with patch.object(experiments, "simulate_progression", side_effect=change_between_arms), patch.object(
            experiments, "_binding", wraps=experiments._binding,
        ) as bind:
            comparison = self.compare()

        self.assertEqual(len(captured), 2)
        self.assertIsNotNone(captured[0])
        self.assertIs(captured[0], captured[1])
        self.assertIs(bind.call_args.kwargs["incubation_policy"], captured[0])
        self.assertEqual(captured[0]["duration_seconds"], 86400)
        with self.assertRaises(TypeError):
            captured[0]["duration_seconds"] = 1
        for arm in (comparison["control"], comparison["candidate"]):
            self.assertEqual(arm["pet_incubation_policy"], dict(captured[0]))
            self.assertEqual(arm["rules_fingerprint"], comparison["binding"]["rules_fingerprint"])
        self.assertEqual(comparison["binding"]["rules_fingerprint"], engine.rules_fingerprint(incubation_policy=captured[0]))
        self.assertFalse(comparison["stale"])

    def test_real_duration_drift_marks_old_evidence_stale_and_blocks_decisions_without_rewriting_reports(self):
        comparison = self.compare()
        saved = ProgressionComparison.objects.get(pk=comparison["id"])
        frozen = deepcopy((saved.control, saved.candidate, saved.binding, saved.evaluation))
        comparison_url = self.detail + f"comparisons/{comparison['id']}/"

        with override_settings(PET_INCUBATION_DURATION_SECONDS=60):
            self.assertNotEqual(engine.rules_fingerprint(), comparison["binding"]["rules_fingerprint"])
            old = self.client.get(comparison_url)
            self.assertEqual(old.status_code, 200, old.content)
            self.assertTrue(old.json()["stale"])
            self.assertEqual(old.json()["freshness"], "stale")
            self.assertTrue(self.client.get(self.detail).json()["comparisons"][0]["stale"])
            decision = self.client.post(self.detail + "decisions/", {
                "revision": 1, "comparison_id": comparison["id"], "outcome": "keep_testing",
                "rationale": "The installed care duration changed.",
                "next_action": "Rerun the comparison under the new installed care policy.",
                "review_on": "2099-01-01",
            }, format="json")
            self.assertEqual(decision.status_code, 409, decision.content)

        self.assertEqual(old.json()["control"], comparison["control"])
        self.assertEqual(old.json()["candidate"], comparison["candidate"])
        saved.refresh_from_db()
        self.assertEqual((saved.control, saved.candidate, saved.binding, saved.evaluation), frozen)
        self.assertFalse(ProgressionDecision.objects.exists())
        self.assertFalse(self.client.get(comparison_url).json()["stale"])
