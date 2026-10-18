"""Expedition quotas bound new promises shared by one child's mounts."""
from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase

from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial, normalize_config, run_trial, simulate_progression
from apps.rpg.tests.test_progression_commitment import catalog_with, item, with_mounts
from apps.rpg.tests.test_progression_economy import empty_catalog, quiet_config


def scenario(*, launches=None, items=None, **changes):
    return quiet_config(expedition_budget={"daily_launches": launches, "daily_items": items}, **changes)


class ExpeditionBudgetTests(SimpleTestCase):
    def test_configuration_is_detached_optional_and_strict_before_any_catalog_read(self):
        supplied = {"expedition_budget": {}}
        before = deepcopy(supplied)
        self.assertEqual(normalize_config(supplied)["expedition_budget"], {"daily_launches": None, "daily_items": None})
        self.assertEqual(supplied, before)
        self.assertEqual(normalize_config()["expedition_budget"], {"daily_launches": None, "daily_items": None})
        invalid = (None, [], True, {"daily_launches": True}, {"daily_launches": -1}, {"daily_launches": 16},
                   {"daily_items": False}, {"daily_items": 46}, {"daily_items": 0.5},
                   {"daily_launches": "1"}, {"user_id": 1})
        with patch("apps.rpg.progression.engine.load_catalog", side_effect=AssertionError("No catalog read")):
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    simulate_progression({"expedition_budget": value})
        self.assertEqual(normalize_config(scenario(launches=0, items=0))["expedition_budget"],
                         {"daily_launches": 0, "daily_items": 0})

    def test_launch_allowance_is_shared_across_all_mounts_and_denials_do_not_roll_loot(self):
        trial = with_mounts(Trial(scenario(launches=3, expeditions_per_day=15), empty_catalog(), 42), 15)
        trial.day = 1
        with patch.object(trial.rng, "random", wraps=trial.rng.random) as random:
            trial.launch_expeditions()
        self.assertEqual(random.call_count, 3)  # Coin jitter only for the three new trips.
        self.assertEqual(len(trial.pending_expeditions), 3)
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["requested_trips"], s["eligible_trips"], s["launched_trips"], s["prevented_trips"]), (15, 15, 3, 12))
        self.assertEqual(s["launch_limited_days"], 1)
        self.assertEqual(s["launch_saturated_days"], 1)

    def test_item_allowance_is_shared_and_later_coin_only_trips_still_launch(self):
        trial = with_mounts(Trial(scenario(items=3, expeditions_per_day=15), catalog_with(item(1)), 42), 15)
        trial.day = 1
        trial.launch_expeditions()
        self.assertEqual([len(row["items"]) for row in trial.pending_expeditions], [3] + [0] * 14)
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["slots_requested"], s["slots_promised"], s["slots_withheld_by_budget"], s["slots_unfilled_by_pool"]), (45, 3, 42, 0))
        self.assertEqual((s["launched_trips"], s["zero_item_trips"], s["zero_coin_trips"], s["empty_trips"]), (15, 14, 0, 0))
        self.assertEqual(s["pending_items"], 3)

    def test_pool_emptiness_does_not_spend_or_masquerade_as_an_item_quota(self):
        trial = with_mounts(Trial(scenario(items=3, expeditions_per_day=3), empty_catalog(), 42), 3)
        trial.day = 1
        trial.launch_expeditions()
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["slots_requested"], s["slots_promised"], s["slots_withheld_by_budget"], s["slots_unfilled_by_pool"]), (9, 0, 0, 9))
        self.assertEqual(s["item_saturated_days"], 0)
        self.assertEqual(s["item_limited_days"], 0)

    def test_saturation_without_any_withholding_is_distinct_from_a_limited_day(self):
        trial = with_mounts(Trial(scenario(launches=1, items=3, expeditions_per_day=1), catalog_with(item(1)), 42), 1)
        trial.day = 1
        trial.launch_expeditions()
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["launch_saturated_days"], s["item_saturated_days"]), (1, 1))
        self.assertEqual((s["launch_limited_days"], s["item_limited_days"]), (0, 0))

    def test_zero_caps_do_not_count_saturation_or_limiting_on_an_idle_no_mount_day(self):
        trial = Trial(scenario(launches=0, items=0, expeditions_per_day=1), empty_catalog(), 42)
        trial.day = 1
        trial.launch_expeditions()
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["requested_trips"], s["eligible_trips"], s["unavailable_mount_trips"]), (1, 0, 1))
        self.assertEqual((s["launch_saturated_days"], s["item_saturated_days"], s["launch_limited_days"], s["item_limited_days"]), (0, 0, 0, 0))

    def test_existing_frozen_loot_claims_and_pouches_pay_fully_under_zero_quotas(self):
        trial = Trial(scenario(launches=0, items=0), catalog_with(item(1, kind="coin_pouch", coins=500)), 42)
        trial.day = 8
        trial.pending_expeditions = [{"returns": 1, "coins": 200, "items": [1, 1]}]
        before = deepcopy(trial.pending_expeditions[0])
        trial.claim_expeditions()
        self.assertEqual(before, {"returns": 1, "coins": 200, "items": [1, 1]})
        trial.feed_and_hatch()
        self.assertEqual(trial.source_totals["expeditions"]["coins"], 200)
        self.assertEqual(trial.source_totals["coin_pouches"]["coins"], 1000)
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["slots_promised"], s["claimed_items"], s["grandfathered_claimed_items"], s["pending_items"]), (0, 2, 2, 0))

    def test_duplicate_cosmetic_salvage_still_counts_one_promised_and_claimed_item(self):
        trial = with_mounts(Trial(scenario(items=1, expeditions_per_day=1),
                                 catalog_with(item(1, kind="cosmetic_frame", coins=5)), 42), 1)
        trial.inventory[1] = 1
        trial.day = 1
        trial.launch_expeditions()
        trial.day = 2
        trial.claim_expeditions()
        self.assertEqual(trial.inventory[1], 1)
        self.assertEqual(trial.source_totals["expeditions_salvage"]["coins"], 5)
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["slots_promised"], s["claimed_items"], s["pending_items"]), (1, 1, 0))

    def test_daily_capacity_never_banks_and_resets_before_the_next_active_visit(self):
        trial = with_mounts(Trial(scenario(launches=1, items=1, expeditions_per_day=1), catalog_with(item(1)), 42), 1)
        trial.day = 1
        trial.launch_expeditions()
        trial.day = 8
        trial.claim_expeditions()
        trial.launch_expeditions()
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["launched_trips"], s["slots_promised"], s["claimed_items"], s["pending_items"]), (2, 2, 1, 1))

    def test_coin_commitment_and_item_quota_are_independent_and_empty_trips_are_visible(self):
        trial = with_mounts(Trial(scenario(items=3, expeditions_per_day=15,
                                          reward_commitment={"enabled": True}), catalog_with(item(1)), 42), 15)
        trial.day = 1
        trial.launch_expeditions()
        s = trial.report()["expedition_budget"]["summary"]
        self.assertEqual((s["launched_trips"], s["slots_promised"], s["zero_item_trips"], s["zero_coin_trips"], s["empty_trips"]), (15, 3, 14, 13, 13))
        self.assertEqual(trial.report()["reward_commitment"]["summary"]["expedition_direct_committed"], 75)

    def test_zero_launch_or_item_capacity_removes_unavailable_targets_not_extends_runway(self):
        catalog = catalog_with(item(1, kind="cosmetic_frame", coins=5), trigger="expedition_returned")
        for limits in ({"launches": 0}, {"items": 0}):
            with self.subTest(limits=limits), patch.object(Trial, "_initial_mount_possible", return_value=True):
                trial = Trial(scenario(**limits, chores_per_day=1, expeditions_per_day=15), catalog, 42)
            self.assertNotIn("cosmetic:1", trial.finite_keys)
            report = trial.report()["expedition_budget"]
            self.assertEqual((report["unlimited_finite_total"], report["unavailable_finite_total"]), (1, 1))
            self.assertEqual(report["removed_finite_targets"], {"cosmetic": 1})

    def test_unlimited_quota_and_installed_coin_comparators_keep_the_other_policy_fixed(self):
        for value, limits, expected_quota_loss, expected_coin_loss in ((5, 0, 1, 0), (50, 1, 0, 1)):
            catalog = catalog_with(item(1, kind="cosmetic_frame", coins=value), trigger="expedition_returned")
            with self.subTest(value=value), patch.object(Trial, "_initial_mount_possible", return_value=True):
                trial = Trial(scenario(items=limits, chores_per_day=1, expeditions_per_day=1,
                                       reward_commitment={"enabled": True}), catalog, 42)
            self.assertEqual(trial.report()["expedition_budget"]["unavailable_finite_total"], expected_quota_loss)
            self.assertEqual(trial.report()["reward_commitment"]["unavailable_finite_total"], expected_coin_loss)


class ExpeditionBudgetCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def test_unlimited_defaults_preserve_seeded_economics_under_all_coin_policies(self):
        catalog = load_catalog()
        for coin_policy in ({}, {"reward_budget": {"daily_coins": 100}}, {"reward_commitment": {"enabled": True}}):
            config = quiet_config(chores_per_day=2, project_minutes=20, expeditions_per_day=3, **coin_policy)
            self.assertEqual(run_trial(config, catalog, 42), run_trial({**config, "expedition_budget": {
                "daily_launches": None, "daily_items": None}}, catalog, 42))

    def test_launch_counts_bound_return_challenge_reachability_at_one_two_or_three_per_day(self):
        definition = QuestDefinition.objects.create(name="Exactly three returns", quest_type="collection",
                                                    target_value=3, duration_days=1, is_system=True,
                                                    trigger_filter={"allowed_triggers": ["expedition_returned"]})
        catalog = load_catalog()
        for cap in (0, 1, 2, 3):
            trial = Trial(scenario(launches=cap, chores_per_day=1, expeditions_per_day=15), catalog, 42)
            self.assertEqual(definition.pk in {q.pk for q in trial.quests}, cap == 3)
            self.assertEqual("expedition_returned" in trial._enabled_triggers(), cap > 0)

    def test_bounded_journeys_remain_detached_and_reconcile_all_promise_counters(self):
        catalog = load_catalog()
        config = scenario(launches=2, items=3, chores_per_day=2, project_minutes=20,
                          expeditions_per_day=15, reward_commitment={"enabled": True}, trials=2)

        def forbid_sql(execute, sql, params, many, context):
            self.fail(f"Quota simulation touched SQL: {sql[:100]}")

        with connection.execute_wrapper(forbid_sql), \
                patch("apps.rewards.services.CoinService.award_coins", side_effect=AssertionError("Live award")), \
                patch("apps.pets.expeditions.ExpeditionService.start", side_effect=AssertionError("Live expedition")):
            report = simulate_progression(config, catalog=catalog)
        s = report["expedition_budget"]["summary"]
        self.assertEqual(s["requested_trips"]["mean"], s["eligible_trips"]["mean"] + s["unavailable_mount_trips"]["mean"])
        self.assertEqual(s["eligible_trips"]["mean"], s["launched_trips"]["mean"] + s["prevented_trips"]["mean"])
        self.assertEqual(s["slots_requested"]["mean"], sum(s[key]["mean"] for key in ("slots_promised", "slots_withheld_by_budget", "slots_unfilled_by_pool")))
        self.assertEqual(s["slots_promised"]["mean"], s["claimed_items"]["mean"] + s["pending_items"]["mean"])
        for day in report["trace"]:
            self.assertLessEqual(day["expedition_budget_launches_today_p90"], 2)
            self.assertLessEqual(day["expedition_budget_items_today_p90"], 3)
