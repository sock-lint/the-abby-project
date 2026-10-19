"""Quota comparisons isolate expedition supply while preserving Coin rules."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"])
class ExpeditionLimitExperimentTests(APITestCase):
    url = "/api/rpg/progression-lab/experiments/"

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(make_family(parents=[{
            "username": "quota-designer", "is_staff": True,
        }]).parents[0])
        self.body = {
            "name": "Share expedition supply", "hypothesis": "Compare item and launch quotas under the same Coin policy.",
            "config": {"horizon_days": 30, "trials": 1}, "candidate_daily_coins": None,
            "candidate_policy": "expedition_limits",
            "candidate_expedition_budget": {"daily_launches": 2, "daily_items": 3}, "targets": [],
        }

    def test_saved_quota_pair_preserves_each_selected_coin_policy(self):
        for coin_config in ({}, {"reward_budget": {"daily_coins": 75}}, {"reward_commitment": {"enabled": True}}):
            cache.clear()
            with self.subTest(coin_config=coin_config):
                response = self.client.post(self.url, {**self.body, "config": {**self.body["config"], **coin_config}}, format="json")
                self.assertEqual(response.status_code, 201, response.content)
                saved = response.json()
                result = self.client.post(f"{self.url}{saved['id']}/compare/", {"revision": 1}, format="json")
                self.assertEqual(result.status_code, 201, result.content)
                pair = result.json()
                self.assertEqual(pair["inputs"]["candidate_policy"], "expedition_limits")
                self.assertIsNone(pair["inputs"]["candidate_daily_coins"])
                self.assertEqual(pair["control"]["config"]["expedition_budget"], {"daily_launches": None, "daily_items": None})
                self.assertEqual(pair["candidate"]["config"]["expedition_budget"], self.body["candidate_expedition_budget"])
                for key in ("reward_budget", "reward_commitment"):
                    self.assertEqual(pair["control"]["config"][key], pair["candidate"]["config"][key])
                for key, value in coin_config.items():
                    self.assertEqual(pair["control"]["config"][key], value)

    def test_policy_requires_null_coin_placeholder_and_bounded_nonempty_quota(self):
        for changes in (
            {"candidate_daily_coins": 100},
            {"candidate_expedition_budget": {"daily_launches": None, "daily_items": None}},
            {"candidate_expedition_budget": None}, {"candidate_expedition_budget": []},
            {"candidate_expedition_budget": {"daily_launches": True}},
            {"candidate_expedition_budget": {"daily_launches": 16}},
            {"candidate_expedition_budget": {"daily_items": 46}},
            {"candidate_expedition_budget": {"daily_items": 1, "family_id": 1}},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(self.url, {**self.body, **changes}, format="json").status_code, 400)

    def test_old_coin_policies_cannot_ignore_quotas_and_old_clients_keep_stored_fields(self):
        old = {**self.body, "candidate_policy": "envelope", "candidate_daily_coins": 100}
        self.assertEqual(self.client.post(self.url, old, format="json").status_code, 400)
        old.pop("candidate_expedition_budget")
        saved = self.client.post(self.url, old, format="json")
        self.assertEqual(saved.status_code, 201, saved.content)
        self.assertEqual(saved.json()["candidate_expedition_budget"], {"daily_launches": None, "daily_items": None})
        capped_config = {**old, "config": {**old["config"], "expedition_budget": {"daily_items": 3}}}
        self.assertEqual(self.client.post(self.url, capped_config, format="json").status_code, 400)
        quota = self.client.post(self.url, self.body, format="json").json()
        missing_optional = {key: value for key, value in self.body.items()
                            if key not in {"candidate_policy", "candidate_expedition_budget"}}
        response = self.client.patch(f"{self.url}{quota['id']}/", {**missing_optional, "revision": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["candidate_policy"], "expedition_limits")
        self.assertEqual(response.json()["candidate_expedition_budget"], self.body["candidate_expedition_budget"])

    def test_current_routine_quota_is_replaced_by_explicit_candidate_and_immutable_evidence_survives_edit(self):
        response = self.client.post(self.url, {**self.body, "config": {
            **self.body["config"], "expedition_budget": {"daily_launches": 1, "daily_items": 1},
        }}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        saved = response.json()
        pair = self.client.post(f"{self.url}{saved['id']}/compare/", {"revision": 1}, format="json")
        self.assertEqual(pair.status_code, 201, pair.content)
        comparison = pair.json()
        updated = self.client.patch(f"{self.url}{saved['id']}/", {
            **self.body, "revision": 1, "candidate_expedition_budget": {"daily_launches": 0, "daily_items": None},
        }, format="json")
        self.assertEqual(updated.status_code, 200, updated.content)
        old = self.client.get(f"{self.url}{saved['id']}/comparisons/{comparison['id']}/").json()
        self.assertTrue(old["stale"])
        self.assertEqual(old["candidate"], comparison["candidate"])
