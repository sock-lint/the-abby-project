"""Fixed promise-preserving design experiment; never a production reward writer.

Allocations constrain new grants. They do not constrain opening or claiming an
existing promise, and contingent salvage is not a second wallet credit.
"""
from collections import Counter, defaultdict
from copy import deepcopy

from apps.rpg.rarity import COSMETIC_TYPES
from .economy import _stats


COMMITMENT_DEFAULTS = {"enabled": False}
COMMITMENT_POLICY = {
    "daily_coins": 100, "expedition_daily_coins": 75, "activity_pouch_daily_coins": 25,
    "tiers": {"short": {"direct_coins": 10, "item_slots": 1},
              "standard": {"direct_coins": 25, "item_slots": 2},
              "long": {"direct_coins": 50, "item_slots": 3}},
}
COUNTERS = (
    "committed_coins", "expedition_direct_committed", "expedition_pouch_committed",
    "expedition_salvage_reserved", "activity_pouch_committed", "expedition_direct_paid",
    "expedition_salvage_paid", "pouch_coins_paid", "authored_pouch_coins_granted",
    "other_pouch_coins_granted", "released_salvage_reserve", "expedition_launches",
    "zero_coin_launches", "empty_expedition_launches", "empty_item_slots", "activity_empty_drops",
    "filtered_activity_pouch_candidates", "filtered_expedition_candidates",
)
GAUGES = ("outstanding_direct_coins", "outstanding_pouch_coins", "contingent_salvage_coins")
POUCH_SOURCES = ("activity_random", "expeditions", "authored", "other", "preexisting")
ASSUMPTIONS = [
    "This fixed opt-in design experiment changes only synthetic new reward commitments. No live reward rule, inventory or expedition is changed.",
    "One child's mounts share 75 Coins of new expedition commitments per calendar day; random activity pouches share a separate 25 Coins. Unused allocation does not bank.",
    "Direct expedition Coins are established first: short 10, standard 25, long 50, reduced before launch if less allocation remains. Later trips may promise zero Coins.",
    "Each item slot filters unaffordable entries before recalculating the existing rarity and companion weights. Pouches reserve their full face value; every cosmetic reserves its positive duplicate-salvage value even while unowned. Empty slots and changed acquisition paths are reported.",
    "Frozen expeditions, owned pouches and authored challenge pouches pay their full promises. Authored pouches and other Coin sources, including random activity cosmetic salvage, remain outside these allocations.",
    "Commitments, wallet credits and contingent salvage are separate quantities. Late claims or pouch opening can pay more than 100 Coins in one day. Unused contingent salvage is released at claim without restoring a past day's allocation.",
    "Consumables and boosts, including Lucky Coin timing, are unmodeled. This experiment cannot establish a live maximum claim or a rollout-ready reservation protocol.",
    "Unavailable finite targets are excluded acquisition paths, not extra playable runway. Reachability is source-level potential, not a promise of completion within the horizon.",
    "The installed finite comparator removes only the Coin commitment policy while retaining expedition launch/item quotas. The separate unlimited expedition comparator retains the Coin policy; their unavailable-target counts cannot be added.",
]


def normalize_commitment(supplied):
    if not isinstance(supplied, dict) or set(supplied) - set(COMMITMENT_DEFAULTS):
        raise ValueError("Unknown anonymous reward_commitment configuration fields.")
    result = {**COMMITMENT_DEFAULTS, **supplied}
    if type(result["enabled"]) is not bool:
        raise ValueError("reward_commitment.enabled must be a boolean.")
    return result


def pouch_value(item):
    return max(0, int((item.metadata or {}).get("coins") or item.coin_value or 0))


def item_liability(item, *, expedition=False):
    if item.item_type == "coin_pouch":
        return pouch_value(item)
    if expedition and item.item_type in COSMETIC_TYPES:
        return max(0, int(item.coin_value or 0))
    return 0


class RewardCommitment:
    def __init__(self, config):
        self.enabled = config["enabled"]
        self.day = None
        self.expedition_today = self.activity_pouch_today = 0
        self.totals = Counter()
        self.pouch_inventory = defaultdict(Counter)
        self.pouch_totals = {source: Counter() for source in POUCH_SOURCES}
        self.affected_paths = []
        self.installed_finite_total = self.unavailable_finite_total = 0
        self.removed_finite_targets = {}

    def begin_day(self, day):
        if day != self.day:
            self.day = day
            self.expedition_today = self.activity_pouch_today = 0

    def remaining(self, day, *, expedition=False):
        self.begin_day(day)
        return (COMMITMENT_POLICY["expedition_daily_coins"] - self.expedition_today if expedition
                else COMMITMENT_POLICY["activity_pouch_daily_coins"] - self.activity_pouch_today)

    def static_limit(self, tier=None):
        return (COMMITMENT_POLICY["expedition_daily_coins"] - COMMITMENT_POLICY["tiers"][tier]["direct_coins"]
                if tier else COMMITMENT_POLICY["activity_pouch_daily_coins"])

    def allows(self, item, *, tier=None, remaining=None):
        limit = self.static_limit(tier) if remaining is None else remaining
        return item_liability(item, expedition=tier is not None) <= limit

    def reserve_direct(self, day, tier):
        amount = min(COMMITMENT_POLICY["tiers"][tier]["direct_coins"], self.remaining(day, expedition=True))
        self.expedition_today += amount
        self.totals["expedition_direct_committed"] += amount
        self.totals["committed_coins"] += amount
        return amount

    def reserve_item(self, item, day, *, expedition=False):
        amount = item_liability(item, expedition=expedition)
        if amount > self.remaining(day, expedition=expedition):
            raise ValueError("Synthetic reward exceeds its new commitment allocation.")
        if expedition:
            self.expedition_today += amount
            key = "expedition_pouch_committed" if item.item_type == "coin_pouch" else "expedition_salvage_reserved"
        else:
            self.activity_pouch_today += amount
            key = "activity_pouch_committed"
        self.totals[key] += amount
        self.totals["committed_coins"] += amount

    def grant_pouch(self, item, quantity, source):
        if not self.enabled or item.item_type != "coin_pouch":
            return
        origin = {"drops": "activity_random", "expeditions": "expeditions", "challenges": "authored"}.get(source, "other")
        amount = pouch_value(item) * quantity
        self.pouch_inventory[item.pk][origin] += quantity
        self.pouch_totals[origin]["granted_coins"] += amount
        if origin in {"authored", "other"}:
            self.totals[f"{origin}_pouch_coins_granted"] += amount

    def open_pouches(self, item, quantity):
        remaining = quantity
        value = pouch_value(item)
        for source in POUCH_SOURCES:
            count = min(remaining, self.pouch_inventory[item.pk][source])
            self.pouch_inventory[item.pk][source] -= count
            self.pouch_totals[source]["opened_coins"] += count * value
            remaining -= count
        self.pouch_totals["preexisting"]["opened_coins"] += remaining * value

    def paid(self, amount, source):
        if self.enabled and source in {"expeditions", "expeditions_salvage", "coin_pouches"}:
            key = {"expeditions": "expedition_direct_paid", "expeditions_salvage": "expedition_salvage_paid",
                   "coin_pouches": "pouch_coins_paid"}[source]
            self.totals[key] += amount

    def gauges(self, trial):
        pending = trial.pending_expeditions
        pending_pouches = sum(pouch_value(trial.catalog.items[pk]) for expedition in pending
                              for pk in expedition["items"] if trial.catalog.items[pk].item_type == "coin_pouch")
        held_pouches = sum(pouch_value(trial.catalog.items[pk]) * quantity for pk, quantity in trial.inventory.items()
                           if quantity > 0 and trial.catalog.items[pk].item_type == "coin_pouch")
        return {"outstanding_direct_coins": sum(row["coins"] for row in pending),
                "outstanding_pouch_coins": pending_pouches + held_pouches,
                "contingent_salvage_coins": sum(row.get("salvage_reserve", 0) for row in pending)}

    def report(self, trial):
        if not self.enabled:
            return {"enabled": False}
        gauges = self.gauges(trial)
        sources = []
        for source in POUCH_SOURCES:
            outstanding = sum(pouch_value(trial.catalog.items[pk]) * counts[source]
                              for pk, counts in self.pouch_inventory.items())
            if source == "preexisting":
                outstanding += sum(pouch_value(trial.catalog.items[pk]) * max(0, quantity - sum(self.pouch_inventory[pk].values()))
                                   for pk, quantity in trial.inventory.items()
                                   if trial.catalog.items[pk].item_type == "coin_pouch")
            pending = (sum(pouch_value(trial.catalog.items[pk]) for row in trial.pending_expeditions
                           for pk in row["items"] if trial.catalog.items[pk].item_type == "coin_pouch")
                       if source == "expeditions" else 0)
            sources.append({"source": source, "granted_coins": self.pouch_totals[source]["granted_coins"],
                            "opened_coins": self.pouch_totals[source]["opened_coins"],
                            "pending_coins": pending, "outstanding_coins": outstanding + pending})
        return {"enabled": True, "policy": deepcopy(COMMITMENT_POLICY),
                "summary": {**{key: self.totals[key] for key in COUNTERS}, **gauges},
                "pouch_sources": sources, "affected_paths": self.affected_paths,
                "installed_finite_total": self.installed_finite_total,
                "unavailable_finite_total": self.unavailable_finite_total,
                "removed_finite_targets": self.removed_finite_targets, "assumptions": list(ASSUMPTIONS)}


def aggregate_commitment(runs, config):
    if not config["enabled"]:
        return {"enabled": False}
    reports = [row["reward_commitment"] for row in runs]
    first = reports[0]
    return {"enabled": True, "policy": deepcopy(COMMITMENT_POLICY),
            "summary": {key: _stats([row["summary"][key] for row in reports]) for key in (*COUNTERS, *GAUGES)},
            "pouch_sources": [{"source": source, **{key: _stats([row["pouch_sources"][index][key] for row in reports])
                              for key in ("granted_coins", "opened_coins", "pending_coins", "outstanding_coins")}}
                              for index, source in enumerate(POUCH_SOURCES)],
            **{key: first[key] for key in ("affected_paths", "installed_finite_total", "unavailable_finite_total", "removed_finite_targets")},
            "assumptions": list(ASSUMPTIONS)}
