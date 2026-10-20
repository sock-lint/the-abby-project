"""Criteria judge server-produced paired evidence, never approve live rewards."""
from copy import deepcopy

from django.test import SimpleTestCase

from apps.rpg.progression.feedback import (
    evaluate_comparison,
    feedback_fingerprint,
    feedback_metadata,
    normalize_targets,
)


def report(*, cap=None, earned=1000, balance=600, cost=500, completed=10, day=30):
    milestone = {
        "completion_rate": completed / 10, "completed_trials": completed,
        "trials": 10, "p50_days": day,
    }
    return {
        "schema_version": 1, "engine_version": "test-engine",
        "rules_fingerprint": "rules", "source_commit": "unavailable",
        "catalog": {"fingerprint": "catalog"},
        "config": {
            "horizon_days": 90, "trials": 10, "seed": 1000,
            "reward_budget": {"daily_coins": cap},
            "economy": {"enabled": True, "offers": [{"key": "outing"}]},
        },
        "summary": {"coins_p50": balance, "finite_content_total": 100},
        "economy": {
            "enabled": True,
            "summary": {"coins_earned": {"p50": earned}, "family_cost_cents": {"p50": cost}},
            "offers": [{"key": "outing", "first_purchase": dict(milestone)}],
        },
        "milestones": [{"key": "finite_80", **milestone}],
    }


class ProgressionFeedbackTests(SimpleTestCase):
    def test_feedback_fingerprint_binds_the_evaluator_independently_of_engine_rules(self):
        actual = feedback_fingerprint()
        self.assertEqual(len(actual), 64)
        self.assertEqual(actual, feedback_fingerprint())
        self.assertTrue(all(character in "0123456789abcdef" for character in actual))
        self.assertEqual(feedback_metadata()["fingerprint"], actual)

    def test_targets_are_bounded_known_metrics_with_explicit_inclusive_bounds(self):
        supplied = [{"metric": "closing_coins_p50", "min": 0, "max": 1000}]
        self.assertEqual(normalize_targets(supplied), supplied)
        supplied[0]["min"] = 5
        self.assertEqual(normalize_targets([{"metric": "closing_coins_p50", "max": 0}]), [
            {"metric": "closing_coins_p50", "min": None, "max": 0},
        ])

    def test_invalid_targets_never_become_unbounded_passing_checks(self):
        invalid = (
            None, {}, True, [None], [{"metric": "config.child_id", "max": 1}],
            [{"metric": "closing_coins_p50"}],
            [{"metric": "closing_coins_p50", "min": None, "max": None}],
            [{"metric": "closing_coins_p50", "max": True}],
            [{"metric": "closing_coins_p50", "max": "100"}],
            [{"metric": "closing_coins_p50", "max": float("nan")}],
            [{"metric": "closing_coins_p50", "max": float("inf")}],
            [{"metric": "closing_coins_p50", "max": 10 ** 1000}],
            [{"metric": "closing_coins_p50", "min": -1}],
            [{"metric": "closing_coins_p50", "min": 2, "max": 1}],
            [{"metric": "priority_purchase_reached_rate", "max": 1.1}],
            [{"metric": "finite_80_day_p50", "max": 366}],
            [{"metric": "closing_coins_p50", "max": 10, "path": "summary.coins_p50"}],
            [{"metric": "closing_coins_p50", "max": 10}] * 2,
            [{"metric": key, "max": 1} for key in (
                "coins_earned_p50", "closing_coins_p50", "fulfillment_cost_cents_p50",
                "priority_purchase_day_p50", "priority_purchase_reached_rate",
                "finite_80_day_p50", "finite_80_reached_rate",
            )],
        )
        for supplied in invalid:
            with self.subTest(supplied=supplied), self.assertRaises(ValueError):
                normalize_targets(supplied)

    def test_candidate_bounds_decide_pass_and_delta_is_candidate_minus_control(self):
        control, candidate = report(), report(cap=100, earned=800, balance=400)
        before = deepcopy((control, candidate))
        result = evaluate_comparison(control, candidate, [
            {"metric": "coins_earned_p50", "min": 800, "max": 800},
            {"metric": "closing_coins_p50", "max": 400},
        ])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["checks"][0]["delta"], -200)
        self.assertEqual(result["checks"][0]["candidate"]["value"], 800)
        self.assertEqual((control, candidate), before)
        self.assertFalse(result["proposal"]["live_ready"])

    def test_a_failed_guardrail_keeps_the_result_failed_with_missing_other_evidence(self):
        candidate = report(cap=100, balance=1001, completed=0, day=None)
        result = evaluate_comparison(report(), candidate, [
            {"metric": "closing_coins_p50", "max": 1000},
            {"metric": "finite_80_day_p50", "min": 60},
        ])
        self.assertEqual(result["status"], "fail")
        self.assertEqual([row["status"] for row in result["checks"]], ["fail", "insufficient"])

    def test_no_targets_is_unconfigured_instead_of_vacuously_passed(self):
        result = evaluate_comparison(report(), report(cap=100), [])
        self.assertEqual(result["status"], "unconfigured")
        self.assertEqual(result["checks"], [])

    def test_unreached_dates_stay_null_and_keep_all_trial_denominators(self):
        result = evaluate_comparison(report(), report(cap=100, completed=0, day=None), [
            {"metric": "priority_purchase_day_p50", "max": 90},
            {"metric": "finite_80_day_p50", "min": 60},
            {"metric": "priority_purchase_reached_rate", "min": 0.8},
        ])
        self.assertEqual(result["status"], "fail")
        for check in result["checks"][:2]:
            self.assertEqual(check["status"], "insufficient")
            self.assertEqual(check["candidate"]["value"], None)
            self.assertEqual(check["candidate"]["completed_trials"], 0)
            self.assertEqual(check["candidate"]["trials"], 10)
            self.assertIsNone(check["delta"])
        self.assertEqual(result["checks"][2]["candidate"]["value"], 0)

    def test_partial_completion_is_visible_and_rate_has_its_own_guardrail(self):
        result = evaluate_comparison(report(), report(cap=100, completed=2, day=20), [
            {"metric": "priority_purchase_day_p50", "max": 30},
            {"metric": "priority_purchase_reached_rate", "min": 0.8},
        ])
        check = result["checks"][0]
        self.assertEqual(check["candidate"], {"value": 20, "completed_trials": 2, "trials": 10})
        self.assertEqual(result["status"], "fail")

    def test_missing_control_evidence_cannot_become_a_passing_comparison(self):
        result = evaluate_comparison(report(completed=0, day=None), report(cap=100), [
            {"metric": "priority_purchase_day_p50", "max": 90},
        ])
        self.assertEqual(result["status"], "insufficient")
        self.assertIsNone(result["checks"][0]["delta"])

    def test_trial_denominators_are_verified_and_rates_come_from_counts(self):
        candidate = report(cap=100, completed=2, day=20)
        candidate["economy"]["offers"][0]["first_purchase"]["completion_rate"] = 1
        result = evaluate_comparison(report(), candidate, [
            {"metric": "priority_purchase_reached_rate", "min": 0.8},
        ])
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"][0]["candidate"]["value"], 0.2)
        candidate["economy"]["offers"][0]["first_purchase"]["trials"] = 2
        result = evaluate_comparison(report(), candidate, [
            {"metric": "priority_purchase_reached_rate", "min": 0.8},
        ])
        self.assertEqual(result["status"], "insufficient")

    def test_first_priority_offer_is_used_instead_of_any_first_purchase(self):
        candidate = report(cap=100, completed=0, day=None)
        candidate["economy"]["offers"].append({
            "key": "small-prize", "first_purchase": {
                "completion_rate": 1, "completed_trials": 10, "trials": 10, "p50_days": 1,
            },
        })
        result = evaluate_comparison(report(), candidate, [{"metric": "priority_purchase_day_p50", "max": 90}])
        self.assertEqual(result["status"], "insufficient")

    def test_disabled_purchasing_has_no_cost_or_purchase_evidence(self):
        control, candidate = report(), report(cap=100)
        for current in (control, candidate):
            current["config"]["economy"] = {"enabled": False}
            current["economy"] = {"enabled": False}
        result = evaluate_comparison(control, candidate, [
            {"metric": "coins_earned_p50", "min": 0},
            {"metric": "fulfillment_cost_cents_p50", "max": 500},
            {"metric": "priority_purchase_reached_rate", "min": 0.5},
        ])
        self.assertEqual(result["checks"][0]["candidate"]["value"], 600)
        self.assertEqual([row["status"] for row in result["checks"]], ["pass", "insufficient", "insufficient"])
        self.assertEqual(result["status"], "insufficient")

    def test_empty_finite_catalog_is_not_evidence_of_zero_days_runway(self):
        candidate = report(cap=100)
        candidate["summary"]["finite_content_total"] = 0
        result = evaluate_comparison(report(), candidate, [{"metric": "finite_80_reached_rate", "max": 1}])
        self.assertEqual(result["status"], "insufficient")

    def test_criteria_require_the_same_routine_seed_catalog_and_rules(self):
        mutations = (
            lambda r: r["config"].update(seed=2),
            lambda r: r["config"].update(horizon_days=30),
            lambda r: r["catalog"].update(fingerprint="other"),
            lambda r: r.update(rules_fingerprint="other"),
            lambda r: r.update(engine_version="other"),
            lambda r: r.update(source_commit="other"),
            lambda r: r["config"]["reward_budget"].update(daily_coins=None),
        )
        for mutation in mutations:
            candidate = report(cap=100)
            mutation(candidate)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evaluate_comparison(report(), candidate, [])
        with self.assertRaises(ValueError):
            evaluate_comparison(report(cap=100), report(cap=50), [])

    def test_metadata_is_detached_and_explicit_about_remaining_live_design_work(self):
        metadata = feedback_metadata()
        self.assertEqual(metadata["max_targets"], 6)
        self.assertEqual(len(metadata["metrics"]), 16)
        self.assertTrue({"challenge_waiting_visits_p50", "challenge_available_visits_p50", "challenge_unreachable_total"}
                        <= {row["key"] for row in metadata["metrics"]})
        proposal = metadata["proposal"]
        self.assertEqual(proposal["status"], "lab_prototype")
        self.assertTrue(proposal["evaluated_by_current_engine"])
        self.assertFalse(proposal["live_ready"])
        self.assertTrue(proposal["blocks_live_change"])
        self.assertEqual(proposal["daily_new_commitment_coins"], 100)
        self.assertEqual(proposal["allocations"], {"expeditions": 75, "activity_pouches": 25})
        self.assertEqual({row["key"] for row in proposal["blockers"]}, {
            "commitment_model", "promised_rewards", "coin_boosts", "content_reachability",
        })
        metadata["metrics"][0]["label"] = "edited"
        proposal["expedition_tiers"][0]["coins"] = 0
        self.assertNotEqual(feedback_metadata(), metadata)

    def test_commitment_prototype_is_an_alternative_to_the_income_envelope(self):
        control, candidate = report(), report()
        candidate["config"]["reward_commitment"] = {"enabled": True}
        result = evaluate_comparison(control, candidate, [])
        self.assertEqual(result["status"], "unconfigured")
        for invalid in ({"enabled": 1}, {"enabled": []}, {"enabled": True, "daily_coins": 50}):
            candidate["config"]["reward_commitment"] = invalid
            with self.assertRaises(ValueError):
                evaluate_comparison(control, candidate, [])
        candidate["config"]["reward_commitment"] = {"enabled": True}
        candidate["config"]["reward_budget"]["daily_coins"] = 100
        with self.assertRaises(ValueError):
            evaluate_comparison(control, candidate, [])
        candidate["config"]["reward_budget"]["daily_coins"] = None
        control["config"]["reward_commitment"] = {"enabled": True}
        with self.assertRaises(ValueError):
            evaluate_comparison(control, candidate, [])

    def test_quota_pair_accepts_each_unchanged_coin_policy_but_rejects_a_mixed_hypothesis(self):
        for cap, committed in ((None, False), (75, False), (None, True)):
            control, candidate = report(cap=cap), report(cap=cap)
            for current in (control, candidate):
                current["config"]["reward_commitment"] = {"enabled": committed}
            candidate["config"]["expedition_budget"] = {"daily_launches": 2, "daily_items": 3}
            self.assertEqual(evaluate_comparison(control, candidate, [])["status"], "unconfigured")
            candidate["config"]["reward_commitment"]["enabled"] = not committed
            with self.assertRaises(ValueError):
                evaluate_comparison(control, candidate, [])
            candidate["config"]["reward_commitment"]["enabled"] = committed
            control["config"]["expedition_budget"] = {"daily_items": 1}
            with self.assertRaises(ValueError):
                evaluate_comparison(control, candidate, [])

    def test_quota_and_first_grown_criteria_preserve_missing_evidence_and_denominators(self):
        control, candidate = report(), report()
        candidate["config"]["expedition_budget"] = {"daily_items": 3}
        for current in (control, candidate):
            current["expedition_budget"] = {"summary": {
                "launched_trips": {"p50": 20}, "slots_promised": {"p50": 40}, "empty_trips": {"p50": 2},
            }}
            current["milestones"].append({"key": "first_mount", "trials": 10, "completed_trials": 5, "p50_days": 21})
        targets = [
            {"metric": "expedition_launches_p50", "max": 20},
            {"metric": "expedition_items_promised_p50", "max": 40},
            {"metric": "expedition_empty_trips_p50", "max": 2},
            {"metric": "first_mount_day_p50", "max": 21},
            {"metric": "first_mount_reached_rate", "min": 0.5},
        ]
        result = evaluate_comparison(control, candidate, targets)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["checks"][3]["candidate"], {"value": 21, "completed_trials": 5, "trials": 10})
        self.assertEqual(result["checks"][4]["candidate"]["value"], 0.5)
        candidate["expedition_budget"]["summary"].pop("slots_promised")
        candidate["milestones"][-1]["completed_trials"] = 0
        candidate["milestones"][-1]["p50_days"] = None
        result = evaluate_comparison(control, candidate, targets)
        self.assertEqual(result["checks"][1]["status"], "insufficient")
        self.assertEqual(result["checks"][3]["status"], "insufficient")
        self.assertEqual(result["checks"][4]["candidate"]["value"], 0)

    def test_native_reports_supply_earned_cost_and_priority_metrics_without_database_access(self):
        from apps.rpg.progression.engine import simulate_progression
        from apps.rpg.tests.test_progression_economy import economy, empty_catalog, quiet_config

        config = quiet_config(horizon_days=30, trials=2, reading_minutes=10, economy=economy())
        control = simulate_progression(config, catalog=empty_catalog())
        candidate = simulate_progression({**config, "reward_budget": {"daily_coins": 100}}, catalog=empty_catalog())
        result = evaluate_comparison(control, candidate, [
            {"metric": "coins_earned_p50", "min": 1},
            {"metric": "closing_coins_p50", "min": 0},
            {"metric": "fulfillment_cost_cents_p50", "min": 500, "max": 500},
            {"metric": "priority_purchase_day_p50", "min": 1, "max": 1},
            {"metric": "priority_purchase_reached_rate", "min": 1},
        ])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["checks"][0]["candidate"]["value"], candidate["economy"]["summary"]["coins_earned"]["p50"])
