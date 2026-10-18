"""Synthetic purchasing is a plan, never an account, redemption or cash-out."""
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase

from apps.rpg.content.loader import ContentPack
from apps.rpg.progression.catalog import Catalog, load_catalog
from apps.rpg.progression.engine import DEFAULTS, Trial, normalize_config, run_trial, simulate_progression, rules_fingerprint
from apps.rpg.progression.economy import aggregate_economy, METRICS


def quiet_config(**changes):
    return {
        **DEFAULTS, "horizon_days": 30, "trials": 1, "active_days_per_week": 7,
        "reading_minutes": 0, "project_minutes": 0, "chores_per_day": 0,
        "habits_per_day": 0, "movement_sessions_per_day": 0,
        "creations_per_day": 0, "journal_per_day": False, "expeditions_per_day": 0,
        **changes,
    }


def offer(**changes):
    return {
        "key": "outing", "label": "An outing", "kind": "real_world",
        "coin_price": 10, "repeat_every_days": 0, "stock": None,
        "family_cost_cents": 500, "print_minutes": 0, "print_grams": 0,
        **changes,
    }


def economy(**changes):
    return {"enabled": True, "offers": [offer()], **changes}


def empty_catalog():
    return Catalog({}, {}, {}, {}, [], [], {}, "synthetic")


class ProgressionEconomyTests(SimpleTestCase):
    def test_opt_in_config_is_anonymous_and_does_not_mutate_the_input(self):
        supplied = quiet_config(economy=economy())
        before = deepcopy(supplied)
        actual = normalize_config(supplied)
        self.assertEqual(supplied, before)
        self.assertTrue(actual["economy"]["enabled"])
        self.assertEqual(actual["economy"]["offers"][0]["coin_price"], 10)

    def test_money_and_cost_units_are_strict_bounded_cents(self):
        for change in ({"chore_money_cents": True}, {"monthly_family_budget_cents": -1},
                       {"start_date": "2026-02-30"}, {"start_date": "1999-12-31"},
                       {"user_id": 123}, {"offers": [offer(), offer()]},
                       {"offers": [offer(kind="digital_item")]},
                       {"offers": [offer(family_cost_cents=0.5)]},
                       {"offers": [offer(stock=-1)]},
                       {"offers": [offer()] * 13}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_config(quiet_config(economy=economy(**change)))

    def test_disabled_economy_preserves_progression_and_random_draws(self):
        base = quiet_config(reading_minutes=10, chores_per_day=1)
        before = run_trial(base, empty_catalog(), 42)
        after = run_trial({**base, "economy": economy(enabled=False, offers=[offer(coin_price=0)])}, empty_catalog(), 42)
        for key in ("trace", "milestones", "sources", "events", "finite_total"):
            self.assertEqual(before[key], after[key], key)

    def test_purchase_spends_coins_and_records_actual_first_purchase(self):
        trial = Trial(quiet_config(reading_minutes=10, economy=economy()), empty_catalog(), 42)
        trial.daily(1)
        self.assertEqual(trial.coins, 0)  # Five reading Coins plus five check-in Coins.
        self.assertEqual(trial.milestones["first_purchase"], 1)
        self.assertEqual(trial.milestones["first_reward"], 1)
        result = trial.report()["economy"]
        self.assertEqual(result["summary"]["coins_earned"], 10)
        self.assertEqual(result["summary"]["coins_spent"], 10)
        self.assertEqual(result["summary"]["family_cost_cents"], 500)
        self.assertEqual(result["summary"]["purchases"], 1)

    def test_affordability_does_not_override_a_zero_family_budget(self):
        trial = Trial(quiet_config(reading_minutes=10, economy=economy(monthly_family_budget_cents=0)), empty_catalog(), 42)
        trial.daily(1)
        result = trial.report()["economy"]
        self.assertEqual(result["offers"][0]["first_coin_affordable"], 1)
        self.assertIsNone(result["offers"][0]["first_purchase"])
        self.assertEqual(result["summary"]["coins_spent"], 0)
        self.assertEqual(result["summary"]["blocked_family_budget_visits"], 1)

    def test_real_calendar_months_reset_cost_caps(self):
        trial = Trial(quiet_config(reading_minutes=10, economy=economy(
            start_date="2026-01-31", monthly_family_budget_cents=500,
            offers=[offer(coin_price=0, repeat_every_days=1)],
        )), empty_catalog(), 42)
        for day in range(1, 4):
            trial.daily(day)
        result = trial.report()["economy"]
        self.assertEqual(result["summary"]["purchases"], 2)
        self.assertEqual([m["month"] for m in result["months"]], ["2026-01", "2026-02"])
        self.assertEqual([m["family_cost_cents"] for m in result["months"]], [500, 500])

    def test_priority_waits_and_flexible_policy_buys_a_lower_offer(self):
        rows = [offer(coin_price=100), offer(key="small", coin_price=5)]
        strict = Trial(quiet_config(reading_minutes=10, economy=economy(offers=rows)), empty_catalog(), 42)
        flexible = Trial(quiet_config(reading_minutes=10, economy=economy(
            offers=rows, purchase_strategy="buy_affordable")), empty_catalog(), 42)
        strict.daily(1)
        flexible.daily(1)
        self.assertEqual(strict.report()["economy"]["summary"]["purchases"], 0)
        self.assertEqual(flexible.report()["economy"]["summary"]["purchases"], 1)

    def test_free_stock_and_cooldown_are_enforced_without_double_purchasing(self):
        trial = Trial(quiet_config(economy=economy(offers=[offer(
            coin_price=0, repeat_every_days=2, stock=2, family_cost_cents=0,
        )])), empty_catalog(), 42)
        for day in range(1, 8):
            trial.daily(day)
        report = trial.report()["economy"]
        self.assertEqual(report["summary"]["purchases"], 2)
        self.assertEqual(report["offers"][0]["stock_remaining"], 0)

    def test_topup_respects_one_dollar_minimum_and_keeps_excess_coins(self):
        trial = Trial(quiet_config(chores_per_day=1, chore_coins=0, chore_xp=0,
            economy=economy(chore_money_cents=100, exchange_shortfalls=True,
                            offers=[offer(coin_price=16)])), empty_catalog(), 42)
        trial.daily(1)  # 5 check-in + 10 daily bonus; one Coin short.
        report = trial.report()["economy"]
        self.assertEqual(report["summary"]["money_earned_cents"], 100)
        self.assertEqual(report["summary"]["money_exchanged_cents"], 100)
        self.assertEqual(report["summary"]["coins_exchanged"], 10)
        self.assertEqual(trial.coins, 9)
        self.assertEqual(report["summary"]["parent_liability_cents"], 500)

    def test_insufficient_topup_never_debits_either_wallet(self):
        trial = Trial(quiet_config(chores_per_day=1, chore_coins=0, chore_xp=0,
            economy=economy(chore_money_cents=99, exchange_shortfalls=True,
                            offers=[offer(coin_price=16)])), empty_catalog(), 42)
        trial.daily(1)
        summary = trial.report()["economy"]["summary"]
        self.assertEqual((summary["money_remaining_cents"], summary["coins_exchanged"], summary["coins_spent"]), (99, 0, 0))
        self.assertEqual(trial.coins, 15)

    def test_project_money_uses_live_entry_rounding_not_raw_hour_fraction(self):
        trial = Trial(quiet_config(project_minutes=20, economy=economy(
            project_hourly_money_cents=800, offers=[])), empty_catalog(), 42)
        trial.daily(1)
        self.assertEqual(trial.report()["economy"]["summary"]["money_earned_cents"], 264)

    def test_print_price_and_independent_resource_caps_use_real_ceiling(self):
        print_offer = offer(kind="printing", print_minutes=61, print_grams=20, coin_price=999)
        config = quiet_config(economy=economy(offers=[print_offer], printing={
            "minutes_per_coin": 2, "monthly_minutes": 60, "monthly_grams": None,
        }))
        self.assertEqual(normalize_config(config)["economy"]["offers"][0]["coin_price"], 31)
        trial = Trial(config, empty_catalog(), 42)
        trial.daily(1)
        summary = trial.report()["economy"]["summary"]
        self.assertEqual(summary["blocked_print_budget_visits"], 1)
        self.assertEqual(summary["coins_spent"], 0)

    def test_no_nominal_inventory_price_is_added_to_either_wallet(self):
        item = SimpleNamespace(pk=999, item_type="quest_scroll", coin_value=1_000_000)
        catalog = Catalog({}, {999: item}, {}, {}, [], [], {}, "synthetic")
        trial = Trial(quiet_config(economy=economy()), catalog, 42)
        trial.inventory[999] = 10000
        trial.daily(1)
        summary = trial.report()["economy"]["summary"]
        self.assertEqual((summary["coins_earned"], summary["money_earned_cents"]), (0, 0))

    def test_aggregate_reports_are_alternative_children_not_summed_household(self):
        result = simulate_progression(quiet_config(trials=2, reading_minutes=10,
            economy=economy()), catalog=empty_catalog())
        report = result["economy"]
        self.assertEqual(report["summary"]["family_cost_cents"]["p50"], 500)
        self.assertEqual(report["offers"][0]["first_purchase"]["completion_rate"], 1)
        self.assertEqual(report["summary"]["coins_earned"]["p50"] + report["summary"]["coins_exchanged"]["p50"]
                         - report["summary"]["coins_spent"]["p50"], report["summary"]["coin_balance"]["p50"])

    def test_parent_liability_is_aggregated_after_adding_each_childs_obligations(self):
        rows = []
        for money, cost in ((100, 0), (0, 100)):
            summary = {key: 0 for key in METRICS}
            summary.update(money_remaining_cents=money, family_cost_cents=cost, parent_liability_cents=100)
            rows.append({"economy": {"summary": summary, "offers": [], "months": []}})
        result = aggregate_economy(rows, normalize_config(quiet_config(economy=economy(offers=[])))["economy"])
        self.assertEqual(result["summary"]["parent_liability_cents"]["p50"], 100)
        self.assertEqual(result["summary"]["money_remaining_cents"]["p50"], 0)
        self.assertEqual(result["summary"]["family_cost_cents"]["p50"], 0)

    def test_budget_rejection_cannot_exchange_money_before_declining_purchase(self):
        trial = Trial(quiet_config(chores_per_day=1, chore_coins=0, chore_xp=0,
            economy=economy(chore_money_cents=500, exchange_shortfalls=True,
                            monthly_family_budget_cents=0, offers=[offer(coin_price=16)])), empty_catalog(), 42)
        trial.daily(1)
        summary = trial.report()["economy"]["summary"]
        self.assertEqual((summary["money_remaining_cents"], summary["coins_exchanged"], summary["coins_spent"]), (500, 0, 0))

    def test_monthly_exchange_limit_prevents_an_unfunded_topup(self):
        trial = Trial(quiet_config(chores_per_day=1, chore_coins=0, chore_xp=0,
            economy=economy(chore_money_cents=500, exchange_shortfalls=True,
                            monthly_exchange_limit_cents=99, offers=[offer(coin_price=16)])), empty_catalog(), 42)
        trial.daily(1)
        self.assertEqual(trial.report()["economy"]["summary"]["coins_exchanged"], 0)

    def test_economy_budget_is_rejected_before_any_catalog_read(self):
        with patch("apps.rpg.progression.engine.load_catalog", side_effect=AssertionError("No catalog read")):
            with self.assertRaisesMessage(ValueError, "work units"):
                simulate_progression({"trials": 40, "economy": economy(offers=[offer(key=f"offer-{i}") for i in range(12)])})

    def test_exchange_rate_changes_invalidate_saved_economy_forecasts(self):
        before = rules_fingerprint()
        with self.settings(COINS_PER_DOLLAR=20):
            self.assertNotEqual(rules_fingerprint(), before)

    def test_cash_topup_can_buy_before_the_pre_exchange_wallet_is_affordable(self):
        trial = Trial(quiet_config(chores_per_day=1, chore_coins=0, chore_xp=0,
            economy=economy(chore_money_cents=100, exchange_shortfalls=True,
                            offers=[offer(coin_price=16)])), empty_catalog(), 42)
        trial.daily(1)
        row = trial.report()["economy"]["offers"][0]
        self.assertIsNone(row["first_coin_affordable"])
        self.assertEqual(row["first_purchase"], 1)

    def test_free_printing_still_uses_calendar_resource_caps(self):
        trial = Trial(quiet_config(economy=economy(offers=[offer(kind="printing", print_minutes=60,
            print_grams=20, repeat_every_days=1)], printing={"monthly_grams": 20})), empty_catalog(), 42)
        trial.daily(1)
        trial.daily(2)
        summary = trial.report()["economy"]["summary"]
        self.assertEqual((summary["coins_spent"], summary["purchases"], summary["print_grams"]), (0, 1, 20))
        self.assertEqual(summary["blocked_print_budget_visits"], 1)


class ProgressionEconomyCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def test_loaded_catalog_money_exchange_and_purchases_cannot_read_or_write_sql(self):
        catalog = load_catalog()

        def forbid_sql(execute, sql, params, many, context):
            self.fail(f"Anonymous economy accessed the database after its global snapshot: {sql[:100]}")

        config = quiet_config(chores_per_day=1, chore_coins=0, chore_xp=0, economy=economy(
            chore_money_cents=1_000_000, exchange_shortfalls=True,
            offers=[offer(coin_price=10_000)],
        ))
        with connection.execute_wrapper(forbid_sql):
            result = simulate_progression(config, catalog=catalog)
        summary = result["economy"]["summary"]
        self.assertGreater(summary["coins_exchanged"]["p50"], 0)
        self.assertEqual(summary["purchases"]["p50"], 1)
        self.assertEqual(summary["coins_earned"]["p50"] + summary["coins_exchanged"]["p50"]
                         - summary["coins_spent"]["p50"], summary["coin_balance"]["p50"])

    def test_disabled_purchases_preserve_actual_catalog_progression_and_rng(self):
        catalog = load_catalog()
        before = run_trial(quiet_config(reading_minutes=10, chores_per_day=1), catalog, 42)
        after = run_trial(quiet_config(reading_minutes=10, chores_per_day=1,
            economy=economy(enabled=False, chore_money_cents=100, exchange_shortfalls=True,
                            offers=[offer(coin_price=0)])), catalog, 42)
        for key in ("trace", "milestones", "sources", "events", "finite_total"):
            self.assertEqual(before[key], after[key], key)
