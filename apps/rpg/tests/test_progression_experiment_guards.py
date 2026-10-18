"""Independent request and evidence guards for the private experiment notebook."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"])
class ProgressionExperimentGuardTests(APITestCase):
    url = "/api/rpg/progression-lab/experiments/"

    def setUp(self):
        cache.clear()
        self.parent = make_family(parents=[{"username": "guard-designer", "is_staff": True}]).parents[0]
        self.client.force_authenticate(self.parent)
        self.body = {
            "name": "Independent guard evidence", "hypothesis": "Guard saved evidence.",
            "config": {"horizon_days": 30, "trials": 1}, "candidate_daily_coins": 100,
            "targets": [{"metric": "closing_coins_p50", "min": 0}],
        }
        response = self.client.post(self.url, self.body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.experiment = response.json()
        self.detail = f"{self.url}{self.experiment['id']}/"
        response = self.client.post(self.detail + "compare/", {"revision": 1}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.comparison = response.json()

    def decision(self, **changes):
        return {
            "revision": 1, "comparison_id": self.comparison["id"], "outcome": "keep_testing",
            "rationale": "Check the saved comparison before further design.",
            "next_action": "Specify and simulate a promise-preserving candidate.",
            "review_on": "2099-01-01", **changes,
        }

    def test_nonstring_outcomes_are_invalid_requests_instead_of_server_errors(self):
        self.client.raise_request_exception = False
        for outcome in ([], {}, ["ready_for_design"], None, True, 1):
            with self.subTest(outcome=outcome):
                response = self.client.post(self.detail + "decisions/", self.decision(outcome=outcome), format="json")
                self.assertEqual(response.status_code, 400, response.content[:100])

    def test_experiment_detail_marks_changed_rules_stale_without_reopening_full_reports(self):
        with patch("apps.rpg.progression.experiments.rules_fingerprint", return_value="changed-rules"):
            response = self.client.get(self.detail)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["comparisons"][0]["stale"])

    def test_evaluator_changes_block_ready_for_design_with_existing_passing_targets(self):
        self.assertEqual(self.comparison["evaluation"]["status"], "pass")
        with patch("apps.rpg.progression.experiments.feedback_fingerprint", return_value="changed-evaluator"):
            response = self.client.post(self.detail + "decisions/", self.decision(outcome="ready_for_design"), format="json")
        self.assertEqual(response.status_code, 409, response.content)

    def test_permission_revoked_during_simulation_prevents_saving_the_result(self):
        from apps.accounts.models import User
        from apps.rpg.models import ProgressionComparison
        from apps.rpg.progression.engine import simulate_progression

        def revoke(*args, **kwargs):
            User.objects.filter(pk=self.parent.pk).update(is_staff=False)
            return simulate_progression(*args, **kwargs)

        with patch("apps.rpg.progression.experiments.simulate_progression", side_effect=revoke):
            response = self.client.post(self.detail + "compare/", {"revision": 1}, format="json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(ProgressionComparison.objects.count(), 1)

    def test_comparison_capacity_is_rechecked_after_simulation_before_persistence(self):
        from apps.rpg.models import ProgressionComparison
        from apps.rpg.progression.engine import simulate_progression

        original = ProgressionComparison.objects.get(pk=self.comparison["id"])
        filled = False

        def fill_capacity(*args, **kwargs):
            nonlocal filled
            if not filled:
                ProgressionComparison.objects.create(
                    experiment_id=original.experiment_id, experiment_revision=1,
                    inputs=original.inputs, control=original.control, candidate=original.candidate,
                    evaluation=original.evaluation, binding=original.binding,
                )
                filled = True
            return simulate_progression(*args, **kwargs)

        with patch("apps.rpg.progression.experiments.MAX_COMPARISONS", 2), patch(
            "apps.rpg.progression.experiments.simulate_progression", side_effect=fill_capacity,
        ):
            response = self.client.post(self.detail + "compare/", {"revision": 1}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(ProgressionComparison.objects.count(), 2)

    def test_full_notebook_rejects_new_experiments_without_catalog_reads_or_rows(self):
        from apps.rpg.models import ProgressionExperiment

        with patch("apps.rpg.progression.experiments.MAX_EXPERIMENTS", 1), patch(
            "apps.rpg.progression.experiments.load_catalog",
        ) as snapshot:
            response = self.client.post(self.url, self.body, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(ProgressionExperiment.objects.count(), 1)
        snapshot.assert_not_called()

    def test_failed_simulation_keeps_saved_evidence_and_cannot_create_a_decision(self):
        from apps.rpg.models import ProgressionComparison, ProgressionDecision

        with patch("apps.rpg.progression.experiments.load_catalog", side_effect=ValueError("Oversized global catalog")):
            response = self.client.post(self.detail + "compare/", {"revision": 1}, format="json")
        self.assertEqual(response.status_code, 503, response.content)
        saved = ProgressionComparison.objects.get(pk=self.comparison["id"])
        self.assertEqual(saved.control, self.comparison["control"])
        self.assertEqual(ProgressionComparison.objects.count(), 1)
        self.assertEqual(ProgressionDecision.objects.count(), 0)
