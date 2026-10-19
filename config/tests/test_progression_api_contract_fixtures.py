"""Raw designer endpoints over fixed, synthetic global content."""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rpg.models import DropTable, ItemDefinition
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared


INCUBATION_POLICY = {
    "duration_seconds": 86400,
    "max_active": 1,
    "clock": "elapsed_seconds",
    "start_strategy": "first_compatible_pair_during_care",
    "claim_strategy": "next_active_care_visit_at_or_after_ready",
}


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None, SOURCE_COMMIT="")
class ProgressionLabResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        designer = make_family(
            "Synthetic progression design",
            family_id=31,
            parents=[{"id": 7, "username": "fixture-progression-designer", "is_staff": True}],
        ).parents[0]
        self.client.force_authenticate(designer)
        language = SkillCategory.objects.create(id=501, name="Language Arts")
        life = SkillCategory.objects.create(id=502, name="Life Skills")
        physical = SkillCategory.objects.create(id=503, name="Physical")
        art = SkillCategory.objects.create(id=504, name="Art & Crafts")
        Skill.objects.create(id=511, name="Reading Comprehension", category=language)
        persistence = Skill.objects.create(id=512, name="Persistence", category=life)
        Skill.objects.create(id=513, name="Mindfulness", category=physical)
        Skill.objects.create(id=514, name="Endurance", category=physical)
        Skill.objects.create(id=515, name="Drawing", category=art)
        base = PotionType.objects.create(id=522, slug="base", name="Base", color_hex="#8B7355")
        chick = PetSpecies.objects.create(id=521, slug="chick", name="Chick", sprite_key="cute-chick")
        chick.available_potions.add(base)
        items = [
            ItemDefinition.objects.create(id=531, slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=chick, metadata={"species": "chick"}),
            ItemDefinition.objects.create(id=532, slug="base-potion", name="Base Potion", item_type="potion", potion_type=base, metadata={"variant": "base"}),
            ItemDefinition.objects.create(id=533, slug="food-birdseed", name="Birdseed", item_type="food", food_species=chick),
            ItemDefinition.objects.create(id=534, slug="lab-coin-pouch", name="Small Coin Pouch", item_type="coin_pouch", metadata={"coins": 7}),
            ItemDefinition.objects.create(id=535, slug="lab-frame", name="Practice Frame", item_type="cosmetic_frame", coin_value=3),
        ]
        for index, item in enumerate(items):
            DropTable.objects.create(id=541 + index, trigger_type="chore_complete", item=item, weight=10)
        DropTable.objects.create(id=546, trigger_type="reading_logged", item=items[2], weight=10)
        DropTable.objects.create(id=547, trigger_type="reading_logged", item=items[3], weight=5)
        Badge.objects.create(
            id=551, name="First lab chore", description="One synthetic approved chore",
            criteria_type="chore_completions", criteria_value={"count": 1}, xp_bonus=5,
        )
        quest = QuestDefinition.objects.create(
            id=561, name="Regular lab chores", description="Two synthetic approved chores",
            quest_type="collection", target_value=2, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
            coin_reward=12, xp_reward=15, is_system=True,
        )
        QuestSkillTag.objects.create(id=562, quest_definition=quest, skill=persistence, xp_weight=1)

    def test_metadata_and_seeded_report_match_shared_wire_contract(self):
        metadata_response = self.client.get("/api/rpg/progression-lab/")
        self.assertEqual(metadata_response.status_code, 200, metadata_response.data)
        self.assertEqual(metadata_response.json().get("pet_incubation_policy"), INCUBATION_POLICY)
        metadata = self.assert_response_fixture(metadata_response, "progression-lab-metadata.json")
        self.assertEqual(metadata["catalog"]["supported_pet_variants"], 1)
        self.assertEqual(metadata["catalog"]["supported_items"], 5)
        report = self.assert_response_fixture(self.client.post(
            "/api/rpg/progression-lab/simulate/",
            {"horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 1,
             "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False},
            format="json",
        ), "progression-lab-report.json")
        self.assertEqual(report["config"]["trials"], 3)
        self.assertEqual(len(report["trace"]), 30)
        self.assertTrue(report["journey"]["events"])
        self.assertEqual(report["coverage"]["initial_state"]["coins"], 0)
        self.assertEqual(report["pet_incubation_policy"], INCUBATION_POLICY)
        self.assertEqual(report["rules_fingerprint"], metadata["rules_fingerprint"])

    def test_purchases_and_money_match_shared_wire_contract(self):
        response = self.client.post(
            "/api/rpg/progression-lab/simulate/",
            {
                "horizon_days": 30, "trials": 3, "seed": 17,
                "chores_per_day": 1, "chore_coins": 5,
                "habits_per_day": 0, "journal_per_day": False,
                "project_minutes": 20,
                "economy": {
                    "enabled": True, "start_date": "2026-01-20",
                    "purchase_strategy": "buy_affordable",
                    "monthly_family_budget_cents": 600,
                    "chore_money_cents": 25, "project_hourly_money_cents": 800,
                    "exchange_shortfalls": True, "monthly_exchange_limit_cents": 100,
                    "printing": {"minutes_per_coin": 10, "monthly_minutes": 30, "monthly_grams": 20},
                    "offers": [
                        {"key": "outing", "label": "Practice outing", "kind": "real_world",
                         "coin_price": 50, "repeat_every_days": 7, "stock": 2,
                         "family_cost_cents": 500, "print_minutes": 0, "print_grams": 0},
                        {"key": "print", "label": "Practice print", "kind": "printing",
                         "coin_price": 0, "repeat_every_days": 7, "stock": None,
                         "family_cost_cents": 25, "print_minutes": 21, "print_grams": 10},
                    ],
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        report = self.assert_response_fixture(response, "progression-lab-economy-report.json")
        self.assertEqual(report["pet_incubation_policy"], INCUBATION_POLICY)
        self.assertTrue(report["economy"]["enabled"])
        self.assertEqual(report["config"]["economy"]["start_date"], "2026-01-20")

    def test_daily_reward_budget_matches_shared_wire_contract(self):
        response = self.client.post(
            "/api/rpg/progression-lab/simulate/",
            {"horizon_days": 30, "trials": 3, "seed": 17,
             "chores_per_day": 1, "chore_coins": 5,
             "habits_per_day": 0, "journal_per_day": False,
             "reward_budget": {"daily_coins": 5}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        # Assert behavior before the fixture comparison so a fixture rewrite
        # cannot accidentally turn an uncapped response into passing evidence.
        self.assertEqual(response.data["config"]["reward_budget"]["daily_coins"], 5)
        budget = response.data["reward_budget"]["summary"]
        self.assertGreater(budget["omitted_coins"]["p50"], 0)
        self.assertLessEqual(budget["awarded_coins"]["p90"], 5 * response.data["summary"]["active_days"])
        self.assert_response_fixture(response, "progression-lab-reward-budget-report.json")
        self.assertEqual(response.json()["pet_incubation_policy"], INCUBATION_POLICY)

    def test_full_value_commitments_match_shared_wire_contract(self):
        response = self.client.post("/api/rpg/progression-lab/simulate/", {
            "horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 10,
            "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False,
            "reward_commitment": {"enabled": True},
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        commitment = response.data["reward_commitment"]
        self.assertTrue(commitment["enabled"])
        self.assertIsNone(response.data["config"]["reward_budget"]["daily_coins"])
        self.assertEqual(commitment["policy"]["daily_coins"], 100)
        self.assertGreater(commitment["summary"]["activity_pouch_committed"]["p50"], 0)
        self.assertGreater(commitment["summary"]["expedition_launches"]["p90"], 0)
        for day in response.data["trace"]:
            self.assertLessEqual(day["reward_commitment_expedition_today_p90"], 75)
            self.assertLessEqual(day["reward_commitment_activity_pouch_today_p90"], 25)
        self.assert_response_fixture(response, "progression-lab-commitment-report.json")

    def test_shared_expedition_limits_match_shared_wire_contract(self):
        response = self.client.post("/api/rpg/progression-lab/simulate/", {
            "horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 10,
            "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False,
            "reward_commitment": {"enabled": True},
            "expedition_budget": {"daily_launches": 1, "daily_items": 1},
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        quotas = response.data["expedition_budget"]
        self.assertEqual(response.data["config"]["expedition_budget"], {"daily_launches": 1, "daily_items": 1})
        self.assertTrue(response.data["reward_commitment"]["enabled"])
        self.assertGreater(quotas["summary"]["launched_trips"]["p90"], 0)
        self.assertGreater(quotas["summary"]["slots_promised"]["p90"], 0)
        self.assertLessEqual(quotas["summary"]["slots_promised"]["p90"], 30)
        self.assert_response_fixture(response, "progression-lab-expedition-budget-report.json")

    @patch("django.utils.timezone.now", return_value=datetime(2026, 10, 18, 12, tzinfo=dt_timezone.utc))
    def test_saved_quota_comparison_matches_shared_wire_contract(self, _now):
        from apps.rpg.models import ProgressionComparison, ProgressionExperiment

        url = "/api/rpg/progression-lab/experiments/"
        response = self.client.post(url, {
            "name": "Shared expedition supply", "hypothesis": "Limit new item promises while preserving the same full-promise Coin policy.",
            "config": {"horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 10,
                       "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False,
                       "reward_commitment": {"enabled": True}},
            "candidate_daily_coins": None, "candidate_policy": "expedition_limits",
            "candidate_expedition_budget": {"daily_launches": 1, "daily_items": 1},
            "targets": [{"metric": "expedition_items_promised_p50", "max": 30},
                        {"metric": "first_mount_reached_rate", "min": 0}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        experiment_id = "00000000-0000-4000-8000-000000000021"
        ProgressionExperiment.objects.filter(pk=response.json()["id"]).update(id=experiment_id)
        detail_url = f"{url}{experiment_id}/"
        comparison = self.client.post(detail_url + "compare/", {"revision": 1}, format="json")
        self.assertEqual(comparison.status_code, 201, comparison.content)
        comparison_id = "00000000-0000-4000-8000-000000000022"
        ProgressionComparison.objects.filter(pk=comparison.json()["id"]).update(id=comparison_id)
        report = self.assert_response_fixture(
            self.client.get(detail_url + f"comparisons/{comparison_id}/"),
            "progression-experiment-expedition-budget-comparison.json",
        )
        self.assertEqual(report["inputs"]["candidate_policy"], "expedition_limits")
        self.assertIsNone(report["inputs"]["candidate_daily_coins"])
        self.assertEqual(report["control"]["config"]["expedition_budget"], {"daily_launches": None, "daily_items": None})
        self.assertEqual(report["candidate"]["config"]["expedition_budget"], {"daily_launches": 1, "daily_items": 1})
        self.assertEqual(report["control"]["config"]["reward_commitment"], report["candidate"]["config"]["reward_commitment"])
        self.assertEqual(report["control"]["config"]["reward_budget"], report["candidate"]["config"]["reward_budget"])

    @patch("django.utils.timezone.now", return_value=datetime(2026, 10, 18, 12, tzinfo=dt_timezone.utc))
    def test_saved_commitment_experiment_matches_shared_wire_contract(self, _now):
        from apps.rpg.models import ProgressionComparison, ProgressionExperiment

        url = "/api/rpg/progression-lab/experiments/"
        response = self.client.post(url, {
            "name": "Full-promise commitment prototype",
            "hypothesis": "Reserve full new grants before launch, keeping every established payout intact.",
            "config": {"horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 10,
                       "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False},
            "candidate_daily_coins": 100, "candidate_policy": "commitment100",
            "targets": [{"metric": "closing_coins_p50", "min": 0}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        experiment_id = "00000000-0000-4000-8000-000000000011"
        ProgressionExperiment.objects.filter(pk=response.json()["id"]).update(id=experiment_id)
        detail_url = f"{url}{experiment_id}/"
        comparison = self.client.post(detail_url + "compare/", {"revision": 1}, format="json")
        self.assertEqual(comparison.status_code, 201, comparison.content)
        comparison_id = "00000000-0000-4000-8000-000000000012"
        ProgressionComparison.objects.filter(pk=comparison.json()["id"]).update(id=comparison_id)
        report = self.assert_response_fixture(
            self.client.get(detail_url + f"comparisons/{comparison_id}/"),
            "progression-experiment-commitment-comparison.json",
        )
        self.assertEqual(report["inputs"]["candidate_policy"], "commitment100")
        self.assertFalse(report["control"]["config"]["reward_commitment"]["enabled"])
        self.assertTrue(report["candidate"]["config"]["reward_commitment"]["enabled"])
        self.assertIsNone(report["candidate"]["config"]["reward_budget"]["daily_coins"])
        self.assertTrue(report["evaluation"]["proposal"]["evaluated_by_current_engine"])
        self.assertFalse(report["evaluation"]["proposal"]["live_ready"])

    @patch("django.utils.timezone.now", return_value=datetime(2026, 10, 19, 12, tzinfo=dt_timezone.utc))
    def test_challenge_gates_and_saved_paired_evidence_match_shared_wire_contract(self, _now):
        from apps.rpg.models import ProgressionComparison, ProgressionExperiment

        QuestDefinition.objects.create(
            id=563, name="Next lab chapter", description="Two newly approved chores after the first chapter",
            quest_type="collection", target_value=2, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
            coin_reward=18, xp_reward=0, is_system=True,
        )
        self.assert_response_fixture(self.client.get("/api/rpg/progression-lab/"), "progression-lab-challenge-gates-metadata.json")
        config = {
            "horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 1,
            "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False,
            "reward_commitment": {"enabled": True},
            "expedition_budget": {"daily_launches": 3, "daily_items": None},
            "challenge_gates": {"mode": "milestone_tenure", "start_date": "2026-01-01", "rules": [{
                "quest_id": 563, "prerequisite_quest_id": 561, "skill_id": 511, "skill_level": 1,
                "min_days": 14, "available_from": None, "available_until": None,
            }]},
        }
        response = self.client.post("/api/rpg/progression-lab/simulate/", config, format="json")
        report = self.assert_response_fixture(response, "progression-lab-challenge-gates-report.json")
        target = next(row for row in report["challenge_gates"]["targets"] if row["quest_id"] == 563)
        self.assertEqual(target["unlocked_trials"], 3)
        self.assertEqual(target["p50_unlock_days"], 15)
        self.assertEqual(target["p50_completion_days"], 16)
        self.assertFalse(report["config"]["reward_budget"]["daily_coins"])
        url = "/api/rpg/progression-lab/experiments/"
        for index, (policy, mode) in enumerate((("milestone_gates", "milestones"), ("tenure_gates", "milestone_tenure")), start=21):
            created = self.client.post(url, {
                "name": "Optional chapter gate experiment", "hypothesis": "Separate chapters while preserving reward values.",
                "config": config, "candidate_policy": policy, "candidate_daily_coins": None,
                "targets": [{"metric": "challenge_waiting_visits_p50", "max": 10},
                            {"metric": "challenge_unreachable_total", "max": 0},
                            {"metric": "gated_challenge_min_completion_rate", "min": 1}],
            }, format="json")
            self.assertEqual(created.status_code, 201, created.content)
            experiment_id = f"00000000-0000-4000-8000-{index:012d}"
            ProgressionExperiment.objects.filter(pk=created.json()["id"]).update(id=experiment_id)
            detail_url = f"{url}{experiment_id}/"
            comparison = self.client.post(detail_url + "compare/", {"revision": 1}, format="json")
            self.assertEqual(comparison.status_code, 201, comparison.content)
            comparison_id = f"00000000-0000-4000-8000-{index + 10:012d}"
            ProgressionComparison.objects.filter(pk=comparison.json()["id"]).update(id=comparison_id)
            pair = self.assert_response_fixture(self.client.get(detail_url + f"comparisons/{comparison_id}/"),
                                               f"progression-experiment-{policy.replace('_', '-')}-comparison.json")
            self.assertEqual(pair["control"]["config"]["challenge_gates"]["mode"], "current")
            self.assertEqual(pair["candidate"]["config"]["challenge_gates"]["mode"], mode)
            self.assertEqual(pair["control"]["config"]["reward_commitment"], pair["candidate"]["config"]["reward_commitment"])
            self.assertEqual(pair["control"]["config"]["expedition_budget"], pair["candidate"]["config"]["expedition_budget"])

    @patch("django.utils.timezone.now", return_value=datetime(2026, 10, 18, 12, tzinfo=dt_timezone.utc))
    def test_saved_experiment_feedback_contracts(self, _now):
        from apps.rpg.models import ProgressionComparison, ProgressionDecision, ProgressionExperiment, ProgressionObservation

        url = "/api/rpg/progression-lab/experiments/"
        response = self.client.post(url, {
            "name": "100-Coin starting experiment", "hypothesis": "Test income and first-reward pacing before changing live grants.",
            "config": {"horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 1,
                       "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False},
            "candidate_daily_coins": 100, "targets": [{"metric": "closing_coins_p50", "min": 0}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        experiment_id = "00000000-0000-4000-8000-000000000001"
        ProgressionExperiment.objects.filter(pk=response.json()["id"]).update(id=experiment_id)
        self.assert_response_fixture(self.client.get(url), "progression-experiment-list.json")
        detail_url = f"{url}{experiment_id}/"
        comparison = self.client.post(detail_url + "compare/", {"revision": 1}, format="json")
        self.assertEqual(comparison.status_code, 201, comparison.content)
        comparison_id = "00000000-0000-4000-8000-000000000002"
        ProgressionComparison.objects.filter(pk=comparison.json()["id"]).update(id=comparison_id)
        report = self.assert_response_fixture(self.client.get(detail_url + f"comparisons/{comparison_id}/"), "progression-experiment-comparison.json")
        self.assertEqual(report["control"]["config"]["seed"], report["candidate"]["config"]["seed"])
        self.assertEqual(report["candidate"]["config"]["reward_budget"]["daily_coins"], 100)
        self.assertFalse(report["evaluation"]["proposal"]["live_ready"])
        decision = self.client.post(detail_url + "decisions/", {
            "revision": 1, "comparison_id": comparison_id, "outcome": "keep_testing",
            "rationale": "This envelope does not yet model promise-safe commitments.",
            "next_action": "Simulate the proposed expedition table and reserve full pouch value before new grants.",
            "review_on": "2099-01-01",
        }, format="json")
        self.assertEqual(decision.status_code, 201, decision.content)
        ProgressionDecision.objects.filter(pk=decision.json()["decisions"][0]["id"]).update(id="00000000-0000-4000-8000-000000000003")
        self.assert_response_fixture(self.client.get(detail_url), "progression-experiment-decided.json")
        empty = self.assert_response_fixture(self.client.get("/api/rpg/progression-lab/observations/"), "progression-observations-empty.json")
        self.assertEqual(empty["status"], "insufficient_evidence")
        self.assertEqual(empty["cohort"]["eligible_children"], 0)
        observation = self.client.post(detail_url + "observations/", {"revision": 1}, format="json")
        self.assertEqual(observation.status_code, 201, observation.content)
        ProgressionObservation.objects.filter(pk=observation.json()["observations"][0]["id"]).update(id="00000000-0000-4000-8000-000000000004")
        snapshot = self.assert_response_fixture(self.client.get(detail_url), "progression-experiment-observed.json")
        self.assertEqual(snapshot["observations"][0]["status"], "insufficient_evidence")

    def test_companion_badges_pay_once_when_care_reaches_their_milestones(self):
        quest = QuestDefinition.objects.get(pk=561)
        quest.target_value = 1
        quest.save(update_fields=["target_value"])
        for item_id, quantity in ((531, 1), (532, 1), (533, 30)):
            QuestRewardItem.objects.create(quest_definition=quest, item_id=item_id, quantity=quantity)
        names = ["First lab hatch", "First lab species", "First lab grown companion"]
        for pk, name, criteria_type, rarity, xp_bonus in (
            (552, names[0], "pets_hatched", "common", 7),
            (553, names[1], "pet_species_owned", "uncommon", 8),
            (554, names[2], "mounts_evolved", "rare", 9),
        ):
            Badge.objects.create(
                id=pk, name=name, criteria_type=criteria_type, criteria_value={"count": 1},
                rarity=rarity, xp_bonus=xp_bonus,
            )
        response = self.client.post("/api/rpg/progression-lab/simulate/", {
            "horizon_days": 30, "trials": 1, "seed": 17, "reading_minutes": 0,
            "chores_per_day": 1, "chore_coins": 5, "chore_xp": 100,
            "habits_per_day": 0, "journal_per_day": False, "expeditions_per_day": 0,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        report = response.json()
        earned = [event for event in report["journey"]["events"]
                  if event["source"] == "badge_earned" and event["target"] in names]
        # Exercise the real endpoint independently of the generated snapshots.
        self.assertEqual([(event["target"], event["day"]) for event in earned],
                         [(name, 2) for name in names])
        self.assertEqual(report["pet_incubation_policy"], INCUBATION_POLICY)
        first_day, claim_day = report["trace"][:2]
        self.assertEqual((first_day["incubating_eggs_p50"], first_day["ready_eggs_p50"],
                          first_day["pets_p50"], first_day["mounts_p50"], first_day["badges_p50"]),
                         (1, 0, 0, 0, 1))
        self.assertEqual((claim_day["incubating_eggs_p50"], claim_day["ready_eggs_p50"],
                          claim_day["pets_p50"], claim_day["mounts_p50"], claim_day["badges_p50"]),
                         (0, 0, 1, 1, 4))
        started = next(event for event in report["journey"]["events"] if event["source"] == "incubation_started")
        self.assertEqual((started["day"], started["duration_seconds"], started["ready_day"]), (1, 86400, 2))
        ready = next(event for event in report["journey"]["events"] if event["source"] == "incubation_ready")
        self.assertEqual(ready["day"], 2)
        self.assertEqual(report["summary"]["finite_breakdown"]["badge"], 4)
        self.assertTrue(all(day["badges_p50"] == 4 for day in report["trace"][1:]))
        badges = next(source for source in report["flows"]["sources"] if source["source"] == "badges")
        self.assertEqual((badges["coins"], badges["xp"]), (60.0, 29.0))
        self.assert_response_fixture(response, "progression-lab-pet-incubation-report.json")

    def test_metadata_and_report_capture_duration_setting_without_rewriting_an_earlier_report(self):
        scenario = {"horizon_days": 30, "trials": 1, "seed": 17}
        original = self.client.post("/api/rpg/progression-lab/simulate/", scenario, format="json")
        self.assertEqual(original.status_code, 200, original.data)
        original = original.json()
        self.assertEqual(original.get("pet_incubation_policy"), INCUBATION_POLICY)
        with override_settings(PET_INCUBATION_DURATION_SECONDS=172800):
            metadata = self.client.get("/api/rpg/progression-lab/")
            changed = self.client.post("/api/rpg/progression-lab/simulate/", scenario, format="json")
        self.assertEqual((metadata.status_code, changed.status_code), (200, 200))
        policy = {**INCUBATION_POLICY, "duration_seconds": 172800}
        self.assertEqual(metadata.json()["pet_incubation_policy"], policy)
        self.assertEqual(changed.json()["pet_incubation_policy"], policy)
        self.assertEqual(metadata.json()["rules_fingerprint"], changed.json()["rules_fingerprint"])
        self.assertNotEqual(original["rules_fingerprint"], changed.json()["rules_fingerprint"])
        self.assertEqual(original["pet_incubation_policy"], INCUBATION_POLICY)
