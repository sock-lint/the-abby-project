"""Saved gate forecasts retain identical economic assumptions and private evidence."""
from copy import deepcopy
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.progression.feedback import evaluate_comparison
from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"])
class ChallengeGateExperimentTests(APITestCase):
    url = "/api/rpg/progression-lab/experiments/"

    def setUp(self):
        cache.clear()
        household = make_family("Gate designers", parents=[
            {"username": "gate-designer", "is_staff": True},
            {"username": "gate-coparent", "is_staff": True},
        ], children=[{"username": "gate-child"}])
        self.designer, self.coparent = household.parents
        self.client.force_authenticate(self.designer)
        category = SkillCategory.objects.create(name="Life Skills")
        self.skill = Skill.objects.create(name="Persistence", category=category)
        self.first = QuestDefinition.objects.create(
            name="First gate chapter", quest_type="collection", target_value=1,
            duration_days=30, trigger_filter={"allowed_triggers": ["chore_complete"]},
            coin_reward=7, xp_reward=0, is_system=True,
        )
        self.second = QuestDefinition.objects.create(
            name="Second gate chapter", quest_type="collection", target_value=1,
            duration_days=30, trigger_filter={"allowed_triggers": ["chore_complete"]},
            coin_reward=20, xp_reward=0, is_system=True,
        )
        self.body = {
            "name": "Chapter pacing", "hypothesis": "Separate fresh chapters without changing payouts.",
            "candidate_policy": "tenure_gates", "candidate_daily_coins": None, "targets": [],
            "config": {
                "horizon_days": 30, "trials": 2, "seed": 123, "reading_minutes": 0,
                "chores_per_day": 1, "habits_per_day": 0, "journal_per_day": False,
                "reward_commitment": {"enabled": True},
                "expedition_budget": {"daily_launches": 3, "daily_items": None},
                "challenge_gates": {
                    "mode": "milestone_tenure", "start_date": "2026-01-01", "rules": [{
                        "quest_id": self.second.pk, "prerequisite_quest_id": self.first.pk,
                        "skill_id": None, "skill_level": 0, "min_days": 14,
                        "available_from": None, "available_until": None,
                    }],
                },
            },
        }

    def create(self, body=None):
        response = self.client.post(self.url, body or self.body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def compare(self, experiment):
        response = self.client.post(f"{self.url}{experiment['id']}/compare/", {"revision": experiment["revision"]}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_gate_candidates_preserve_coin_rules_quotas_catalog_seeds_and_native_targets(self):
        from apps.accounts.models import User
        from apps.quests.models import ChallengeActivity, ChallengeGoal
        from apps.rewards.models import CoinLedger
        from apps.rpg.models import UserInventory
        from apps.rpg.progression.catalog import load_catalog

        for policy, mode, completion_day in (("milestone_gates", "milestones", 2), ("tenure_gates", "milestone_tenure", 15)):
            with self.subTest(policy=policy):
                experiment = self.create({**self.body, "candidate_policy": policy})
                self.assertEqual(experiment["config"]["challenge_gates"]["mode"], "current")
                models = (User, CoinLedger, UserInventory, ChallengeActivity, ChallengeGoal)
                before = [model.objects.count() for model in models]
                with patch("apps.rpg.progression.experiments.load_catalog", wraps=load_catalog) as snapshot:
                    pair = self.compare(experiment)
                self.assertEqual(snapshot.call_count, 1)
                self.assertEqual([model.objects.count() for model in models], before)
                control, candidate = pair["control"], pair["candidate"]
                expected = deepcopy(control["config"])
                expected["challenge_gates"]["mode"] = mode
                self.assertEqual(candidate["config"], expected)
                self.assertEqual(candidate["config"]["reward_commitment"], {"enabled": True})
                self.assertEqual(candidate["config"]["expedition_budget"]["daily_launches"], 3)
                self.assertEqual(control["catalog"], candidate["catalog"])
                self.assertEqual(control["summary"]["finite_content_total"], candidate["summary"]["finite_content_total"])
                before_target = next(row for row in control["challenge_gates"]["targets"] if row["quest_id"] == self.second.pk)
                after_target = next(row for row in candidate["challenge_gates"]["targets"] if row["quest_id"] == self.second.pk)
                self.assertEqual(before_target["p50_completion_days"], 1)
                self.assertEqual(after_target["p50_completion_days"], completion_day)
                self.assertEqual(after_target["completed_trials"], 2)
                url = f"{self.url}{experiment['id']}/comparisons/{pair['id']}/"
                self.assertEqual(self.client.get(url).json()["candidate"], candidate)

    def test_gate_guardrail_can_fail_waiting_without_treating_it_as_content(self):
        body = deepcopy(self.body)
        body["targets"] = [
            {"metric": "challenge_waiting_visits_p50", "max": 0},
            {"metric": "challenge_unreachable_total", "max": 0},
        ]
        pair = self.compare(self.create(body))
        checks = pair["evaluation"]["checks"]
        self.assertEqual(pair["evaluation"]["status"], "fail")
        self.assertEqual(checks[0]["control"]["value"], 0)
        self.assertGreater(checks[0]["candidate"]["value"], 0)
        self.assertEqual(checks[1]["status"], "pass")

    def test_invalid_cross_policy_inputs_and_empty_recipes_are_refused(self):
        empty = deepcopy(self.body)
        empty["config"]["challenge_gates"]["rules"] = []
        for body in (
            {**self.body, "candidate_daily_coins": 100},
            {**self.body, "candidate_expedition_budget": {"daily_launches": 3}}, empty,
        ):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.url, body, format="json").status_code, 400)

    def test_comparison_rejects_economic_and_gate_recipe_changes_in_the_same_pair(self):
        pair = self.compare(self.create())
        for field, value in (("reward_commitment", {"enabled": False}), ("expedition_budget", {"daily_launches": 2, "daily_items": None})):
            changed = deepcopy(pair["candidate"])
            changed["config"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate_comparison(pair["control"], changed, [])
        changed = deepcopy(pair["candidate"])
        changed["config"]["challenge_gates"]["rules"][0]["min_days"] = 99
        with self.assertRaises(ValueError):
            evaluate_comparison(pair["control"], changed, [])

    def test_saved_comparison_is_private_and_older_updates_preserve_the_gate_policy(self):
        experiment = self.create()
        pair = self.compare(experiment)
        updated = {key: value for key, value in self.body.items() if key != "candidate_policy"}
        updated["revision"] = 1
        response = self.client.patch(f"{self.url}{experiment['id']}/", updated, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["candidate_policy"], "tenure_gates")
        self.assertTrue(response.json()["comparisons"][0]["stale"])
        self.client.force_authenticate(self.coparent)
        self.assertEqual(self.client.get(f"{self.url}{experiment['id']}/").status_code, 404)
        self.assertEqual(self.client.get(f"{self.url}{experiment['id']}/comparisons/{pair['id']}/").status_code, 404)

    def test_unknown_catalog_reference_is_a_scenario_error_without_saved_evidence(self):
        body = deepcopy(self.body)
        body["config"]["challenge_gates"]["rules"][0]["quest_id"] = 2147483647
        experiment = self.create(body)
        response = self.client.post(f"{self.url}{experiment['id']}/compare/", {"revision": 1}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.client.get(f"{self.url}{experiment['id']}/").json()["comparisons"], [])
        response = self.client.post("/api/rpg/progression-lab/simulate/", body["config"], format="json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_gated_completion_guardrail_fails_a_policy_that_never_finishes_its_target(self):
        body = deepcopy(self.body)
        body["config"]["challenge_gates"]["rules"][0]["min_days"] = 365
        body["targets"] = [{"metric": "gated_challenge_min_completion_rate", "min": 1}]
        pair = self.compare(self.create(body))
        check = pair["evaluation"]["checks"][0]
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["control"], {"value": 1, "completed_trials": 2, "trials": 2})
        self.assertEqual(check["candidate"], {"value": 0, "completed_trials": 0, "trials": 2})
        self.assertEqual(check["delta"], -1)

    def test_gated_completion_guardrail_is_unknown_when_no_configured_target_is_in_the_routine(self):
        body = deepcopy(self.body)
        body["config"]["chores_per_day"] = 0
        body["targets"] = [{"metric": "gated_challenge_min_completion_rate", "min": 0}]
        pair = self.compare(self.create(body))
        check = pair["evaluation"]["checks"][0]
        self.assertEqual(check["status"], "insufficient")
        self.assertIsNone(check["candidate"]["value"])
        self.assertIsNone(check["candidate"]["completed_trials"])
