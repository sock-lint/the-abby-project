"""Saved experiments compare installed rules with full-promise hypotheses."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"])
class CommitmentExperimentTests(APITestCase):
    url = "/api/rpg/progression-lab/experiments/"

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(make_family(parents=[{"username": "commitment-designer", "is_staff": True}]).parents[0])
        self.body = {"name": "Preserve committed rewards", "hypothesis": "Reserve before granting, then pay promises fully.",
                     "config": {"horizon_days": 30, "trials": 1}, "candidate_daily_coins": 100,
                     "candidate_policy": "commitment100", "targets": []}

    def test_saved_pair_has_installed_control_and_fixed_commitment_candidate(self):
        created = self.client.post(self.url, self.body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        saved = created.json()
        self.assertEqual(saved["candidate_policy"], "commitment100")
        result = self.client.post(f"{self.url}{saved['id']}/compare/", {"revision": 1}, format="json")
        self.assertEqual(result.status_code, 201, result.content)
        pair = result.json()
        self.assertFalse(pair["control"]["config"]["reward_commitment"]["enabled"])
        self.assertTrue(pair["candidate"]["config"]["reward_commitment"]["enabled"])
        self.assertIsNone(pair["candidate"]["config"]["reward_budget"]["daily_coins"])
        self.assertEqual(pair["inputs"]["candidate_policy"], "commitment100")
        self.assertTrue(pair["candidate"]["reward_commitment"]["enabled"])

    def test_policy_types_are_strict_and_commitment_parameters_are_fixed(self):
        for values in ({"candidate_policy": []}, {"candidate_policy": None}, {"candidate_policy": True},
                       {"candidate_policy": {}}, {"candidate_policy": "live"}, {"candidate_daily_coins": 75}):
            self.assertEqual(self.client.post(self.url, {**self.body, **values}, format="json").status_code, 400)

    def test_old_clients_default_to_envelope_and_cannot_accidentally_rewrite_selected_policy(self):
        old = {key: value for key, value in self.body.items() if key != "candidate_policy"}
        created = self.client.post(self.url, old, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["candidate_policy"], "envelope")
        committed = self.client.post(self.url, self.body, format="json").json()
        edited = self.client.patch(f"{self.url}{committed['id']}/", {**old, "revision": 1}, format="json")
        self.assertEqual(edited.status_code, 200, edited.content)
        self.assertEqual(edited.json()["candidate_policy"], "commitment100")

    def test_imported_commitment_config_never_changes_installed_control_or_overrides_saved_policy(self):
        body = {**self.body, "candidate_policy": "envelope", "candidate_daily_coins": 75,
                "config": {**self.body["config"], "reward_commitment": {"enabled": True}}}
        created = self.client.post(self.url, body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        saved = created.json()
        self.assertFalse(saved["config"]["reward_commitment"]["enabled"])
        result = self.client.post(f"{self.url}{saved['id']}/compare/", {"revision": 1}, format="json")
        self.assertEqual(result.status_code, 201, result.content)
        pair = result.json()
        self.assertFalse(pair["control"]["config"]["reward_commitment"]["enabled"])
        self.assertFalse(pair["candidate"]["config"]["reward_commitment"]["enabled"])
        self.assertEqual(pair["candidate"]["config"]["reward_budget"]["daily_coins"], 75)

    def test_omitted_policy_cannot_turn_commitment_into_a_different_daily_amount(self):
        saved = self.client.post(self.url, self.body, format="json").json()
        old = {key: value for key, value in self.body.items() if key != "candidate_policy"}
        edited = self.client.patch(f"{self.url}{saved['id']}/", {
            **old, "revision": 1, "candidate_daily_coins": 75,
        }, format="json")
        self.assertEqual(edited.status_code, 400, edited.content)
        reopened = self.client.get(f"{self.url}{saved['id']}/").json()
        self.assertEqual((reopened["candidate_policy"], reopened["revision"]), ("commitment100", 1))

    def test_required_fields_and_unknown_fields_remain_strict(self):
        for missing in ("name", "hypothesis", "config", "candidate_daily_coins", "targets"):
            body = {key: value for key, value in self.body.items() if key != missing}
            self.assertEqual(self.client.post(self.url, body, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.url, {**self.body, "live_ready": True}, format="json").status_code, 400)
