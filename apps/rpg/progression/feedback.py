"""Bounded criteria for paired Lab reports and an explicit design prototype.

These functions inspect detached, server-generated simulation reports only. A
passing check is evidence for further design work, never a publication grant
or proof that the simulated commitment prototype is ready for live rewards.
"""
from copy import deepcopy
import hashlib
import inspect
import math
import sys


MAX_TARGETS = 6
METRICS = (
    {"key": "coins_earned_p50", "label": "Median Coins earned", "unit": "coins", "min_value": 0, "max_value": 1_000_000_000},
    {"key": "closing_coins_p50", "label": "Median closing Coin balance", "unit": "coins", "min_value": 0, "max_value": 1_000_000_000},
    {"key": "fulfillment_cost_cents_p50", "label": "Median estimated fulfillment cost", "unit": "cents", "min_value": 0, "max_value": 1_000_000_000},
    {"key": "priority_purchase_day_p50", "label": "Priority reward purchase day, among completing journeys", "unit": "days", "min_value": 0, "max_value": 365},
    {"key": "priority_purchase_reached_rate", "label": "Journeys purchasing the priority reward", "unit": "rate", "min_value": 0, "max_value": 1},
    {"key": "finite_80_day_p50", "label": "Day reaching 80% of modeled content, among completing journeys", "unit": "days", "min_value": 0, "max_value": 365},
    {"key": "finite_80_reached_rate", "label": "Journeys reaching 80% of modeled content", "unit": "rate", "min_value": 0, "max_value": 1},
    {"key": "expedition_launches_p50", "label": "Median expedition launches", "unit": "trips", "min_value": 0, "max_value": 1_000_000},
    {"key": "expedition_items_promised_p50", "label": "Median expedition item promises", "unit": "items", "min_value": 0, "max_value": 1_000_000},
    {"key": "expedition_empty_trips_p50", "label": "Median empty expedition trips", "unit": "trips", "min_value": 0, "max_value": 1_000_000},
    {"key": "first_mount_day_p50", "label": "First grown companion day, among completing journeys", "unit": "days", "min_value": 0, "max_value": 365},
    {"key": "first_mount_reached_rate", "label": "Journeys reaching a grown companion", "unit": "rate", "min_value": 0, "max_value": 1},
    {"key": "challenge_waiting_visits_p50", "label": "Median active visits waiting for a one-off challenge gate", "unit": "visits", "min_value": 0, "max_value": 365},
    {"key": "challenge_available_visits_p50", "label": "Median active visits with an available one-off challenge", "unit": "visits", "min_value": 0, "max_value": 365},
    {"key": "challenge_unreachable_total", "label": "Modeled finite targets made unreachable by challenge gates", "unit": "targets", "min_value": 0, "max_value": 1_000_000},
    {"key": "gated_challenge_min_completion_rate", "label": "Lowest completion rate among configured challenges in the native routine subset", "unit": "rate", "min_value": 0, "max_value": 1},
)
METRIC_BY_KEY = {row["key"]: row for row in METRICS}

PROPOSAL = {
    "status": "lab_prototype",
    "live_ready": False,
    "blocks_live_change": True,
    "evaluated_by_current_engine": True,
    "title": "100-Coin daily commitment prototype",
    "daily_new_commitment_coins": 100,
    "allocations": {"expeditions": 75, "activity_pouches": 25},
    "expedition_tiers": [
        {"key": "short", "duration_minutes": 120, "coins": 10, "item_slots": 1},
        {"key": "standard", "duration_minutes": 240, "coins": 25, "item_slots": 2},
        {"key": "long", "duration_minutes": 480, "coins": 50, "item_slots": 3},
    ],
    "pouch_face_values": [5, 10, 15, 50, 100, 250, 500],
    "principles": [
        "This hypothetical candidate retains its 10/25/50 expedition table and original pouch values. The installed control follows the current production rates and smaller versioned random pouches.",
        "Reserve new expedition direct Coins, full pouch value and maximum possible positive cosmetic salvage before launch. Establish any reduced direct amount before the child commits; never trim a claim.",
        "Reserve a random activity pouch's full face value before granting it. Only candidates whose full value fits the remaining allocation are eligible before the draw; never grant a partial pouch or reroll saved loot.",
        "Each child's new commitments reset daily without banking unused allowance. Redemptions may exceed 100 Coins on a later day because previously established rewards are paid in full.",
        "Preserve owned pouches, frozen expedition loot and authored challenge promises. Fixed authored rewards stay outside this proposed random-grant allocation and must be reported separately.",
        "Track reserved, paid and outstanding Coin values separately, along with empty item slots, zero-Coin expeditions and permanently unavailable content.",
    ],
    "blockers": [
        {
            "key": "commitment_model",
            "title": "Evaluate the prototype against explicit targets",
            "detail": "The Lab now separately models the 75/25 allocation, fixed expedition rewards and full-value pouch reservations. The income-envelope candidate remains a separate policy that omits payout excess.",
            "next_action": "Save paired 90-day and 365-day comparisons with income, purchasing and content-access targets; record the design decision and affected acquisition paths before implementing live rules.",
        },
        {
            "key": "promised_rewards",
            "title": "Preserve every established reward",
            "detail": "The in-memory model pays established rewards fully. Production has no corresponding reservation protocol; existing pouch stacks read shared item definitions rather than a per-unit face-value snapshot.",
            "next_action": "Specify versioned reward definitions and reservation records; test full redemption, late claims, retries, concurrent launches and the accounting of outstanding promises.",
        },
        {
            "key": "coin_boosts",
            "title": "Specify Lucky Coin timing",
            "detail": "Live Lucky Coin can double direct expedition Coins at claim. Consumable effects are excluded from both Lab policies, so neither candidate proves a live maximum payout.",
            "next_action": "Decide when boosted value is established and reserved, then simulate and test activation, expiry and delayed claims without changing prior promises.",
        },
        {
            "key": "content_reachability",
            "title": "Check pouch and collection access",
            "detail": "The prototype reports filtered grants and unavailable finite targets because full-value reservations change acquisition paths. Missing paths are not additional playable runway, and source-level availability does not guarantee timely completion.",
            "next_action": "Audit every affected acquisition path, first-reward pacing, empty returns and collection milestones; use the content workbench for new reward versions and a reviewed code change for expedition policy.",
        },
    ],
}


def feedback_metadata():
    """Return detached choices for authoring criteria and planning next actions."""
    from .expedition_budget import EXPEDITION_BUDGET_DEFAULTS, EXPEDITION_BUDGET_LIMITS

    return {"max_targets": MAX_TARGETS, "metrics": deepcopy(list(METRICS)), "proposal": deepcopy(PROPOSAL),
            "expedition_budget_defaults": deepcopy(EXPEDITION_BUDGET_DEFAULTS),
            "expedition_budget_limits": deepcopy(EXPEDITION_BUDGET_LIMITS),
            "fingerprint": feedback_fingerprint()}


def feedback_fingerprint():
    """Bind saved evaluations to the exact criteria and proposed-design code."""
    return hashlib.sha256(inspect.getsource(sys.modules[__name__]).encode("utf-8")).hexdigest()


def _number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def normalize_targets(supplied):
    """Accept only bounded, explicit thresholds against enumerated metrics."""
    if not isinstance(supplied, list) or len(supplied) > MAX_TARGETS:
        raise ValueError(f"Targets must be a list of at most {MAX_TARGETS} criteria.")
    result, seen = [], set()
    for target in supplied:
        if not isinstance(target, dict) or set(target) - {"metric", "min", "max"}:
            raise ValueError("Each target accepts only metric, min and max.")
        metric = target.get("metric")
        if not isinstance(metric, str) or metric not in METRIC_BY_KEY or metric in seen:
            raise ValueError("Targets require distinct supported metric choices.")
        spec = METRIC_BY_KEY[metric]
        lower, upper = target.get("min"), target.get("max")
        if lower is None and upper is None:
            raise ValueError("Each target requires an explicit minimum or maximum.")
        for value in (lower, upper):
            if value is not None and (not _number(value) or not spec["min_value"] <= value <= spec["max_value"]):
                raise ValueError(f"Invalid bound for {metric}.")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("A target minimum cannot exceed its maximum.")
        result.append({"metric": metric, "min": lower, "max": upper})
        seen.add(metric)
    return result


def _check_pair(control, candidate):
    """Defense in depth; the caller generates both reports from one snapshot."""
    from .expedition_budget import normalize_expedition_budget
    from .challenge_gates import normalize_challenge_gates

    configs, quotas, coin_policies, gates = [], [], [], []
    for report in (control, candidate):
        config = report.get("config")
        if not isinstance(config, dict) or not isinstance(config.get("reward_budget"), dict):
            raise ValueError("Comparison requires normalized server-generated reports.")
        commitment = config.get("reward_commitment", {"enabled": False})
        if (not isinstance(commitment, dict) or set(commitment) != {"enabled"}
                or type(commitment["enabled"]) is not bool):
            raise ValueError("Comparison requires a normalized commitment policy.")
        cap = config["reward_budget"].get("daily_coins")
        if ((cap is not None and (type(cap) is not int or not 0 <= cap <= 100_000))
                or (commitment["enabled"] and cap is not None)):
            raise ValueError("Comparison requires one valid Coin policy per report.")
        quota = config.get("expedition_budget", {})
        if not isinstance(quota, dict):
            raise ValueError("Comparison requires normalized expedition quotas.")
        quotas.append(normalize_expedition_budget(quota))
        gates.append(normalize_challenge_gates(config.get("challenge_gates", {})))
        coin_policies.append((cap, commitment["enabled"]))
        configs.append({key: value for key, value in config.items()
                        if key not in {"reward_budget", "reward_commitment", "expedition_budget", "challenge_gates"}})
    if configs[0] != configs[1]:
        raise ValueError("Control and candidate must use the same routine, seeds and purchasing assumptions.")
    unlimited = normalize_expedition_budget({})
    if gates[0] != gates[1]:
        if (gates[0]["mode"] != "current" or gates[1]["mode"] not in {"milestones", "milestone_tenure"}
                or not gates[0]["rules"]
                or {key: value for key, value in gates[0].items() if key != "mode"}
                != {key: value for key, value in gates[1].items() if key != "mode"}):
            raise ValueError("Challenge-gate comparisons must retain one recipe and change only the current control's gate mode.")
        if quotas[0] != quotas[1] or coin_policies[0] != coin_policies[1]:
            raise ValueError("Challenge-gate comparisons must retain the same Coin rules and expedition quotas.")
    elif quotas[0] != unlimited:
        raise ValueError("The control must use unlimited expedition quotas.")
    elif quotas[1] != unlimited:
        if coin_policies[0] != coin_policies[1]:
            raise ValueError("Quota comparisons must retain the same Coin rules in both reports.")
    elif gates[0] == gates[1]:
        if coin_policies[0] != (None, False):
            raise ValueError("The Coin-policy control must use installed reward rules.")
        cap, committed = coin_policies[1]
        if not committed and cap is None:
            raise ValueError("The candidate requires a Coin hypothesis or expedition quotas.")
    for key in ("schema_version", "engine_version", "rules_fingerprint", "source_commit"):
        if key not in control or control[key] != candidate.get(key):
            raise ValueError("Control and candidate must share the same engine and rule bindings.")
    fingerprint = control.get("catalog", {}).get("fingerprint")
    if not fingerprint or fingerprint != candidate.get("catalog", {}).get("fingerprint"):
        raise ValueError("Control and candidate must share one catalog snapshot.")


def _observation(value, trials, *, completed=None):
    if not _number(value) or value < 0:
        value = None
    return {"value": value, "completed_trials": completed, "trials": trials}


def _milestone_observations(row, trials, horizon):
    completed = row.get("completed_trials") if isinstance(row, dict) else None
    denominator = row.get("trials") if isinstance(row, dict) else None
    if type(completed) is not int or type(denominator) is not int or denominator != trials or not 0 <= completed <= trials:
        unknown = _observation(None, trials)
        return unknown, dict(unknown)
    day = row.get("p50_days")
    if not completed or not _number(day) or not 1 <= day <= horizon:
        day = None
    return (_observation(day, trials, completed=completed),
            _observation(completed / trials, trials, completed=completed))


def _measure(report):
    trials, horizon = report["config"]["trials"], report["config"]["horizon_days"]
    summary, economy = report.get("summary", {}), report.get("economy", {})
    result = {key: _observation(None, trials) for key in METRIC_BY_KEY}
    result["closing_coins_p50"] = _observation(summary.get("coins_p50"), trials)
    if economy.get("enabled"):
        totals = economy.get("summary", {})
        result["coins_earned_p50"] = _observation(totals.get("coins_earned", {}).get("p50"), trials)
        result["fulfillment_cost_cents_p50"] = _observation(totals.get("family_cost_cents", {}).get("p50"), trials)
        offers = economy.get("offers", [])
        expected = report["config"].get("economy", {}).get("offers", [])
        if offers and expected and offers[0].get("key") == expected[0].get("key"):
            result["priority_purchase_day_p50"], result["priority_purchase_reached_rate"] = _milestone_observations(
                offers[0].get("first_purchase"), trials, horizon,
            )
    else:
        # Without purchasing there are no wages, exchanges or Coin sinks, so
        # the closing balance is also the median of activity Coins earned.
        result["coins_earned_p50"] = _observation(summary.get("coins_p50"), trials)
    if _number(summary.get("finite_content_total")) and summary["finite_content_total"] > 0:
        row = next((row for row in report.get("milestones", []) if row.get("key") == "finite_80"), None)
        result["finite_80_day_p50"], result["finite_80_reached_rate"] = _milestone_observations(row, trials, horizon)
    row = next((row for row in report.get("milestones", []) if row.get("key") == "first_mount"), None)
    result["first_mount_day_p50"], result["first_mount_reached_rate"] = _milestone_observations(row, trials, horizon)
    expedition_summary = report.get("expedition_budget", {}).get("summary", {})
    for metric, counter in (
        ("expedition_launches_p50", "launched_trips"),
        ("expedition_items_promised_p50", "slots_promised"),
        ("expedition_empty_trips_p50", "empty_trips"),
    ):
        result[metric] = _observation(expedition_summary.get(counter, {}).get("p50"), trials)
    gates = report.get("challenge_gates", {})
    visits = gates.get("visits", {})
    result["challenge_waiting_visits_p50"] = _observation(visits.get("waiting_for_gate_p50"), trials)
    result["challenge_available_visits_p50"] = _observation(visits.get("with_available_challenge_p50"), trials)
    result["challenge_unreachable_total"] = _observation(gates.get("gate_unreachable_finite_total"), trials)
    configured = {rule["quest_id"] for rule in report["config"].get("challenge_gates", {}).get("rules", [])}
    configured_rows = [row for row in gates.get("targets", [])
                       if row.get("quest_id") in configured and row.get("in_native_subset") is True]
    if (configured_rows and gates.get("trials") == trials
            and len({row["quest_id"] for row in configured_rows}) == len(configured_rows)
            and all(type(row.get("completed_trials")) is int and 0 <= row["completed_trials"] <= trials
                    for row in configured_rows)):
        completed = min(row["completed_trials"] for row in configured_rows)
        result["gated_challenge_min_completion_rate"] = _observation(completed / trials, trials, completed=completed)
    return result


def evaluate_comparison(control_report, candidate_report, targets):
    """Judge absolute candidate thresholds and retain honest paired denominators.

    Day percentiles describe completing journeys only. Pair a day target with
    a reached-rate target to require the desired share of children. Missing
    evidence in either report cannot pass, and never becomes the horizon day.
    """
    targets = normalize_targets(targets)
    _check_pair(control_report, candidate_report)
    control, candidate = _measure(control_report), _measure(candidate_report)
    checks = []
    for target in targets:
        key = target["metric"]
        before, after = control[key], candidate[key]
        missing = before["value"] is None or after["value"] is None
        delta = None if missing else after["value"] - before["value"]
        if missing:
            status, reason = "insufficient", "The metric is missing or was not reached in one or both reports."
        elif ((target["min"] is not None and after["value"] < target["min"])
              or (target["max"] is not None and after["value"] > target["max"])):
            status, reason = "fail", "The candidate falls outside the entered bounds."
        else:
            status, reason = "pass", "The candidate meets the entered bounds."
        checks.append({
            **target, "label": METRIC_BY_KEY[key]["label"], "unit": METRIC_BY_KEY[key]["unit"],
            "control": before, "candidate": after, "delta": delta, "status": status, "reason": reason,
        })
    statuses = {row["status"] for row in checks}
    status = "unconfigured" if not checks else "fail" if "fail" in statuses else "insufficient" if "insufficient" in statuses else "pass"
    return {"status": status, "checks": checks, "proposal": deepcopy(PROPOSAL)}
