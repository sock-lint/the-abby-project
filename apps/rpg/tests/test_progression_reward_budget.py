"""Income envelope experiments never alter saved rewards or real children."""
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase

from apps.rpg.content.loader import ContentPack
from apps.rpg.progression.catalog import Catalog, load_catalog
from apps.rpg.progression.engine import Trial, normalize_config, run_trial, simulate_progression
from apps.rpg.tests.test_progression_economy import empty_catalog, economy, offer, quiet_config


INCLUDED = ("expeditions", "expeditions_salvage", "coin_pouches")


def budget_config(cap, **changes):
    return quiet_config(reward_budget={"daily_coins": cap}, **changes)


class ProgressionRewardBudgetTests(SimpleTestCase):
    def test_legacy_config_defaults_to_an_uncapped_detached_policy(self):
        supplied = {"reward_budget": {}}
        before = deepcopy(supplied)
        actual = normalize_config(supplied)
        self.assertEqual(actual["reward_budget"], {"daily_coins": None})
        self.assertEqual(normalize_config()["reward_budget"], {"daily_coins": None})
        actual["reward_budget"]["daily_coins"] = 1
        self.assertEqual(normalize_config()["reward_budget"], {"daily_coins": None})
        self.assertEqual(supplied, before)

    def test_invalid_policies_fail_before_loading_any_catalog(self):
        policies = (None, False, [], 50, {"daily_coins": True}, {"daily_coins": -1},
                    {"daily_coins": 0.5}, {"daily_coins": "50"}, {"daily_coins": 100001},
                    {"child_id": 1}, {"daily_coins": 100, "bank_unused": True})
        with patch("apps.rpg.progression.engine.load_catalog", side_effect=AssertionError("No catalog read")):
            for policy in policies:
                with self.subTest(policy=policy), self.assertRaises(ValueError):
                    simulate_progression({"reward_budget": policy})

    def test_zero_cap_omits_only_the_three_included_coin_sources(self):
        trial = Trial(budget_config(0), empty_catalog(), 42)
        for source in INCLUDED:
            trial.coin_award(100, source)
        for source in ("chores", "challenges", "badges", "drops_salvage", "money_exchange", "reading"):
            trial.coin_award(10, source)
        self.assertEqual((trial.coins, trial.earned_coins), (60, 60))
        self.assertEqual(trial.report()["reward_budget"]["summary"], {
            "raw_coins": 300, "awarded_coins": 0, "omitted_coins": 300, "capped_days": 1,
        })

    def test_mounts_salvage_and_pouches_share_one_childs_daily_envelope(self):
        trial = Trial(budget_config(100), empty_catalog(), 42)
        trial.day = 1
        trial.pending_expeditions = [
            {"returns": 1, "coins": 75, "items": []},
            {"returns": 1, "coins": 75, "items": []},
        ]
        trial.claim_expeditions()
        trial.coin_award(20, "expeditions_salvage")
        trial.coin_award(50, "coin_pouches")
        self.assertEqual(trial.coins, 105)  # Expedition claim also earns an exempt check-in.
        report = trial.report()["reward_budget"]
        self.assertEqual(report["summary"], {
            "raw_coins": 220, "awarded_coins": 100, "omitted_coins": 120, "capped_days": 1,
        })
        rows = {row["source"]: row for row in report["sources"]}
        self.assertEqual(rows["expeditions"]["awarded_coins"], 100)
        self.assertEqual(rows["expeditions_salvage"]["omitted_coins"], 20)
        self.assertEqual(rows["coin_pouches"]["omitted_coins"], 50)

    def test_unused_and_inactive_days_never_bank_more_daily_allowance(self):
        trial = Trial(budget_config(100, active_days_per_week=1), empty_catalog(), 42)
        trial.daily(1)
        trial.coin_award(20, "coin_pouches")
        for day in range(2, 8):
            trial.daily(day)
        trial.daily(8)
        trial.coin_award(150, "expeditions")
        self.assertEqual(trial.coins, 120)
        self.assertEqual(trial.report()["reward_budget"]["summary"]["omitted_coins"], 50)

    def test_cap_resets_each_calendar_day_and_counts_capped_days_once(self):
        trial = Trial(budget_config(50), empty_catalog(), 42)
        for day in (1, 2):
            trial.daily(day)
            for _ in range(2):
                trial.coin_award(40, "expeditions")
        summary = trial.report()["reward_budget"]["summary"]
        self.assertEqual(summary, {"raw_coins": 160, "awarded_coins": 100,
                                   "omitted_coins": 60, "capped_days": 2})

    def test_consumed_pouch_excess_is_omitted_not_retained_for_tomorrow(self):
        pouch = SimpleNamespace(pk=1, item_type="coin_pouch", coin_value=500,
                                metadata={"coins": 500}, display_name="A pouch")
        catalog = Catalog({}, {1: pouch}, {}, {}, [], [], {}, "synthetic")
        trial = Trial(budget_config(50), catalog, 42)
        trial.inventory[1] = 2
        trial.daily(1)
        trial.daily(2)
        self.assertEqual(trial.coins, 50)
        self.assertEqual(trial.inventory[1], 0)
        self.assertEqual(trial.sink_totals["coin_pouch_opening"]["items"], 2)
        summary = trial.report()["reward_budget"]["summary"]
        self.assertEqual((summary["raw_coins"], summary["omitted_coins"]), (1000, 950))

    def test_nonpositive_awards_do_not_consume_daily_allowance(self):
        trial = Trial(budget_config(100), empty_catalog(), 42)
        for amount in (0, -100):
            trial.coin_award(amount, "expeditions")
        trial.coin_award(100, "coin_pouches")
        self.assertEqual(trial.report()["reward_budget"]["summary"], {
            "raw_coins": 100, "awarded_coins": 100, "omitted_coins": 0, "capped_days": 0,
        })

    def test_purchasing_spends_only_the_awarded_coins(self):
        trial = Trial(budget_config(50, economy=economy(offers=[offer(coin_price=75)])), empty_catalog(), 42)
        trial.day = 1
        trial.coin_award(100, "expeditions")
        trial.daily(1)
        self.assertEqual(trial.report()["economy"]["summary"]["purchases"], 0)
        self.assertEqual(trial.report()["economy"]["summary"]["coins_earned"], 50)
        self.assertEqual(trial.report()["reward_budget"]["summary"]["omitted_coins"], 50)

    def test_aggregate_source_rows_reconcile_and_trace_is_cumulative(self):
        pouch = SimpleNamespace(pk=1, item_type="coin_pouch", coin_value=500,
                                metadata={"coins": 500}, display_name="A pouch")
        catalog = Catalog({}, {1: pouch}, {}, {}, [], [], {}, "synthetic")
        original_daily = Trial.daily

        def daily_with_pouches(trial, day):
            if day in (1, 2):
                trial.inventory[1] += 1
            return original_daily(trial, day)

        with patch.object(Trial, "daily", daily_with_pouches):
            report = simulate_progression(budget_config(50, trials=2), catalog=catalog)
        summary = report["reward_budget"]["summary"]
        for key, expected in (("raw_coins", 1000), ("awarded_coins", 100), ("omitted_coins", 900), ("capped_days", 2)):
            self.assertEqual(summary[key], {"p10": expected, "p50": expected, "p90": expected, "mean": expected})
            self.assertEqual(report["trace"][-1][f"reward_budget_{key}_p50"], expected)
        for key in ("raw_coins", "awarded_coins", "omitted_coins"):
            self.assertEqual(sum(row[key]["mean"] for row in report["reward_budget"]["sources"]), summary[key]["mean"])
        self.assertEqual(report["reward_budget"]["daily_coins"], 50)
        self.assertTrue(report["reward_budget"]["assumptions"])


class ProgressionRewardBudgetCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def test_explicit_uncapped_policy_preserves_random_draws_and_progression(self):
        catalog = load_catalog()
        before = run_trial(quiet_config(reading_minutes=10, chores_per_day=2,
                                        project_minutes=20, expeditions_per_day=1), catalog, 42)
        after = run_trial(budget_config(None, reading_minutes=10, chores_per_day=2,
                                       project_minutes=20, expeditions_per_day=1), catalog, 42)
        self.assertEqual(before, after)
        summary = after["reward_budget"]["summary"]
        self.assertEqual(summary["raw_coins"], summary["awarded_coins"])
        self.assertEqual(summary["omitted_coins"], 0)

    def test_snapshot_budget_simulation_never_calls_sql_or_live_reward_writers(self):
        catalog = load_catalog()

        def forbid_sql(execute, sql, params, many, context):
            self.fail(f"Budget simulation touched SQL after snapshot: {sql[:100]}")

        with connection.execute_wrapper(forbid_sql), \
                patch("apps.rewards.services.CoinService.award_coins", side_effect=AssertionError("Live reward writer")), \
                patch("apps.rpg.services.InventoryItemService.open_coin_pouch", side_effect=AssertionError("Live inventory writer")):
            result = simulate_progression(budget_config(50, chores_per_day=2, project_minutes=20,
                                                       expeditions_per_day=1), catalog=catalog)
        summary = result["reward_budget"]["summary"]
        self.assertGreater(summary["raw_coins"]["mean"], 0)
        self.assertLessEqual(summary["awarded_coins"]["mean"], 30 * 50)
        self.assertEqual(summary["raw_coins"]["mean"], summary["awarded_coins"]["mean"] + summary["omitted_coins"]["mean"])
