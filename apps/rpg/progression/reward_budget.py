"""Hypothetical per-child automatic Coin income, never a live claim policy.

The engine consumes the same synthetic pouches and rolls the same item rewards.
Excess Coins are omitted, not held as a payable balance or deferred to tomorrow.
Applying such a cap to promised live rewards would require a different design.
"""
from collections import Counter

from .economy import _stats


REWARD_BUDGET_DEFAULTS = {"daily_coins": None}
REWARD_BUDGET_LIMITS = {"daily_coins": {"min": 0, "max": 100_000, "nullable": True}}
REWARD_BUDGET_SOURCES = ("expeditions", "expeditions_salvage", "coin_pouches")
COIN_METRICS = ("raw_coins", "awarded_coins", "omitted_coins")
SUMMARY_METRICS = (*COIN_METRICS, "capped_days")
ASSUMPTIONS = [
    "This is a hypothetical reduction in new-child Coin income, not a live reward rule. Each trial is an alternative history of one child.",
    "One shared envelope covers direct expedition Coins, expedition cosmetic salvage and all opened Coin pouches, regardless of pouch origin. Other Coin sources, XP and item rolls retain their installed rules.",
    "The envelope resets each simulation calendar day. Unused allowance is not banked; inactive days do not increase the next visit's budget. Null means uncapped and zero omits all included Coins.",
    "Included awards use first-arrival order: expedition claims precede activity and end-of-visit pouch opening. All mounts share the same child's allowance; earlier rewards can leave no allowance for later pouches.",
    "Excess included Coins are omitted, never deferred or owed. Synthetic pouches are still consumed and expedition items retained. This must not be applied retroactively to owned pouches or already committed live expedition loot.",
    "Raw Coins are the included awards encountered within each policy's simulated journey, not a paired uncapped counterfactual. Coin-related progression changes can alter later eligibility and rewards.",
    "Summary and source percentiles are calculated independently across alternative trials; use means or individual trial values to reconcile source totals.",
]


def normalize_reward_budget(supplied):
    if not isinstance(supplied, dict) or set(supplied) - set(REWARD_BUDGET_DEFAULTS):
        raise ValueError("Unknown anonymous reward_budget configuration fields.")
    result = {**REWARD_BUDGET_DEFAULTS, **supplied}
    cap = result["daily_coins"]
    limits = REWARD_BUDGET_LIMITS["daily_coins"]
    if cap is not None and (type(cap) is not int or not limits["min"] <= cap <= limits["max"]):
        raise ValueError("Invalid reward_budget.daily_coins; use null or a whole Coin amount from 0 through 100000.")
    return result


class RewardBudget:
    def __init__(self, config):
        self.daily_coins = config["daily_coins"]
        self.day = None
        self.used_today = 0
        self.capped_today = False
        self.totals = Counter()
        self.sources = {source: Counter() for source in REWARD_BUDGET_SOURCES}

    def begin_day(self, day):
        if day != self.day:
            self.day = day
            self.used_today = 0
            self.capped_today = False

    def award(self, amount, source, day):
        if amount <= 0 or source not in self.sources:
            return amount
        self.begin_day(day)
        awarded = amount if self.daily_coins is None else min(amount, max(0, self.daily_coins - self.used_today))
        self.used_today += awarded
        omitted = amount - awarded
        for key, value in zip(COIN_METRICS, (amount, awarded, omitted)):
            self.totals[key] += value
            self.sources[source][key] += value
        if omitted > 0 and not self.capped_today:
            self.totals["capped_days"] += 1
            self.capped_today = True
        return awarded

    def report(self):
        return {
            "daily_coins": self.daily_coins,
            "summary": {key: self.totals[key] for key in SUMMARY_METRICS},
            "sources": [{"source": source, **{key: totals[key] for key in COIN_METRICS}}
                        for source, totals in self.sources.items()],
            "assumptions": list(ASSUMPTIONS),
        }


def aggregate_reward_budget(runs, config):
    reports = [run["reward_budget"] for run in runs]
    return {
        "daily_coins": config["daily_coins"],
        "summary": {key: _stats([report["summary"][key] for report in reports]) for key in SUMMARY_METRICS},
        "sources": [
            {"source": source, **{key: _stats([report["sources"][index][key] for report in reports])
                                  for key in COIN_METRICS}}
            for index, source in enumerate(REWARD_BUDGET_SOURCES)
        ],
        "assumptions": list(ASSUMPTIONS),
    }
