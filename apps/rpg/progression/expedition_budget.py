"""Anonymous expedition quotas constrain new launches and item promises only."""
from collections import Counter
from copy import deepcopy

from .economy import _stats


EXPEDITION_BUDGET_DEFAULTS = {"daily_launches": None, "daily_items": None}
EXPEDITION_BUDGET_LIMITS = {
    "daily_launches": {"min": 0, "max": 15, "nullable": True},
    "daily_items": {"min": 0, "max": 45, "nullable": True},
}
COUNTERS = (
    "requested_trips", "eligible_trips", "launched_trips", "prevented_trips", "unavailable_mount_trips",
    "slots_requested", "slots_promised", "slots_withheld_by_budget", "slots_unfilled_by_pool",
    "claimed_items", "grandfathered_claimed_items", "zero_item_trips", "zero_coin_trips", "empty_trips",
    "launch_limited_days", "item_limited_days", "launch_saturated_days", "item_saturated_days",
)
GAUGES = ("pending_items", "grandfathered_pending_items")
ASSUMPTIONS = [
    "This anonymous experiment changes only new synthetic expedition launches and item promises. No live expedition, reward rule or inventory is changed.",
    "One child's mounts share the daily launch and item allocations. Null means unlimited, zero prevents the selected new commitments, and unused capacity never banks across calendar days.",
    "Requested trips are the configured count after the installed control's shared daily launch allowance. Eligible trips are the smaller of that request and currently available species. Prevented trips are eligible trips withheld by this optional launch quota, not by the installed allowance; unavailable species are reported separately. The standalone commitment prototype retains its explicit launch assumptions.",
    "Nominal item slots are counted only for launched trips. Before drawing loot, the remaining item quota bounds whole slots; each successfully selected item consumes one unit, including pouches and cosmetics later salvaged. Empty eligible pools do not consume item capacity.",
    "Slots requested equal slots promised plus nominal slots withheld by the quota plus permitted slots left unfilled by the eligible pool or Coin commitment policy. Withheld nominal slots are not a counterfactual count of items that would have dropped.",
    "Item-only quotas still allow later Coin-only trips. The Coin commitment policy may also promise zero direct Coins; zero-item, zero-Coin and fully empty trips remain visible rather than being silently skipped.",
    "A saturated day exactly uses an allocation on a relevant eligible opportunity; a limited day actually withholds a trip or nominal slot. Zero allocations do not count idle or no-mount days as saturated. Each day counts at most once per measure.",
    "Frozen loot claims retain their complete item and Coin promises. Claimed and pending items count promised units, including later salvage, not retained inventory. Grandfathered units lack a new-budget reservation marker and are reported separately.",
    "For new-budget promises, slots promised equal claimed items minus grandfathered claimed items plus pending items minus grandfathered pending items. Claims do not consume a later day's allocation.",
    "The unlimited finite denominator removes both optional expedition quotas while retaining the installed allowance, Coin policy and routine. Unavailable targets are excluded acquisition paths, not extra playable runway; this loss cannot be added to the separate Coin-policy comparator.",
    "Authored challenge items, activity drops, boosts and future launch/claim concurrency are outside these expedition slot quotas. This is a design comparison, not a live reservation protocol or retention prediction.",
]


def normalize_expedition_budget(supplied):
    if not isinstance(supplied, dict) or set(supplied) - set(EXPEDITION_BUDGET_DEFAULTS):
        raise ValueError("Unknown anonymous expedition_budget configuration fields.")
    result = {**EXPEDITION_BUDGET_DEFAULTS, **supplied}
    for key, value in result.items():
        bounds = EXPEDITION_BUDGET_LIMITS[key]
        if value is not None and (type(value) is not int or not bounds["min"] <= value <= bounds["max"]):
            raise ValueError(f"expedition_budget.{key} must be null or a whole number from {bounds['min']} to {bounds['max']}.")
    return result


class ExpeditionBudget:
    def __init__(self, config):
        self.config = dict(config)
        self.day = None
        self.launches_today = self.items_today = 0
        self.totals = Counter()
        self.counted_days = {key: set() for key in ("launch_limited_days", "item_limited_days",
                                                   "launch_saturated_days", "item_saturated_days")}
        self.unlimited_finite_total = self.unavailable_finite_total = 0
        self.removed_finite_targets = {}

    def begin_day(self, day):
        if day != self.day:
            self.day = day
            self.launches_today = self.items_today = 0

    def _day(self, key, day):
        if day not in self.counted_days[key]:
            self.counted_days[key].add(day)
            self.totals[key] += 1

    def prepare_launches(self, day, requested, available):
        self.begin_day(day)
        eligible = min(requested, available)
        cap = self.config["daily_launches"]
        launched = eligible if cap is None else min(eligible, max(0, cap - self.launches_today))
        prevented = eligible - launched
        for key, value in (("requested_trips", requested), ("eligible_trips", eligible),
                           ("unavailable_mount_trips", requested - eligible), ("prevented_trips", prevented),
                           ("launched_trips", launched)):
            self.totals[key] += value
        self.launches_today += launched
        if prevented:
            self._day("launch_limited_days", day)
        if cap is not None and eligible > 0 and self.launches_today == cap:
            self._day("launch_saturated_days", day)
        return launched

    def prepare_slots(self, day, nominal):
        self.begin_day(day)
        cap = self.config["daily_items"]
        permitted = nominal if cap is None else min(nominal, max(0, cap - self.items_today))
        self.totals["slots_requested"] += nominal
        self.totals["slots_withheld_by_budget"] += nominal - permitted
        if permitted < nominal:
            self._day("item_limited_days", day)
        if cap is not None and nominal > 0 and self.items_today == cap:
            self._day("item_saturated_days", day)
        return permitted

    def promise_items(self, day, permitted, promised):
        self.begin_day(day)
        self.items_today += promised
        self.totals["slots_promised"] += promised
        self.totals["slots_unfilled_by_pool"] += permitted - promised
        cap = self.config["daily_items"]
        if cap is not None and promised > 0 and self.items_today == cap:
            self._day("item_saturated_days", day)

    def trip(self, coins, item_count):
        self.totals["zero_item_trips"] += int(item_count == 0)
        self.totals["zero_coin_trips"] += int(coins == 0)
        self.totals["empty_trips"] += int(coins == 0 and item_count == 0)

    def claim(self, expedition):
        count = len(expedition["items"])
        self.totals["claimed_items"] += count
        if "budget_promised_items" not in expedition:
            self.totals["grandfathered_claimed_items"] += count

    @staticmethod
    def gauges(trial):
        return {"pending_items": sum(len(row["items"]) for row in trial.pending_expeditions),
                "grandfathered_pending_items": sum(len(row["items"]) for row in trial.pending_expeditions
                                                   if "budget_promised_items" not in row)}

    def trace(self, trial):
        return {"expedition_budget_launches_today": self.launches_today,
                "expedition_budget_items_today": self.items_today,
                **{f"expedition_budget_{key}": self.totals[key] for key in COUNTERS},
                **{f"expedition_budget_{key}": value for key, value in self.gauges(trial).items()}}

    def report(self, trial):
        return {**self.config, "summary": {**{key: self.totals[key] for key in COUNTERS}, **self.gauges(trial)},
                "unlimited_finite_total": self.unlimited_finite_total,
                "unavailable_finite_total": self.unavailable_finite_total,
                "removed_finite_targets": self.removed_finite_targets, "assumptions": list(ASSUMPTIONS)}


def aggregate_expedition_budget(runs, config):
    reports = [row["expedition_budget"] for row in runs]
    return {**deepcopy(config),
            "summary": {key: _stats([row["summary"][key] for row in reports]) for key in (*COUNTERS, *GAUGES)},
            **{key: reports[0][key] for key in ("unlimited_finite_total", "unavailable_finite_total", "removed_finite_targets")},
            "assumptions": list(ASSUMPTIONS)}
