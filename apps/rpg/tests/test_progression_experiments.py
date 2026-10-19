"""Saved design evidence is private, reproducible and never publication authority."""
from unittest.mock import patch
from uuid import UUID

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"])
class ProgressionExperimentTests(APITestCase):
    url = "/api/rpg/progression-lab/experiments/"

    def setUp(self):
        cache.clear()
        family = make_family("Experiment owner", parents=[
            {"username": "designer", "is_staff": True},
            {"username": "coparent", "is_staff": True},
            {"username": "parent"},
        ], children=[{"username": "child", "is_staff": True}])
        self.designer, self.coparent, self.parent = family.parents
        self.child = family.children[0]
        self.other = make_family("Other experiment family", parents=[
            {"username": "other-designer", "is_staff": True},
        ]).parents[0]
        self.client.force_authenticate(self.designer)
        self.body = {
            "name": "100 Coins, regular routine",
            "hypothesis": "Reduce automatic income while keeping the first reward reachable.",
            "config": {"horizon_days": 30, "trials": 1, "seed": 123},
            "candidate_daily_coins": 100,
            "targets": [{"metric": "closing_coins_p50", "min": 0}],
        }

    def create(self):
        response = self.client.post(self.url, self.body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def detail_url(self, experiment):
        return f"{self.url}{experiment['id']}/"

    def compare(self, experiment):
        response = self.client.post(self.detail_url(experiment) + "compare/", {"revision": experiment["revision"]}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_staff_parent_only_and_no_household_target_selectors(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        for actor in (self.parent, self.child):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, self.body, format="json").status_code, 403)
        self.client.force_authenticate(self.designer)
        self.assertEqual(self.client.get(self.url, {"user_id": self.child.pk}).status_code, 400)
        response = self.client.get(self.url, {"_abby_session": "synthetic", "_abby_retry": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_experiment_survives_reload_and_is_author_and_family_scoped(self):
        experiment = self.create()
        detail = self.client.get(self.detail_url(experiment)).json()
        self.assertEqual(detail["config"]["seed"], 123)
        self.assertEqual(detail["config"]["reward_budget"], {"daily_coins": None})
        for actor in (self.coparent, self.other):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.url).json()["experiments"], [])
            self.assertEqual(self.client.get(self.detail_url(experiment)).status_code, 404)
            self.assertEqual(self.client.post(self.detail_url(experiment) + "compare/", {"revision": 1}, format="json").status_code, 404)

    def test_config_and_evidence_fields_are_strict(self):
        for changes in ({"candidate_daily_coins": True}, {"candidate_daily_coins": -1},
                        {"report": {}}, {"config": {"user_id": self.child.pk}},
                        {"targets": [{"metric": "journal_body", "min": 0}]}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(self.url, {**self.body, **changes}, format="json").status_code, 400)

    def test_compare_generates_same_seed_evidence_with_one_catalog_and_no_domain_writes(self):
        from apps.accounts.models import User
        from apps.rewards.models import CoinLedger
        from apps.rpg.models import UserInventory
        from apps.rpg.progression.catalog import load_catalog

        experiment = self.create()
        before = (User.objects.count(), CoinLedger.objects.count(), UserInventory.objects.count())
        with patch("apps.rpg.progression.experiments.load_catalog", wraps=load_catalog) as snapshot:
            comparison = self.compare(experiment)
        self.assertEqual(snapshot.call_count, 1)
        self.assertEqual(comparison["control"]["config"]["reward_budget"], {"daily_coins": None})
        self.assertEqual(comparison["candidate"]["config"]["reward_budget"], {"daily_coins": 100})
        self.assertEqual(comparison["control"]["config"]["seed"], comparison["candidate"]["config"]["seed"])
        self.assertEqual(comparison["control"]["catalog"], comparison["candidate"]["catalog"])
        self.assertEqual(before, (User.objects.count(), CoinLedger.objects.count(), UserInventory.objects.count()))
        reopened = self.client.get(self.detail_url(experiment) + f"comparisons/{comparison['id']}/")
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["candidate"], comparison["candidate"])

    def test_edits_keep_old_comparisons_but_make_them_stale(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        response = self.client.patch(self.detail_url(experiment), {**self.body, "revision": 1, "candidate_daily_coins": 75}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["revision"], 2)
        self.assertTrue(response.json()["comparisons"][0]["stale"])
        self.assertEqual(self.client.patch(self.detail_url(experiment), {**self.body, "revision": 1}, format="json").status_code, 409)
        old = self.client.get(self.detail_url(experiment) + f"comparisons/{comparison['id']}/").json()
        self.assertEqual(old["candidate"]["config"]["reward_budget"]["daily_coins"], 100)
        self.assertTrue(old["stale"])

    def test_rule_drift_preserves_report_but_blocks_decision(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        with patch("apps.rpg.progression.experiments.rules_fingerprint", return_value="new-rules"):
            old = self.client.get(self.detail_url(experiment) + f"comparisons/{comparison['id']}/").json()
            self.assertTrue(old["stale"])
            result = self.client.post(self.detail_url(experiment) + "decisions/", self.decision(comparison), format="json")
            self.assertEqual(result.status_code, 409)
        self.assertEqual(old["control"], comparison["control"])

    def test_unavailable_current_catalog_keeps_old_evidence_readable_and_blocks_decisions(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        with patch("apps.rpg.progression.experiments.load_catalog", side_effect=ValueError("Global catalog exceeds its limit.")):
            response = self.client.get(self.detail_url(experiment) + f"comparisons/{comparison['id']}/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["stale"])
            self.assertEqual(response.json()["freshness"], "unavailable")
            self.assertEqual(response.json()["control"], comparison["control"])
            detail = self.client.get(self.detail_url(experiment)).json()
            self.assertTrue(detail["comparisons"][0]["stale"])
            self.assertEqual(self.client.post(self.detail_url(experiment) + "decisions/", self.decision(comparison), format="json").status_code, 503)

    def test_oversized_evidence_is_rejected_without_replacing_prior_comparison(self):
        from apps.rpg.models import ProgressionComparison
        experiment = self.create()
        original = self.compare(experiment)
        with patch("apps.rpg.progression.experiments.MAX_EVIDENCE_BYTES", 1):
            response = self.client.post(self.detail_url(experiment) + "compare/", {"revision": 1}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(ProgressionComparison.objects.values_list("id", flat=True)), [UUID(original["id"])])

    def decision(self, comparison, **changes):
        return {"revision": 1, "comparison_id": comparison["id"], "outcome": "keep_testing",
                "rationale": "The income hypothesis needs a promise-safe issuance model.",
                "next_action": "Draft new expedition rewards, preserve all owned pouch values.",
                "review_on": "2099-01-01", **changes}

    def test_decision_has_evidence_action_and_review_date_and_is_append_only(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        response = self.client.post(self.detail_url(experiment) + "decisions/", self.decision(comparison), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        saved = response.json()["decisions"][0]
        self.assertEqual(saved["comparison_id"], comparison["id"])
        self.assertIn("preserve", saved["next_action"])
        self.assertEqual(self.client.get(self.detail_url(experiment)).json()["decisions"], [saved])
        self.assertEqual(self.client.patch(self.detail_url(experiment) + "decisions/", {}, format="json").status_code, 405)

    def test_decisions_reject_cross_experiment_evidence_empty_action_and_unconfigured_approval(self):
        experiment = self.create()
        comparison = self.compare(experiment)
        other = self.create()
        result = self.client.post(self.detail_url(other) + "decisions/", self.decision(comparison), format="json")
        self.assertEqual(result.status_code, 404)
        for changes in ({"next_action": ""}, {"review_on": "2020-01-01"}, {"outcome": "publish"}):
            self.assertEqual(self.client.post(self.detail_url(experiment) + "decisions/", self.decision(comparison, **changes), format="json").status_code, 400)
        response = self.client.patch(self.detail_url(experiment), {**self.body, "revision": 1, "targets": []}, format="json")
        comparison = self.compare(response.json())
        result = self.client.post(self.detail_url(experiment) + "decisions/", self.decision(comparison, revision=2, outcome="ready_for_design"), format="json")
        self.assertEqual(result.status_code, 400)

    def test_revision_changed_during_simulation_does_not_save_stale_evidence(self):
        from apps.rpg.models import ProgressionExperiment, ProgressionComparison
        from apps.rpg.progression.engine import simulate_progression

        experiment = self.create()
        def change_revision(*args, **kwargs):
            ProgressionExperiment.objects.filter(pk=experiment["id"]).update(revision=2)
            return simulate_progression(*args, **kwargs)
        with patch("apps.rpg.progression.experiments.simulate_progression", side_effect=change_revision):
            result = self.client.post(self.detail_url(experiment) + "compare/", {"revision": 1}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(ProgressionComparison.objects.count(), 0)

    def test_oversized_scenario_rejected_before_catalog_read(self):
        with patch("apps.rpg.progression.experiments.load_catalog") as catalog:
            result = self.client.post(self.url, {**self.body, "config": {"horizon_days": 365, "trials": 40}}, format="json")
        self.assertEqual(result.status_code, 400)
        catalog.assert_not_called()

    def test_observation_endpoint_is_separate_and_has_no_target_selectors(self):
        url = "/api/rpg/progression-lab/observations/"
        self.assertEqual(self.client.get(url, {"family_id": self.other.family_id}).status_code, 400)
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_observation_checkpoints_preserve_before_and_after_accounting_without_client_results(self):
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService

        self.child.is_staff = False
        self.child.save(update_fields=["is_staff"])
        experiment = self.create()
        url = self.detail_url(experiment) + "observations/"
        first = self.client.post(url, {"revision": 1}, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        before = first.json()["observations"][0]
        self.assertEqual(before["status"], "insufficient_evidence")
        self.assertFalse(before["payload"]["policy"]["is_live_experiment"])
        CoinService.award_coins(self.child, 40, CoinLedger.Reason.ADJUSTMENT, source=CoinLedger.Source.COIN_POUCH)
        second = self.client.post(url, {"revision": 1}, format="json")
        self.assertEqual(second.status_code, 201, second.content)
        snapshots = second.json()["observations"]
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(next(row for row in snapshots if row["id"] == before["id"]), before)
        after = next(row for row in snapshots if row["id"] != before["id"])
        self.assertEqual(after["payload"]["automatic_sources"]["coins"], 40)
        self.assertEqual(after["status"], "observations_available")
        self.assertEqual(after["binding"]["scope"], "own_family_recent_children")
        self.assertEqual(self.client.post(url, {"revision": 1, "payload": {}}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"revision": 0}, format="json").status_code, 409)
        self.client.force_authenticate(self.coparent)
        self.assertEqual(self.client.post(url, {"revision": 1}, format="json").status_code, 404)
