"""A bounded, in-memory new-child projection, using the installed domain rules.

This is deliberately not a transaction/rollback sandbox. No household models or
award writers are called. Missing activity types remain visible exclusions.
"""

from collections import Counter, defaultdict
from copy import copy, deepcopy
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import inspect
import json
import math
import random
from types import SimpleNamespace
from types import MappingProxyType

from django.conf import settings
from apps.quests import activity as challenge_activity_rules
from apps.quests import milestone_eligibility as milestone_rules

from apps.achievements.models import XP_THRESHOLDS
from apps.achievements import criteria as badge_criteria
from apps.achievements.criteria import criteria_types_for_scopes
from apps.achievements.services import BadgeService, SkillService
from apps.chronicle.services import JOURNAL_SKILL_WEIGHTS, JOURNAL_XP_POOL
from apps.creations.services import CreationService
from apps.habits.services import HabitService
from apps.movement.services import MovementSessionService
from apps.pets.expeditions import ExpeditionService, TIER_CONFIG
from apps.pets.lifecycle import growth_thresholds
from apps.pets.services import PetService
from apps.quests.goals import EFFORT_TRIGGERS, FACT_TRIGGERS, _amount
from apps.quests.services import QuestService, TRIGGER_DAMAGE
from apps.quests import goals
from apps.quests.models import DailyBonus
from apps.quests.daily_bonus import process_daily_bonus
from apps.timecards.services import ClockService, TimecardService
from apps.printing.pricing import quote_print_coins
from apps.reading.services import ReadingRewardService
from apps.rewards.services import ExchangeService
from apps.rpg.companion_catalog import companion_drop_weights
from apps.rpg.catalog_support import random_item_is_available, available_random_items
from apps.rpg.item_effects import FOOD_GROWTH_BY_RARITY, MAX_AUTHORED_FOOD_GROWTH, PREFERRED_FOOD_BONUS, food_base_growth
from apps.rpg.rarity import (
    ACCOMPLISHMENT_TIER_WEIGHTS, ACCOMPLISHMENT_TRIGGERS, BASE_TIER_WEIGHTS,
    drop_tier_weights, tier_balanced_weights,
)
from apps.rpg.tasks import _award_perfect_day
from apps.rpg.services import (
    BASE_CHECK_IN_COINS,
    BASE_DROP_RATES,
    STREAK_DROP_BONUS_CAP,
    STREAK_DROP_BONUS_PER_DAY,
    STREAK_MULTIPLIER_CAP,
    STREAK_MULTIPLIER_PER_DAY,
    DropService,
    ConsumableService,
    StreakService,
)
from apps.rpg import inventory as inventory_rules
from apps.wellbeing.services import GRATITUDE_FIRST_OF_DAY_COINS

from .catalog import load_catalog
from .capacity import ItemCapacity
from .economy import (
    ECONOMY_DEFAULTS, ECONOMY_LIMITS, OFFER_DEFAULTS, Economy,
    aggregate_economy, normalize_economy, project_money_cents, exchange_quote_cents,
)
from .reward_budget import (
    REWARD_BUDGET_DEFAULTS, REWARD_BUDGET_LIMITS, REWARD_BUDGET_SOURCES,
    SUMMARY_METRICS as REWARD_BUDGET_METRICS,
    RewardBudget, aggregate_reward_budget, normalize_reward_budget,
)
from .commitment import (
    COMMITMENT_DEFAULTS, COMMITMENT_POLICY, ASSUMPTIONS as COMMITMENT_ASSUMPTIONS,
    RewardCommitment, aggregate_commitment, item_liability, normalize_commitment,
)
from .expedition_budget import (
    EXPEDITION_BUDGET_DEFAULTS, EXPEDITION_BUDGET_LIMITS, ASSUMPTIONS as EXPEDITION_BUDGET_ASSUMPTIONS,
    ExpeditionBudget, aggregate_expedition_budget, normalize_expedition_budget,
)

from .challenge_gates import (
    CHALLENGE_GATES_DEFAULTS, CHALLENGE_GATES_LIMITS, ASSUMPTIONS as CHALLENGE_GATES_ASSUMPTIONS,
    ChallengeGates, aggregate_challenge_gates, challenge_gate_choices, normalize_challenge_gates,
    validate_challenge_gate_catalog,
)


SCHEMA_VERSION = 1
ENGINE_VERSION = "2026-10-20.5"
SECONDS_PER_DAY = 86400
MAX_WORK_UNITS = 10000
DEFAULTS = {
    "horizon_days": 90,
    "trials": 20,
    "seed": 42,
    "active_days_per_week": 5,
    "reading_minutes": 10,
    "project_minutes": 0,
    "chores_per_day": 2,
    "chore_coins": 10,
    "chore_xp": 10,
    "habits_per_day": 1,
    "habit_xp": 5,
    "movement_sessions_per_day": 0,
    "movement_minutes": 20,
    "movement_intensity": "medium",
    "creations_per_day": 0,
    "journal_per_day": True,
    "feed_strategy": "feed_all",
    "expeditions_per_day": 1,
    "expedition_tier": "long",
    "economy": deepcopy(ECONOMY_DEFAULTS),
    "reward_budget": dict(REWARD_BUDGET_DEFAULTS),
    "reward_commitment": dict(COMMITMENT_DEFAULTS),
    "expedition_budget": dict(EXPEDITION_BUDGET_DEFAULTS),
    "challenge_gates": deepcopy(CHALLENGE_GATES_DEFAULTS),
}
LIMITS = {
    "horizon_days": {"choices": [30, 90, 180, 365]},
    "trials": {"min": 1, "max": 40},
    "seed": {"min": 0, "max": 2147483647},
    "active_days_per_week": {"min": 1, "max": 7},
    "reading_minutes": {"min": 0, "max": 240},
    "project_minutes": {"min": 0, "max": 240},
    "chores_per_day": {"min": 0, "max": 10},
    "chore_coins": {"min": 0, "max": 200},
    "chore_xp": {"min": 0, "max": 100},
    "habits_per_day": {"min": 0, "max": 10},
    "habit_xp": {"min": 0, "max": 100},
    "movement_sessions_per_day": {"min": 0, "max": 6},
    "movement_minutes": {"min": 1, "max": 240},
    "movement_intensity": {"choices": ["low", "medium", "high"]},
    "creations_per_day": {"min": 0, "max": 4},
    "journal_per_day": {"type": "boolean"},
    "feed_strategy": {"choices": ["feed_all", "none"]},
    "expeditions_per_day": {"min": 0, "max": 15},
    "expedition_tier": {"choices": ["short", "standard", "long"]},
    "economy": {"type": "object"},
    "reward_budget": {"type": "object"},
    "reward_commitment": {"type": "object"},
    "expedition_budget": {"type": "object"},
    "challenge_gates": {"type": "object"},
}
MILESTONES = {
    "first_reward": "First XP or Coins",
    "character_level_1": "Character level 1",
    "character_level_3": "Character level 3",
    "character_level_6": "Character level 6",
    "first_pet": "First hatched companion",
    "first_middle": "First middle-stage companion",
    "first_mount": "First grown companion",
    "first_challenge": "First completed challenge",
    "finite_25": "25% of modeled finite content",
    "finite_50": "50% of modeled finite content",
    "finite_80": "80% of modeled finite content",
    "finite_100": "All modeled finite content",
}
COSMETIC_TYPES = {"cosmetic_frame", "cosmetic_title", "cosmetic_theme", "cosmetic_pet_accessory"}
DAILY_BONUS_COINS = DailyBonus._meta.get_field("coin_reward").default
DAILY_BONUS_XP = DailyBonus._meta.get_field("xp_reward").default
ACTIVITY_SKILLS = {
    "chores": [("Life Skills", "Persistence", 1)],
    "habits": [("Physical", "Mindfulness", 1)],
    "project": [("Life Skills", "Persistence", 1)],
    "movement": [("Physical", "Endurance", 1)],
    "creations": [("Art & Crafts", "Drawing", 1)],
    "reading": [("Language Arts", ReadingRewardService.SKILL_NAME, 1)],
    "journal": [("Language Arts", name, weight) for name, weight in JOURNAL_SKILL_WEIGHTS],
}


def estimate_work(config):
    """Conservative visit/source budget, checked before any catalog read."""
    weeks, remainder = divmod(config["horizon_days"], 7)
    visits = weeks * config["active_days_per_week"] + min(remainder, config["active_days_per_week"])
    sources = (
        int(config["reading_minutes"] >= ReadingRewardService.TARGET_MINUTES)
        + int(config["project_minutes"] > 0)
        + config["chores_per_day"]
        + config["habits_per_day"]
        + config["movement_sessions_per_day"]
        + config["creations_per_day"]
        + int(config["journal_per_day"])
        + config["expeditions_per_day"]
        + (len(config.get("economy", {}).get("offers", [])) + 1 if config.get("economy", {}).get("enabled") else 0)
    )
    return config["trials"] * (config["horizon_days"] + visits * sources)


def normalize_config(config=None):
    supplied = {} if config is None else config
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULTS):
        raise ValueError("Unknown Progression Lab configuration fields.")
    result = {**DEFAULTS, **supplied}
    result["economy"] = normalize_economy(supplied.get("economy"))
    result["reward_budget"] = normalize_reward_budget(supplied.get("reward_budget", {}))
    result["reward_commitment"] = normalize_commitment(supplied.get("reward_commitment", {}))
    result["expedition_budget"] = normalize_expedition_budget(supplied.get("expedition_budget", {}))
    result["challenge_gates"] = normalize_challenge_gates(supplied.get("challenge_gates", {}))
    if result["reward_commitment"]["enabled"] and result["reward_budget"]["daily_coins"] is not None:
        raise ValueError("Commitment promises cannot be combined with the hypothetical Coin income envelope.")
    for key, value in result.items():
        if key in {"economy", "reward_budget", "reward_commitment", "expedition_budget", "challenge_gates"}:
            continue
        limit = LIMITS[key]
        if limit.get("type") == "boolean":
            valid = type(value) is bool
        elif "choices" in limit:
            valid = value in limit["choices"] and type(value) is type(DEFAULTS[key])
        else:
            valid = type(value) is int and limit["min"] <= value <= limit["max"]
        if not valid:
            raise ValueError(f"Invalid Progression Lab value for {key}.")
    work = estimate_work(result)
    if work > MAX_WORK_UNITS:
        raise ValueError(
            f"Scenario needs {work:,} work units; the limit is {MAX_WORK_UNITS:,}. Reduce trials, horizon, activities, expedition launches or offers."
        )
    return result


def pet_incubation_policy():
    """Capture installed care rules once, without mutable runtime settings."""
    return MappingProxyType({
        "duration_seconds": PetService.incubation_duration_seconds(),
        "max_active": 1,
        "clock": "elapsed_seconds",
        "start_strategy": "first_compatible_pair_during_care",
        "claim_strategy": "next_active_care_visit_at_or_after_ready",
    })


def _capture_incubation_policy(policy):
    if policy is None:
        return pet_incubation_policy()
    return policy if isinstance(policy, MappingProxyType) else MappingProxyType(dict(policy))


def rules_fingerprint(*, incubation_policy=None):
    # Source digests include the pure helpers so a formula change invalidates
    # saved forecasts even when its constants stay the same.
    rules = {
        "engine": ENGINE_VERSION,
        "milestone_goal_source": inspect.getsource(inspect.getmodule(_amount)),
        "milestone_source": inspect.getsource(milestone_rules),
        "milestone_activity_source": inspect.getsource(challenge_activity_rules),
        "badge_criteria_source": inspect.getsource(badge_criteria),
        "badge_criteria_scopes": {str(key): sorted(value) for key, value in badge_criteria._CRITERIA_SCOPES.items()},
        "badge_criteria_registry": {str(key): f"{fn.__module__}.{fn.__qualname__}"
                                    for key, fn in badge_criteria._CRITERIA_CHECKERS.items()},
        "badge_service_source": inspect.getsource(inspect.getmodule(BadgeService)),
        "inventory_grant_source": inspect.getsource(inventory_rules),
        "inventory_badge_hook": inspect.getsource(BadgeService.evaluate_inventory_badges),
        "pet_incubation_policy": dict(_capture_incubation_policy(incubation_policy)),
        "seconds_per_day": SECONDS_PER_DAY,
        "xp": XP_THRESHOLDS,
        "drops": BASE_DROP_RATES,
        "max_work_units": MAX_WORK_UNITS,
        "check_in": [BASE_CHECK_IN_COINS, STREAK_MULTIPLIER_PER_DAY, STREAK_MULTIPLIER_CAP],
        "streak_drops": [STREAK_DROP_BONUS_PER_DAY, STREAK_DROP_BONUS_CAP],
        "growth": [FOOD_GROWTH_BY_RARITY, PREFERRED_FOOD_BONUS, MAX_AUTHORED_FOOD_GROWTH],
        "rarity": [BASE_TIER_WEIGHTS, ACCOMPLISHMENT_TIER_WEIGHTS, sorted(ACCOMPLISHMENT_TRIGGERS)],
        "accomplishment_loot": {
            "badge_earned": "one draw per newly saved badge",
            "quest_complete": "one draw per first payout of each occurrence or participant",
            "perfect_day": "one draw per new daily receipt; omitted from the activity model",
            "perfect_day_tier_weights": drop_tier_weights("perfect_day"),
        },
        "tiers": TIER_CONFIG,
        "damage": TRIGGER_DAMAGE,
        "coins_per_hour": settings.COINS_PER_HOUR,
        "coins_per_dollar": settings.COINS_PER_DOLLAR,
        "economy_defaults": ECONOMY_DEFAULTS,
        "economy_limits": ECONOMY_LIMITS,
        "economy_source": inspect.getsource(inspect.getmodule(Economy)),
        "reward_budget_defaults": REWARD_BUDGET_DEFAULTS,
        "reward_budget_limits": REWARD_BUDGET_LIMITS,
        "reward_budget_source": inspect.getsource(inspect.getmodule(RewardBudget)),
        "reward_commitment_source": inspect.getsource(inspect.getmodule(RewardCommitment)),
        "expedition_budget_source": inspect.getsource(inspect.getmodule(ExpeditionBudget)),
        "challenge_gates_source": inspect.getsource(inspect.getmodule(ChallengeGates)),
        "item_capacity_source": inspect.getsource(inspect.getmodule(ItemCapacity)),
        "challenge_gates_assumptions": list(inspect.getmodule(ChallengeGates).ASSUMPTIONS),
        "badge_coins": settings.COINS_PER_BADGE_RARITY,
        "reading": [ReadingRewardService.TARGET_MINUTES, ReadingRewardService.BASE_XP, ReadingRewardService.BASE_COINS],
        "journal": [JOURNAL_XP_POOL, JOURNAL_SKILL_WEIGHTS, GRATITUDE_FIRST_OF_DAY_COINS],
        "creations": [CreationService.BASELINE_XP, CreationService.DAILY_XP_LIMIT],
        "movement": [
            MovementSessionService.DAILY_REWARD_LIMIT,
            MovementSessionService.XP_PER_10_MIN,
            MovementSessionService.INTENSITY_MULTIPLIER,
        ],
        "activity_skills": ACTIVITY_SKILLS,
        "daily_bonus": [DAILY_BONUS_COINS, DAILY_BONUS_XP],
        "helpers": [
            inspect.getsource(fn)
            for fn in (
                SkillService._iter_tagged_xp,
                SkillService.level_for_xp,
                MovementSessionService.compute_xp_pool,
                _amount,
                companion_drop_weights,
                random_item_is_available,
                available_random_items,
                tier_balanced_weights,
                drop_tier_weights,
                DropService.award_accomplishment,
                DropService.process_drops,
                ConsumableService.use,
                StreakService.record_activity,
                HabitService.log_tap,
                goals._award,
                QuestService._award_quest_rewards,
                _award_perfect_day,
                food_base_growth,
                growth_thresholds,
                process_daily_bonus,
                ClockService.clock_out,
                PetService.feed_pet,
                PetService.start_incubation,
                PetService.hatch_incubation,
                PetService.incubation_duration_seconds,
                PetService._save_growth,
                PetService._evaluate_pet_badges,
                ExpeditionService._roll_loot,
                ExpeditionService._materialize_loot,
                BadgeService._award_badge_xp,
                BadgeService._award_badge_coins,
                BadgeService.evaluate_badges,
                ReadingRewardService.credit_new_session,
                TimecardService.generate_weekly_timecard,
                quote_print_coins,
                normalize_economy,
                project_money_cents,
                exchange_quote_cents,
                ExchangeService.request_exchange,
                ExchangeService.approve,
            )
        ],
        "engine_source": inspect.getsource(Trial),
    }
    return hashlib.sha256(json.dumps(rules, sort_keys=True, default=str).encode()).hexdigest()


def coverage(catalog):
    return {
        "modeled": [
            "New child with zero XP, Coins and owned companions/inventory",
            "Reading, approved synthetic chores, positive synthetic habits, project time, journal, creations and movement",
            "Supported drops use current rarity tier budgets, authored within-tier weights and unowned cosmetic priority",
            "Parallel automatic catalog challenges, guaranteed companion trails and eligible badge criteria",
            "One guaranteed loot draw per newly earned badge and completed automatic challenge occurrence, including repeat windows",
            "Inventory grants immediately evaluate modeled collection badges; zero-XP positive habits still evaluate habit achievements",
            "One elapsed-time egg incubation, explicit active-visit hatching, rarity/authored food growth, evolution and bounded mount expeditions with same-trip cosmetic duplicate avoidance",
            "Opt-in anonymous real-world reward and print purchases, calendar cost/resource budgets, assumed wages and parent-approved money-to-Coins top-ups",
            "Hypothetical shared per-child daily Coin income envelopes for expeditions, expedition salvage and opened Coin pouches",
            "Opt-in fixed 100-Coin new commitment experiment: 75 expedition and 25 random activity-pouch Coins, preserving full established rewards",
            "Shared optional per-child expedition launch and whole-item promise quotas, independent of the Coin policy",
        ],
        "excluded": [
            "Homework, completed projects/milestones, savings, actual cash payments/bonuses, birthdays and grade progression",
            "Private family chores, habits, reward offers/budgets and redemptions; digital shop fulfillment, parent goals and co-op/legacy quests",
            "Consumable use and XP/Coin/drop/growth boosts; consumable drops remain held inventory",
            "Perfect Day (live completion loot is Uncommon-or-better), manual grants, time-of-day and approval-delay effects",
            "Unmodeled badge criteria and cosmetic equipping; cosmetic-only starter cover gift",
            "Production deployment/asset delivery verification and player retention/engagement predictions",
        ],
        "assumptions": [
            "Day 1 starts an abstract week; visits occur on the first N days of each seven-day block",
            "All configured chores are approved that visit; each habit is a distinct positive habit with one tap/day",
            "Source skills are fixed synthetic tags, reported in activity_skills; absent/locked skills earn no XP",
            "Visits occur at fixed 86400-second intervals; within-visit actions take no modeled time",
            "Care reserves one compatible pair, freezes its installed incubation duration and claims it at the next active visit at or after its deadline, before other activity rewards",
            "End-of-visit care starts the first compatible unowned pair when no egg is pending, opens Coin pouches and feeds all available food to the oldest unevolved pet",
            "Expeditions launch at the end of a visit and are claimed on the next active visit after return",
            "New source events advance every matching challenge; challenge duration is a deadline, not a minimum wait",
            "Badge and challenge celebration loot does not count as activity, streak credit, daily effort or additional challenge progress",
            "Finite completion draws and authored item quantities fund distinct ingredients and food units; conservative per-target capacity proofs do not promise joint collection of all finite targets",
            "Percentile days are calendar days conditional on completion; unreached trials remain in completion_rate",
            "Finite content counts modeled badges, one-off challenges, obtainable cosmetic identities and companion stages only; it is not total app runway",
            "Remaining finite targets means uncompleted, including missed one-off deadlines; expired unfinished challenges are reported separately and are not future playable content",
        ],
        "activity_skills": ACTIVITY_SKILLS,
        "excluded_badge_criteria": dict(catalog.excluded_badges),
        "initial_state": {"coins": 0, "xp": 0, "pets": 0, "mounts": 0, "inventory": 0},
    }


def audit_catalog(catalog):
    messages = [
        {
            "severity": "info",
            "code": "partial_model",
            "message": "This forecasts the stated activity/care policy, not full app exhaustion or measured retention.",
        },
        {
            "severity": "warning",
            "code": "no_coin_spending",
            "message": "No private reward offers are read. Coins accumulate; shop affordability and economic balance require a separate spending assumption.",
        },
    ]
    if not catalog.pairs:
        messages.append(
            {
                "severity": "warning",
                "code": "no_supported_companions",
                "message": "The loaded global catalog has no supported hatchable companion pairs.",
            }
        )
    if not catalog.items or not catalog.skills:
        messages.append(
            {
                "severity": "warning",
                "code": "catalog_not_loaded",
                "message": "Global content is missing. Load the intended catalog before interpreting this forecast.",
            }
        )
    guaranteed = False
    for quest in catalog.quests:
        rewards = [catalog.items[row.item_id] for row in quest.reward_items.all() if row.item_id in catalog.items]
        eggs = {item.pet_species_id for item in rewards if item.item_type == "egg"}
        potions = {item.potion_type_id for item in rewards if item.item_type == "potion"}
        guaranteed |= any(species in eggs and potion in potions for species, potion in catalog.pairs)
    if guaranteed:
        messages.append({
            "severity": "info", "code": "guaranteed_companion_paths",
            "message": "The catalog includes companion trails promising an egg and compatible potion. Their activity rules, prerequisites and deadlines must be met; other acquisitions can still depend on random draws.",
        })
    elif catalog.pairs:
        messages.append(
            {
                "severity": "warning",
                "code": "random_first_hatch",
                "message": "There is no assumed starter pet or guaranteed egg/potion. First hatch depends on the loaded eligible sources and random draws.",
            }
        )
    return messages


@dataclass
class SimPet:
    species: object
    potion: object
    growth_points: int = 0
    evolved_to_mount: bool = False


@dataclass
class SimIncubation:
    pair: tuple
    species: object
    potion: object
    duration_seconds: int
    ready_seconds: int
    ready_reported: bool = False


class Trial:
    def __init__(self, config, catalog, seed, *, incubation_policy=None, _comparators=True):
        self.config, self.catalog, self.seed = normalize_config(config), catalog, seed
        self.pet_incubation_policy = _capture_incubation_policy(incubation_policy)
        self.pending_incubation = None
        self.economy = Economy(self.config["economy"]) if self.config["economy"]["enabled"] else None
        self.reward_budget = RewardBudget(self.config["reward_budget"])
        self.reward_commitment = RewardCommitment(self.config["reward_commitment"])
        self.expedition_budget = ExpeditionBudget(self.config["expedition_budget"])
        self.challenge_gates = ChallengeGates(self.config["challenge_gates"], catalog)
        self.rng = random.Random(seed)
        self.day = self.active_days = self.streak = self.last_active = 0
        self.coins = self.total_xp = self.earned_coins = 0
        self.xp, self.inventory, self.counters = Counter(), Counter(), Counter()
        self.unlocked = {s.pk for s in catalog.skills.values() if not s.is_locked_by_default}
        self.skill_info = {
            s.pk: (
                s.is_locked_by_default,
                s.category_id,
                s.subject_id,
                tuple((p.required_skill_id, p.required_level) for p in s.prerequisites.all()),
            )
            for s in catalog.skills.values()
        }
        self.locked_prerequisites = [(pk, info[3]) for pk, info in self.skill_info.items() if info[0] and info[3]]
        self.category_required = defaultdict(set)
        for s in catalog.skills.values():
            if not s.is_locked_by_default:
                self.category_required[s.category.name].add(s.pk)
        self.cross_category_skills = {
            pk
            for pk, info in self.skill_info.items()
            if info[0] and any(self.skill_info[required][1] != info[1] for required, _level in info[3])
        }
        self.badges, self.completed_quests, self.seen_items = set(), set(), set()
        self.pets, self.pending_expeditions, self.quest_windows = {}, [], {}
        self.habit_strength = [0] * self.config["habits_per_day"]
        self.source_totals, self.sink_totals = defaultdict(Counter), defaultdict(Counter)
        self.milestones, self.trace, self.events = {}, [], []
        self.event_count = 0
        self._level_cache_key, self._level_cache = -1, {}
        self._pool_cache = {}
        self._initial_mount_possible_cache = {}
        self._badge_scope_cache = {}
        self._evaluating_badges = False
        self._pending_badge_scopes = []
        self.last_novelty_day = self.longest_novelty_gap = 0
        self.tags = {
            source: [
                SimpleNamespace(skill=s, xp_weight=weight)
                for category, name, weight in names
                for s in catalog.skills.values()
                if s.category.name == category and s.name == name
            ]
            for source, names in ACTIVITY_SKILLS.items()
        }
        self.quests = self._eligible_quests()
        self.finite_keys = self._finite_keys()
        native_quest_ids = set(self.reachable_quest_ids)
        self.challenge_gates.native_ids = {q.pk for q in self.quests if not q.is_repeatable and q.pk in native_quest_ids}
        gated_finite = self.finite_keys
        if self.challenge_gates.enabled:
            gated_finite = self._finite_keys(respect_gates=True)
        self.challenge_gates.reachable_ids = set(self.reachable_quest_ids)
        self.challenge_gates.native_finite_total = len(self.finite_keys)
        self.challenge_gates.reachable_finite_total = len(self.finite_keys & gated_finite)
        # Keep the installed native subset and denominator even for a gate that
        # makes a reward path impossible. Such a lock cannot create content.
        self.reachable_quest_ids = native_quest_ids
        if self.reward_commitment.enabled and _comparators:
            # Compare Coin policies while retaining the same expedition quotas.
            # A sibling initialization also recomputes challenge capacity and
            # prerequisites rather than reusing the constrained quest list.
            installed = Trial({**self.config, "reward_commitment": {"enabled": False}}, catalog, seed,
                              incubation_policy=self.pet_incubation_policy, _comparators=False)
            installed_finite = installed.finite_keys
            self.reward_commitment.installed_finite_total = len(installed_finite)
            removed = installed_finite - self.finite_keys
            self.reward_commitment.unavailable_finite_total = len(removed)
            self.reward_commitment.removed_finite_targets = dict(Counter(key.split(":")[0] for key in removed))
            self.reward_commitment.affected_paths = self._commitment_affected_paths()
        unlimited_finite = self.finite_keys
        if _comparators and any(value is not None for value in self.config["expedition_budget"].values()):
            unlimited = Trial({**self.config, "expedition_budget": dict(EXPEDITION_BUDGET_DEFAULTS)},
                              catalog, seed, incubation_policy=self.pet_incubation_policy, _comparators=False)
            unlimited_finite = unlimited.finite_keys
        self.expedition_budget.unlimited_finite_total = len(unlimited_finite)
        quota_removed = unlimited_finite - self.finite_keys
        self.expedition_budget.unavailable_finite_total = len(quota_removed)
        self.expedition_budget.removed_finite_targets = dict(Counter(key.split(":")[0] for key in quota_removed))
        self.completed_finite = set()

    @property
    def level(self):
        return SkillService.level_for_xp(self.total_xp)

    @property
    def mounts(self):
        return {pair: pet for pair, pet in self.pets.items() if pet.evolved_to_mount}

    @property
    def elapsed_seconds(self):
        return max(0, self.day - 1) * SECONDS_PER_DAY

    @property
    def incubation_is_ready(self):
        return self.pending_incubation is not None and self.pending_incubation.ready_seconds <= self.elapsed_seconds

    def mark_incubation_ready(self):
        pending = self.pending_incubation
        if self.incubation_is_ready and not pending.ready_reported:
            pending.ready_reported = True
            self.record("incubation_ready", target=pending.species.name)

    def claim_incubation(self):
        """The modeled child explicitly claims at the start of active care."""
        if (self.day - 1) % 7 >= self.config["active_days_per_week"] or not self.incubation_is_ready:
            return
        self.mark_incubation_ready()
        pending = self.pending_incubation
        self.pending_incubation = None
        if pending.pair in self.pets:
            return
        self.pets[pending.pair] = SimPet(pending.species, pending.potion)
        self.milestones.setdefault("first_pet", self.day)
        self.record("hatch", target=pending.species.name)
        self.evaluate_badges(scopes={"pet", "badges"})

    def _enabled_triggers(self):
        c = self.config
        triggers = {
            trigger
            for trigger, enabled in {
                "reading_logged": c["reading_minutes"] >= ReadingRewardService.TARGET_MINUTES,
                "clock_out": c["project_minutes"] > 0,
                "chore_complete": c["chores_per_day"] > 0,
                "habit_log": c["habits_per_day"] > 0,
                "journal_entry": c["journal_per_day"],
                "creation_logged": c["creations_per_day"] > 0,
                "movement_session": c["movement_sessions_per_day"] > 0,
            }.items()
            if enabled
        }
        if self._expedition_launch_capacity() > 0 and c["feed_strategy"] != "none" and self._initial_mount_possible(triggers):
            triggers.add("expedition_returned")
        return triggers

    def _expedition_launch_capacity(self):
        requested = self.config["expeditions_per_day"]
        cap = self.config["expedition_budget"]["daily_launches"]
        return requested if cap is None else min(requested, cap)

    def _direct_drop_triggers(self, triggers):
        """Saved clock facts and available random-roll sources have different gates."""
        return {
            trigger
            for trigger in triggers
            if trigger != "expedition_returned"
            and (trigger != "clock_out" or self.config["project_minutes"] >= ClockService.DROP_MINUTES_PER_DAY)
        }

    def _initial_mount_possible(self, triggers):
        key = frozenset(triggers)
        if key in self._initial_mount_possible_cache:
            return self._initial_mount_possible_cache[key]
        obtainable = set().union(*(self._obtainable_drop_items(trigger) for trigger in self._direct_drop_triggers(triggers)))
        # Determine whether source facts can reach a first mount without
        # assuming future expedition loot. Celebration pools can supply the
        # first ingredients or food, but cannot bootstrap an unreachable badge.
        potential = copy(self)
        potential.quests = potential._eligible_quests(enabled=triggers)
        potential._reachable_badges(obtainable, triggers=triggers)
        possible = any(target.startswith("mount:") for target in potential._reachability_capacity.companion_keys(
            feeding=self.config["feed_strategy"] != "none"))
        self._initial_mount_possible_cache[key] = possible
        return possible

    def _eligible_quests(self, *, enabled=None):
        enabled = self._enabled_triggers() if enabled is None else enabled
        badge_ids = {b.pk for b in self.catalog.badges}
        result = []
        for q in self.catalog.quests:
            filters = q.trigger_filter or {}
            if self._has_milestones(q) and (q.quest_type != "collection" or q.is_repeatable
                    or set(filters) != {"allowed_triggers"}
                    or tuple(filters.get("allowed_triggers") or ()) != ("reading_logged",)):
                continue
            allowed = set(filters.get("allowed_triggers") or EFFORT_TRIGGERS)
            if not allowed & enabled & FACT_TRIGGERS or q.required_badge_id and q.required_badge_id not in badge_ids:
                continue
            # Private object filters have no synthetic identity to match.
            if any(
                filters.get(key)
                for key in ("project_id", "skill_category_id", "chore_ids", "savings_goal_id", "on_time")
            ):
                continue
            if q.target_value > 0 and q.duration_days > 0 and self._challenge_capacity(q, enabled) >= q.target_value:
                result.append(q)
        # Keep only structurally usable milestone references. Actual progress
        # is evaluated at the fresh activity, never predicted as an offer rule.
        ids = {q.pk for q in result}
        return [q for q in result if (not getattr(q, "prerequisite_quest_id", None) or q.prerequisite_quest_id in ids)
                and (not getattr(q, "required_skill_id", None) or q.required_skill_id in self.catalog.skills)]

    @staticmethod
    def _has_milestones(quest):
        return bool(getattr(quest, "prerequisite_quest_id", None)
                    or getattr(quest, "required_skill_id", None) or getattr(quest, "required_skill_level", 0))

    def _milestones_met(self, quest):
        prerequisite = getattr(quest, "prerequisite_quest_id", None)
        skill = getattr(quest, "required_skill_id", None)
        level = getattr(quest, "required_skill_level", 0)
        return (not prerequisite or prerequisite in self.completed_quests) and (
            not skill and level == 0 or skill in self.unlocked
            and 1 <= level <= 6 and SkillService.level_for_xp(self.xp[skill]) >= level)

    def _challenge_capacity(self, quest, triggers):
        c = self.config
        counts = {
            "reading_logged": int(c["reading_minutes"] >= ReadingRewardService.TARGET_MINUTES),
            "clock_out": int(c["project_minutes"] > 0),
            "chore_complete": c["chores_per_day"],
            "habit_log": c["habits_per_day"],
            "journal_entry": int(c["journal_per_day"]),
            "creation_logged": min(c["creations_per_day"], CreationService.DAILY_XP_LIMIT),
            "movement_session": c["movement_sessions_per_day"],
            "expedition_returned": self._expedition_launch_capacity(),
        }
        snapshot = {
            "metric": "damage" if quest.quest_type == "boss" else "count",
            "filter": quest.trigger_filter,
            "unit": "actions",
        }
        per_day = sum(
            (
                _amount(
                    snapshot,
                    SimpleNamespace(
                        trigger_type=trigger,
                        context={
                            "duration_minutes": c["project_minutes"]
                            if trigger == "clock_out"
                            else c["movement_minutes"]
                        },
                    ),
                )
                * counts.get(trigger, 0)
                for trigger in triggers
            ),
            Decimal(0),
        )
        # Windows can begin on any weekday after badge unlock. Use the largest
        # possible active-day count; never declare an impossible target reachable.
        weeks, remainder = divmod(quest.duration_days, 7)
        active = weeks * c["active_days_per_week"] + max(
            sum((offset + day) % 7 < c["active_days_per_week"] for day in range(remainder)) for offset in range(7)
        )
        return per_day * active

    def _source_pool(self, trigger, level, expedition_tier=None):
        cache_key = (trigger, expedition_tier, level)
        if cache_key not in self._pool_cache:
            entries = [e for e in self.catalog.pools.get(trigger, []) if e.min_level <= level]
            if expedition_tier is not None and not entries:
                entries = [e for key in ("clock_out", "chore_complete")
                           for e in self.catalog.pools.get(key, []) if e.min_level <= level]
            self._pool_cache[cache_key] = entries, companion_drop_weights(entries)
        return self._pool_cache[cache_key]

    def _obtainable_drop_items(self, trigger, *, installed=False):
        budgets = drop_tier_weights(trigger)
        return {
            entry.item_id for entry in self.catalog.pools.get(trigger, [])
            if entry.min_level <= max(XP_THRESHOLDS) and entry.weight > 0
            and budgets.get(entry.item.rarity, 0) > 0
            and (installed or not self.reward_commitment.enabled or self.reward_commitment.allows(entry.item))
        }

    def eligible_pool(self, trigger, *, expedition_tier=None, owned_item_ids=None, record_filtered=False):
        entries, authored = self._source_pool(trigger, self.level, expedition_tier)
        if self.reward_commitment.enabled:
            remaining = self.reward_commitment.remaining(self.day, expedition=expedition_tier is not None)
            filtered = [entry for entry in entries
                        if self.reward_commitment.allows(entry.item, tier=expedition_tier, remaining=remaining)]
            if record_filtered:
                key = "filtered_expedition_candidates" if expedition_tier is not None else "filtered_activity_pouch_candidates"
                self.reward_commitment.totals[key] += len(entries) - len(filtered)
            entries = filtered
            authored = companion_drop_weights(entries)
        budgets = (TIER_CONFIG[expedition_tier]["rarity_weights"] if expedition_tier is not None
                   else drop_tier_weights(trigger))
        if expedition_tier is None:
            eligible = [(entry, weight) for entry, weight in zip(entries, authored)
                        if weight > 0 and budgets.get(entry.item.rarity, 0) > 0]
            entries = [entry for entry, _weight in eligible]
            authored = [weight for _entry, weight in eligible]
        if owned_item_ids is None:
            owned_item_ids = {pk for pk, quantity in self.inventory.items()
                              if quantity > 0 and self.catalog.items[pk].item_type in COSMETIC_TYPES}
        # Ownership changes during a run (and within an expedition's pre-roll),
        # so only the source pool is cached, never its effective draw weights.
        return entries, tier_balanced_weights(entries, budgets, authored_weights=authored,
                                              owned_item_ids=owned_item_ids)

    def _finite_keys(self, *, installed=False, respect_gates=False):
        # Scenario-reachable means a compatible source exists in this model,
        # not that the target can be completed within the requested horizon.
        triggers = self._enabled_triggers()
        obtainable = set().union(*(self._obtainable_drop_items(trigger, installed=installed)
                                  for trigger in self._direct_drop_triggers(triggers)))
        reachable_badges = self._reachable_badges(obtainable, respect_gates=respect_gates, installed=installed)
        capacity = self._reachability_capacity
        keys = {f"cosmetic:{pk}" for pk in obtainable if self.catalog.items[pk].item_type in COSMETIC_TYPES
                and capacity.prove_collection([pk]) is not None}
        keys.update(capacity.companion_keys(feeding=self.config["feed_strategy"] != "none"))
        keys.update(f"quest:{q.pk}" for q in self.quests if not q.is_repeatable and q.pk in self.reachable_quest_ids)
        keys.update(f"badge:{pk}" for pk in reachable_badges)
        return keys

    def _commitment_affected_paths(self):
        """Static lost source paths; an item may still be available elsewhere."""
        paths = {}
        triggers = self._enabled_triggers()
        sources = [(trigger, None) for trigger in self._direct_drop_triggers(triggers)]
        if any(key.startswith("badge:") for key in self.finite_keys):
            sources.append(("badge_earned", None))
        if self.reachable_quest_ids:
            sources.append(("quest_complete", None))
        if "expedition_returned" in triggers and self.config["expedition_budget"]["daily_items"] != 0:
            sources.append(("expedition_returned", self.config["expedition_tier"]))
        for trigger, tier in sources:
            for level in XP_THRESHOLDS:
                entries, _weights = self._source_pool(trigger, level, tier)
                budgets = TIER_CONFIG[tier]["rarity_weights"] if tier else drop_tier_weights(trigger)
                for entry in entries:
                    if entry.weight <= 0 or budgets.get(entry.item.rarity, 0) <= 0:
                        continue
                    if not self.reward_commitment.allows(entry.item, tier=tier):
                        paths[(trigger, entry.item_id)] = {
                            "source": trigger, "item_id": entry.item_id, "name": entry.item.display_name,
                            "required_coins": item_liability(entry.item, expedition=tier is not None),
                            "maximum_available_coins": self.reward_commitment.static_limit(tier),
                        }
        return [paths[key] for key in sorted(paths)]

    def _reachable_badges(self, obtainable, *, respect_gates=False, installed=False, triggers=None):
        """Filter finite targets by the scenario's eventual source capacity.

        An unbounded potential state is only a reachability calculation. It is
        never used for rewards or timelines; real trials still begin at zero.
        """
        potential = copy(self)
        potential.counters = Counter()
        potential.xp = Counter()
        potential.unlocked = set(self.unlocked)
        potential.badges, potential.completed_quests = set(), set()
        potential.inventory = Counter({pk: 1 for pk in obtainable})
        potential.pets = {}
        capacity = ItemCapacity(self.catalog, obtainable)
        max_count = 10**9
        c = self.config
        unscoped = (c["journal_per_day"] and self.tags["journal"]) or (
            c["movement_sessions_per_day"]
            and MovementSessionService.compute_xp_pool(c["movement_minutes"], c["movement_intensity"]) > 0
        )
        available_scopes = {"badges"}
        for enabled, scopes in (
            (c["reading_minutes"] >= ReadingRewardService.TARGET_MINUTES, {"skill_xp", "coin"}),
            (c["project_minutes"], {"time", "skill_xp", "coin"}),
            (c["chores_per_day"], {"chore", "skill_xp", "coin", "money"}),
            (c["habits_per_day"], {"habit", "skill_xp"} if c["habit_xp"] else {"habit"}),
            (c["creations_per_day"], {"creation", "skill_xp"}),
            (c["journal_per_day"], {"chronicle"}),
            (self.quests, {"quest", "coin", "skill_xp"}),
            (c["movement_sessions_per_day"] * c["movement_minutes"] >= 10, {"coin", "skill_xp"}),
        ):
            if enabled:
                available_scopes.update(scopes)
        count_sources = {
            "project_sessions": c["project_minutes"],
            "project_minutes": c["project_minutes"],
            "chores": c["chores_per_day"],
            "habits": c["habits_per_day"],
            "journal": c["journal_per_day"],
            "creations": c["creations_per_day"],
            "movement_sessions": c["movement_sessions_per_day"],
            "movement_minutes": c["movement_sessions_per_day"],
        }
        for key, enabled in count_sources.items():
            potential.counters[key] = max_count if enabled else 0
        streak_cap = max_count if c["active_days_per_week"] == 7 else c["active_days_per_week"]
        potential.counters["project_best_streak"] = streak_cap if c["project_minutes"] else 0
        potential.counters["journal_best_streak"] = streak_cap if c["journal_per_day"] else 0
        strength_cap = max_count if c["active_days_per_week"] >= 4 else c["active_days_per_week"]
        potential.habit_strength = [strength_cap] * c["habits_per_day"]
        enabled_triggers = self._enabled_triggers() if triggers is None else triggers
        potential.earned_coins = max_count if enabled_triggers else 0
        earning = set()
        for source, enabled in {
            "reading": c["reading_minutes"] >= ReadingRewardService.TARGET_MINUTES,
            "project": c["project_minutes"] >= 3,
            "chores": c["chores_per_day"] and c["chore_xp"] > 0,
            "habits": c["habits_per_day"] and c["habit_xp"] > 0,
            "journal": c["journal_per_day"],
            "creations": c["creations_per_day"],
            "movement": c["movement_sessions_per_day"]
            and MovementSessionService.compute_xp_pool(c["movement_minutes"], c["movement_intensity"]) > 0,
        }.items():
            if enabled:
                earning.update(tag.skill.pk for tag in self.tags[source])
        # Daily bonus uses the first qualifying source's tags, including when
        # that source itself has zero XP (e.g. a Coin-only chore).
        if c["chores_per_day"] or c["project_minutes"] >= 10:
            earning.update(tag.skill.pk for tag in self.tags["chores"])
        elif c["movement_sessions_per_day"] * c["movement_minutes"] >= 10:
            earning.update(tag.skill.pk for tag in self.tags["movement"])
        for _ in range(len(self.catalog.badges) + len(self.quests) + 1):
            previous = (
                len(potential.badges),
                len(potential.completed_quests),
                len(earning),
                len(potential.unlocked),
                len(obtainable),
            )
            for pk in earning & potential.unlocked:
                potential.xp[pk] = max(XP_THRESHOLDS.values())
            potential.total_xp = sum(potential.xp.values())
            potential.evaluate_unlocks()
            potential_triggers = set(enabled_triggers)
            if "expedition_returned" in potential_triggers:
                # Spend the first mount's physical ingredients/food before
                # treating trips as a renewable reward source. An expedition
                # cannot finance its own prerequisite mount.
                proof = capacity.prove_companions(1, grown=True)
                if proof is None:
                    potential_triggers.discard("expedition_returned")
                else:
                    capacity = proof
                if "expedition_returned" in potential_triggers and self.config["expedition_budget"]["daily_items"] != 0:
                    tier = self.config["expedition_tier"]
                    for level in XP_THRESHOLDS:
                        entries, weights = self._source_pool("expedition_returned", level, tier)
                        renewable = {entry.item_id for entry, weight in zip(entries, weights)
                                          if weight > 0 and TIER_CONFIG[tier]["rarity_weights"].get(entry.item.rarity, 0) > 0
                                          and (installed or not self.reward_commitment.enabled
                                               or self.reward_commitment.allows(entry.item, tier=tier))}
                        obtainable.update(renewable)
                        capacity.renewable.update(renewable)
            for q in self.quests:
                if q.pk in potential.completed_quests:
                    continue
                if q.required_badge_id and q.required_badge_id not in potential.badges:
                    continue
                if self._challenge_capacity(q, potential_triggers) < q.target_value:
                    continue
                if respect_gates and not self.challenge_gates.potential_allows(q, potential):
                    continue
                if not potential._milestones_met(q):
                    continue
                potential.completed_quests.add(q.pk)
                obtainable.update(row.item_id for row in q.reward_items.all() if row.item_id in self.catalog.items)
                pool = self._obtainable_drop_items("quest_complete", installed=installed)
                obtainable.update(pool)
                capacity.add_draws("quest_complete", pool, repeatable=q.is_repeatable)
                for row in q.reward_items.all():
                    if row.item_id in self.catalog.items:
                        if q.is_repeatable:
                            capacity.renewable.add(row.item_id)
                        else:
                            capacity.fixed[row.item_id] += row.quantity
                potential.counters[f"quest_completed:{q.pk}"] = max_count if q.is_repeatable else 1
                if q.xp_reward > 0:
                    earning.update(tag.skill_id for tag in q.skill_tags.all())
            potential.inventory.update({pk: 1 for pk in obtainable if pk not in potential.inventory})
            potential_pairs = capacity.companion_keys(feeding=self.config["feed_strategy"] != "none")
            potential.pets = {}
            for pair, (species, potion) in self.catalog.pairs.items():
                if f"pet:{pair}" in potential_pairs:
                    grown = f"mount:{pair}" in potential_pairs
                    potential.pets[pair] = SimPet(species, potion, 100 if grown else 0, grown)
            for kind in ("boss", "collection"):
                potential.counters[f"{kind}_quests"] = sum(
                    potential.counters[f"quest_completed:{q.pk}"] for q in self.quests if q.quest_type == kind
                )
            potential.counters["quest_completions"] = sum(
                potential.counters[f"quest_completed:{q.pk}"] for q in self.quests
            )
            # Care evaluates pet criteria even without an unscoped activity.
            # Recompute after each pass: a badge-gated challenge can introduce
            # the first obtainable pair or the food needed for its evolution.
            care_scopes = {"pet"} if potential.pets else set()
            inventory_scopes = {"rpg_inventory", "badges"} if obtainable else set()
            reachable_types = None if unscoped else criteria_types_for_scopes(available_scopes | care_scopes | inventory_scopes)
            for badge in self.catalog.badges:
                if (reachable_types is None or badge.criteria_type in reachable_types) and potential._badge_matches(
                    badge
                ):
                    if badge.pk in potential.badges:
                        continue
                    proof = capacity
                    count = int((badge.criteria_value or {}).get("count", 1))
                    if badge.criteria_type in {"pets_hatched", "pet_species_owned", "mounts_evolved"}:
                        proof = capacity.prove_companions(count, grown=badge.criteria_type == "mounts_evolved",
                            distinct_species=badge.criteria_type == "pet_species_owned")
                    elif badge.criteria_type == "cosmetic_set_owned":
                        slugs = set((badge.criteria_value or {}).get("slugs", []))
                        proof = capacity.prove_collection([pk for pk, item in self.catalog.items.items() if item.slug in slugs])
                    if proof is None:
                        continue
                    capacity = proof
                    potential.badges.add(badge.pk)
                    pool = self._obtainable_drop_items("badge_earned", installed=installed)
                    obtainable.update(pool)
                    capacity.add_draws("badge_earned", pool)
            if previous == (
                len(potential.badges),
                len(potential.completed_quests),
                len(earning),
                len(potential.unlocked),
                len(obtainable),
            ):
                break
        self.reachable_quest_ids = potential.completed_quests
        self._reachability_capacity = capacity
        return potential.badges

    def record(self, source, *, coins=0, xp=0, items=0, target="", **details):
        self.event_count += 1
        if len(self.events) < 1000:
            self.events.append(
                {"day": self.day, "source": source, "coins": coins, "xp": xp, "items": items, "target": str(target), **details}
            )

    def coin_award(self, amount, source):
        if amount <= 0:
            return
        amount = self.reward_budget.award(amount, source, self.day)
        if amount <= 0:
            return
        self.coins += amount
        self.earned_coins += amount
        self.source_totals[source]["coins"] += amount
        self.reward_commitment.paid(amount, source)
        self.record(source, coins=amount)

    def award_xp(self, pool, tags, source):
        credited = 0
        for skill, amount in SkillService._iter_tagged_xp(tags, pool):
            if skill.pk not in self.unlocked:
                continue
            self.xp[skill.pk] += amount
            credited += amount
            self.evaluate_unlocks()
        self.total_xp += credited
        self.source_totals[source]["xp"] += credited
        if credited:
            self.record(source, xp=credited)
        return credited

    def evaluate_unlocks(self):
        for pk, prerequisites in self.locked_prerequisites:
            if pk in self.unlocked:
                continue
            if all(self.xp[required] >= XP_THRESHOLDS.get(level, math.inf) for required, level in prerequisites):
                self.unlocked.add(pk)

    def grant_item(self, pk, quantity, source, *, salvage_cosmetic=False, salvage_egg=False):
        item = self.catalog.items.get(pk)
        if not item or quantity <= 0:
            return
        if (
            salvage_cosmetic
            and item.item_type in COSMETIC_TYPES
            and self.inventory[pk] > 0
            and (source != "expeditions" or item.coin_value > 0)
        ) or (salvage_egg and item.item_type == "egg" and any(pair[0] == item.pet_species_id for pair in self.mounts)):
            self.coin_award(item.coin_value * quantity, f"{source}_salvage")
            return
        self.inventory[pk] += quantity
        self.reward_commitment.grant_pouch(item, quantity, source)
        self.seen_items.add(pk)
        self.source_totals[source]["items"] += quantity
        self.record(source, items=quantity, target=item.display_name)
        self.evaluate_inventory_badges()

    def consume(self, pk, quantity, source):
        self.inventory[pk] -= quantity
        self.sink_totals[source]["items"] += quantity
        self.record(source, items=-quantity, target=self.catalog.items[pk].display_name)

    def drop(self, trigger):
        rate = min(
            BASE_DROP_RATES.get(trigger, 0.20) + min(self.streak * STREAK_DROP_BONUS_PER_DAY, STREAK_DROP_BONUS_CAP),
            1.0,
        )
        self.counters["drop_opportunities"] += 1
        self.counters[f"drop_opportunities:{trigger}"] += 1
        if self.rng.random() > rate:
            return
        entries, weights = self.eligible_pool(trigger, record_filtered=True)
        if entries and sum(weights) > 0:
            entry = self.rng.choices(entries, weights=weights, k=1)[0]
            if self.reward_commitment.enabled:
                self.reward_commitment.reserve_item(entry.item, self.day)
            self.grant_item(entry.item_id, 1, "drops", salvage_cosmetic=True)
            self.counters["drops"] += 1
        elif self.reward_commitment.enabled:
            self.reward_commitment.totals["activity_empty_drops"] += 1

    def check_in(self):
        if self.last_active == self.day:
            return
        self.streak = self.streak + 1 if self.last_active == self.day - 1 else 1
        self.last_active = self.day
        amount = int(BASE_CHECK_IN_COINS * min(1 + self.streak * STREAK_MULTIPLIER_PER_DAY, STREAK_MULTIPLIER_CAP))
        self.coin_award(amount, "check_in")

    def event(
        self, trigger, context=None, tags=None, *, drops=True, catalog_eligible=True, evaluate_source_badges=True
    ):
        context, tags = context or {}, tags or []
        scopes = {
            "reading_logged": {"skill_xp", "coin", "badges"},
            "clock_out": {"time", "skill_xp", "coin", "badges"},
            "chore_complete": {"chore", "skill_xp", "coin", "money", "badges"},
            "habit_log": {"habit", "skill_xp", "badges"},
            "creation_logged": {"creation", "skill_xp", "badges"},
        }
        if (
            evaluate_source_badges
            and trigger != "expedition_returned"
        ):
            source_scopes = scopes.get(trigger)
            if trigger == "habit_log" and self.config["habit_xp"] == 0:
                source_scopes = {"habit", "badges"}
            self.evaluate_badges(scopes=source_scopes)
        self.check_in()
        if drops:
            self.drop(trigger)
        if trigger in FACT_TRIGGERS:
            self.advance_challenges(trigger, context, catalog_eligible=catalog_eligible)
            if trigger in {"chore_complete", "homework_complete", "milestone_complete", "project_complete"}:
                self.daily_bonus(tags)
            elif trigger in {"clock_out", "movement_session"}:
                self.counters["qualifying_minutes_today"] += context.get("duration_minutes", 0)
                if self.counters["qualifying_minutes_today"] >= 10:
                    self.daily_bonus(tags)
        self.update_progress()

    def daily_bonus(self, tags):
        if self.counters["daily_bonus_day"] == self.day:
            return
        self.counters["daily_bonus_day"] = self.day
        self.coin_award(DAILY_BONUS_COINS, "daily_bonus")
        self.award_xp(DAILY_BONUS_XP, tags or self.tags["chores"], "daily_bonus")
        self.evaluate_badges(scopes={"coin", "skill_xp", "badges"})

    def advance_challenges(self, trigger, context, *, catalog_eligible=True):
        if not catalog_eligible:
            return
        # Production materializes eligible catalog goals once before processing
        # the fact. A completion seal cannot enroll its next chapter halfway
        # through this same fact, regardless of catalog ordering.
        eligible = [q for q in self.quests if self.challenge_gates.can_offer(q, self)
                    and (q.pk in self.quest_windows or self._milestones_met(q))]
        for q in eligible:
            snapshot = {
                "metric": "damage" if q.quest_type == "boss" else "count",
                "filter": q.trigger_filter,
                "unit": "actions",
            }
            amount = _amount(snapshot, SimpleNamespace(context=context, trigger_type=trigger))
            if q.pk not in self.quest_windows:
                if self._has_milestones(q) and amount <= 0:
                    continue
                self.quest_windows[q.pk] = {"start": self.day, "progress": Decimal(0), "paid": False}
                self.challenge_gates.unlock_days.setdefault(q.pk, self.day)
            window = self.quest_windows[q.pk]
            if self.day >= window["start"] + q.duration_days:
                if not q.is_repeatable:
                    continue
                periods = (self.day - window["start"]) // q.duration_days
                window.update(start=window["start"] + periods * q.duration_days, progress=Decimal(0), paid=False)
            if window["paid"]:
                continue
            window["progress"] += amount
            if window["progress"] < q.target_value:
                continue
            window["paid"] = True
            self.completed_quests.add(q.pk)
            self.challenge_gates.completion_days.setdefault(q.pk, self.day)
            self.counters[f"{q.quest_type}_quests"] += 1
            self.counters["quest_completions"] += 1
            self.counters[f"quest_completed:{q.pk}"] += 1
            self.coin_award(q.coin_reward, "challenges")
            self.award_xp(q.xp_reward, list(q.skill_tags.all()), "challenges")
            self.evaluate_badges(scopes={"quest", "coin", "skill_xp", "badges"})
            for row in q.reward_items.all():
                self.grant_item(row.item_id, row.quantity, "challenges", salvage_egg=True)
            self.record("challenge_completed", target=q.name)
            self.drop("quest_complete")
            self.milestones.setdefault("first_challenge", self.day)

    def _badge_matches(self, badge):
        kind, c = badge.criteria_type, badge.criteria_value or {}
        count = int(c.get("count", 1))
        if self._level_cache_key != self.total_xp:
            self._level_cache = {pk: SkillService.level_for_xp(xp) for pk, xp in self.xp.items()}
            self._level_cache_key = self.total_xp
        levels = self._level_cache
        if kind == "first_clock_in":
            return self.counters["project_sessions"] > 0
        if kind == "hours_worked":
            return self.counters["project_minutes"] / 60 >= c.get("hours", 0)
        if kind == "hours_in_day":
            return self.config["project_minutes"] / 60 >= c.get("hours", 4) and self.counters["project_sessions"] > 0
        if kind == "days_worked":
            return self.counters["project_sessions"] >= int(c.get("count", 5))
        if kind == "skill_level_reached":
            return sum(level >= c.get("level", 2) for level in levels.values()) >= count
        if kind == "skills_unlocked":
            return sum(self.skill_info[pk][0] for pk in self.unlocked) >= count
        if kind == "subjects_completed":
            return (
                len(
                    {
                        self.skill_info[pk][2]
                        for pk, level in levels.items()
                        if level >= c.get("min_level", 2) and self.skill_info[pk][2]
                    }
                )
                >= count
            )
        if kind == "skill_categories_breadth":
            return len(
                {self.skill_info[pk][1] for pk, level in levels.items() if level >= c.get("min_level", 1)}
            ) >= c.get("categories", 4)
        if kind == "cross_category_unlock":
            return bool(self.cross_category_skills & self.unlocked)
        if kind == "category_mastery":
            required = self.category_required.get(c.get("category"))
            return bool(required) and all(levels.get(pk, 0) >= int(c.get("min_level", 3)) for pk in required)
        if kind == "streak_days":
            return self.counters["project_best_streak"] >= int(c.get("days", 7))
        if kind == "total_coins_earned":
            return self.earned_coins >= c.get("amount", 500)
        if kind == "chore_completions":
            return self.counters["chores"] >= int(c.get("count", 10))
        if kind == "habit_taps_lifetime":
            return self.counters["habits"] >= int(c.get("count", 50))
        if kind == "habit_max_strength":
            return any(s >= int(c.get("strength", 7)) for s in self.habit_strength)
        if kind == "habit_count_at_strength":
            return sum(s >= int(c.get("strength", 5)) for s in self.habit_strength) >= int(c.get("count", 3))
        if kind == "badges_earned_count":
            return len(self.badges) >= int(c.get("count", 10))
        if kind == "pets_hatched":
            return len(self.pets) >= count
        if kind == "pet_species_owned":
            return len({pair[0] for pair in self.pets}) >= count
        if kind == "mounts_evolved":
            return len(self.mounts) >= count
        if kind == "quest_completed":
            wanted = c.get("quest_names")
            if wanted is None:
                if not c.get("quest_name"):
                    return False
                wanted = [c["quest_name"]]
            matched = [q for q in self.quests if (not wanted or q.name in wanted) and q.pk in self.completed_quests]
            if c.get("count") is not None:
                return sum(self.counters[f"quest_completed:{q.pk}"] for q in matched) >= int(c["count"])
            return bool(matched)
        if kind == "boss_quests_completed":
            return self.counters["boss_quests"] >= int(c.get("count", 5))
        if kind == "collection_quests_completed":
            return self.counters["collection_quests"] >= int(c.get("count", 5))
        if kind == "cosmetic_set_owned":
            return bool(c.get("slugs")) and set(c["slugs"]).issubset(
                {self.catalog.items[pk].slug for pk, qty in self.inventory.items() if qty > 0}
            )
        if kind == "journal_entries_written":
            return self.counters["journal"] >= count
        if kind == "journal_streak_days":
            return self.counters["journal_best_streak"] >= int(c.get("days", 3))
        if kind == "creations_logged":
            return self.counters["creations"] >= count
        if kind == "creation_skill_breadth":
            return len(self.tags["creations"]) >= int(c.get("count", 5)) and self.counters["creations"] > 0
        if kind == "movement_sessions_logged":
            return self.counters["movement_sessions"] >= count
        if kind == "movement_total_minutes":
            return self.counters["movement_minutes"] >= int(c.get("minutes", 60))
        return False

    def evaluate_inventory_badges(self):
        self.evaluate_badges(scopes={"rpg_inventory", "badges"})

    def evaluate_badges(self, *, scopes=None):
        # Preserve each ordered live pass. Only scopes queued by an inventory
        # mutation drain afterward; rewards never re-enter the activity loop.
        requested = set(scopes) if scopes else None
        if self._evaluating_badges:
            if requested is None:
                self._pending_badge_scopes[:] = [None]
            elif None not in self._pending_badge_scopes:
                if self._pending_badge_scopes:
                    self._pending_badge_scopes[0].update(requested)
                else:
                    self._pending_badge_scopes.append(requested)
            return
        self._evaluating_badges = True
        self._pending_badge_scopes = [requested]
        try:
            while self._pending_badge_scopes:
                self._evaluate_badge_pass(scopes=self._pending_badge_scopes.pop(0))
        finally:
            self._evaluating_badges = False
            self._pending_badge_scopes = []

    def _evaluate_badge_pass(self, *, scopes=None):
        key = frozenset(scopes) if scopes else None
        if key not in self._badge_scope_cache:
            relevant = criteria_types_for_scopes(scopes) if scopes else None
            self._badge_scope_cache[key] = [
                b for b in self.catalog.badges if relevant is None or b.criteria_type in relevant
            ]
        for badge in self._badge_scope_cache[key]:
            if badge.pk in self.badges or not self._badge_matches(badge):
                continue
            self.badges.add(badge.pk)
            if badge.award_coins:
                self.coin_award(int(settings.COINS_PER_BADGE_RARITY.get(badge.rarity, 0)), "badges")
            active = [pk for pk in self.xp if pk in self.unlocked and SkillService.level_for_xp(self.xp[pk]) > 0]
            if badge.xp_bonus > 0 and active:
                each = max(1, badge.xp_bonus // len(active))
                for pk in active:
                    self.xp[pk] += each
                self.total_xp += each * len(active)
                self.source_totals["badges"]["xp"] += each * len(active)
                self.evaluate_unlocks()
                self.record("badges", xp=each * len(active), target=badge.name)
            self.record("badge_earned", target=badge.name)
            self.drop("badge_earned")

    def start_incubation(self):
        if self.pending_incubation is not None:
            return
        potion_ids = [
            pk
            for pk, quantity in self.inventory.items()
            if quantity > 0 and self.catalog.items[pk].item_type == "potion"
        ]
        for pk in sorted(self.inventory):
            egg = self.catalog.items[pk]
            if egg.item_type != "egg" or self.inventory[pk] <= 0:
                continue
            for potion_id in sorted(potion_ids):
                potion = self.catalog.items[potion_id]
                pair = (egg.pet_species_id, potion.potion_type_id)
                if (
                    potion.item_type != "potion"
                    or self.inventory[potion_id] <= 0
                    or pair in self.pets
                    or pair not in self.catalog.pairs
                ):
                    continue
                self.consume(pk, 1, "hatching")
                self.consume(potion_id, 1, "hatching")
                duration = self.pet_incubation_policy["duration_seconds"]
                species, potion_type = self.catalog.pairs[pair]
                self.pending_incubation = SimIncubation(pair, species, potion_type, duration,
                                                       self.elapsed_seconds + duration)
                self.record("incubation_started", target=species.name, duration_seconds=duration,
                            ready_day=1 + math.ceil(self.pending_incubation.ready_seconds / SECONDS_PER_DAY))
                return

    def feed_and_hatch(self):
        self.start_incubation()
        if self.config["feed_strategy"] != "none":
            for pk in sorted(self.inventory):
                food = self.catalog.items[pk]
                if food.item_type != "food":
                    continue
                while self.inventory[pk] > 0:
                    pet = next((p for p in self.pets.values() if not p.evolved_to_mount), None)
                    if pet is None:
                        break
                    food_type = str(food.metadata.get("food_type", "")).strip()
                    preferred = (
                        food.food_species_id == pet.species.pk
                        if food.food_species_id
                        else bool(food_type) and food_type == pet.species.food_preference
                    )
                    middle, grown = growth_thresholds(pet)
                    food_view = SimpleNamespace(rarity=food.rarity, metadata=dict(food.metadata or {}))
                    growth = food_base_growth(food_view) + (PREFERRED_FOOD_BONUS if preferred else 0)
                    pet.growth_points = min(grown, pet.growth_points + growth)
                    self.consume(pk, 1, "feeding")
                    if pet.growth_points >= middle:
                        self.milestones.setdefault("first_middle", self.day)
                    if pet.growth_points >= grown:
                        pet.evolved_to_mount = True
                        self.milestones.setdefault("first_mount", self.day)
                        self.record("evolution", target=pet.species.name)
                        self.evaluate_badges(scopes={"pet", "badges"})
        for pk in sorted(self.inventory):
            item = self.catalog.items[pk]
            if item.item_type == "coin_pouch" and self.inventory[pk] > 0:
                quantity = self.inventory[pk]
                amount = int((item.metadata or {}).get("coins") or item.coin_value or 0)
                if amount > 0:
                    if self.reward_commitment.enabled:
                        self.reward_commitment.open_pouches(item, quantity)
                    self.consume(pk, quantity, "coin_pouch_opening")
                    self.coin_award(amount * quantity, "coin_pouches")
        self.update_progress()

    def claim_expeditions(self):
        remaining = []
        for expedition in self.pending_expeditions:
            if expedition["returns"] > self.day:
                remaining.append(expedition)
                continue
            self.coin_award(expedition["coins"], "expeditions")
            salvage_before = self.source_totals["expeditions_salvage"]["coins"] if self.reward_commitment.enabled else 0
            for pk in expedition["items"]:
                self.grant_item(pk, 1, "expeditions", salvage_cosmetic=True)
            self.expedition_budget.claim(expedition)
            if self.reward_commitment.enabled:
                salvage_paid = self.source_totals["expeditions_salvage"]["coins"] - salvage_before
                self.reward_commitment.totals["released_salvage_reserve"] += max(0, expedition.get("salvage_reserve", 0) - salvage_paid)
            self.event("expedition_returned", drops=False)
        self.pending_expeditions = remaining

    def launch_expeditions(self):
        active = {e["pair"] for e in self.pending_expeditions}
        tier = self.config["expedition_tier"]
        tier_config = TIER_CONFIG[tier]
        item_slots = COMMITMENT_POLICY["tiers"][tier]["item_slots"] if self.reward_commitment.enabled else tier_config["item_slots"]
        available = [pair for pair in self.mounts if pair not in active]
        allowed_launches = self.expedition_budget.prepare_launches(self.day, self.config["expeditions_per_day"], len(available))
        for pair in available[:allowed_launches]:
            coins = (self.reward_commitment.reserve_direct(self.day, tier) if self.reward_commitment.enabled
                     else max(1, int(tier_config["base_coins"] * (0.85 + self.rng.random() * 0.30))))
            owned = {pk for pk, quantity in self.inventory.items()
                     if quantity > 0 and self.catalog.items[pk].item_type in COSMETIC_TYPES}
            items = []
            salvage_reserve = 0
            permitted_slots = self.expedition_budget.prepare_slots(self.day, item_slots)
            for _ in range(permitted_slots):
                entries, weights = self.eligible_pool("expedition_returned", expedition_tier=tier,
                                                       owned_item_ids=owned, record_filtered=True)
                if not entries or not any(weights):
                    break
                entry = self.rng.choices(entries, weights=weights, k=1)[0]
                if self.reward_commitment.enabled:
                    self.reward_commitment.reserve_item(entry.item, self.day, expedition=True)
                    if entry.item.item_type in COSMETIC_TYPES:
                        salvage_reserve += item_liability(entry.item, expedition=True)
                items.append(entry.item_id)
                if entry.item.item_type in COSMETIC_TYPES:
                    owned.add(entry.item_id)
            self.expedition_budget.promise_items(self.day, permitted_slots, len(items))
            self.expedition_budget.trip(coins, len(items))
            self.pending_expeditions.append(
                {
                    "pair": pair,
                    "returns": self.day + tier_config["duration_minutes"] / 1440,
                    "coins": coins,
                    "items": items,
                    "budget_promised_items": len(items),
                    **({"salvage_reserve": salvage_reserve} if self.reward_commitment.enabled else {}),
                }
            )
            if self.reward_commitment.enabled:
                totals = self.reward_commitment.totals
                totals["expedition_launches"] += 1
                totals["zero_coin_launches"] += int(coins == 0)
                totals["empty_expedition_launches"] += int(coins == 0 and not items)
                totals["empty_item_slots"] += item_slots - len(items)
            self.record("expedition_launch", target=self.pets[pair].species.name)

    def update_progress(self):
        if self.earned_coins > 0 or self.total_xp > 0:
            self.milestones.setdefault("first_reward", self.day)
        for level in (1, 3, 6):
            if self.level >= level:
                self.milestones.setdefault(f"character_level_{level}", self.day)
        completed = {f"badge:{pk}" for pk in self.badges} | {f"quest:{pk}" for pk in self.completed_quests}
        completed.update(f"cosmetic:{pk}" for pk in self.seen_items)
        for pair, pet in self.pets.items():
            completed.add(f"pet:{pair}")
            if pet.growth_points >= growth_thresholds(pet)[0]:
                completed.add(f"middle:{pair}")
            if pet.evolved_to_mount:
                completed.add(f"mount:{pair}")
        completed &= self.finite_keys
        if len(completed) > len(self.completed_finite):
            self.longest_novelty_gap = max(self.longest_novelty_gap, self.day - self.last_novelty_day)
            self.last_novelty_day = self.day
        self.completed_finite = completed
        if self.finite_keys:
            for threshold in (25, 50, 80, 100):
                if len(completed) / len(self.finite_keys) >= threshold / 100:
                    self.milestones.setdefault(f"finite_{threshold}", self.day)

    def daily(self, day):
        self.day = day
        self.mark_incubation_ready()
        self.reward_budget.begin_day(day)
        self.reward_commitment.begin_day(day)
        self.expedition_budget.begin_day(day)
        if self.economy:
            self.economy.begin_day(day)
        c = self.config
        self.counters["qualifying_minutes_today"] = 0
        active = (day - 1) % 7 < c["active_days_per_week"]
        if active:
            self.active_days += 1
            self.challenge_gates.visit(self)
            self.claim_incubation()
            self.claim_expeditions()
            if c["reading_minutes"] >= ReadingRewardService.TARGET_MINUTES:
                self.award_xp(ReadingRewardService.BASE_XP, self.tags["reading"], "reading")
                self.coin_award(ReadingRewardService.BASE_COINS, "reading")
                self.event("reading_logged")
            if c["project_minutes"] > 0:
                self.counters["project_minutes"] += c["project_minutes"]
                self.counters["project_sessions"] += 1
                self.counters["project_streak"] = (
                    self.counters["project_streak"] + 1 if self.counters["project_day"] == day - 1 else 1
                )
                self.counters["project_day"] = day
                self.counters["project_best_streak"] = max(
                    self.counters["project_best_streak"], self.counters["project_streak"]
                )
                self.award_xp(round(c["project_minutes"] / 60 * 10), self.tags["project"], "project_time")
                self.coin_award(round(c["project_minutes"] / 60 * settings.COINS_PER_HOUR), "project_time")
                self.event(
                    "clock_out",
                    {"duration_minutes": c["project_minutes"]},
                    self.tags["project"],
                    drops=c["project_minutes"] >= ClockService.DROP_MINUTES_PER_DAY,
                )
            for _ in range(c["chores_per_day"]):
                self.counters["chores"] += 1
                self.award_xp(c["chore_xp"], self.tags["chores"], "chores")
                self.coin_award(c["chore_coins"], "chores")
                self.event("chore_complete", tags=self.tags["chores"])
            for habit in range(c["habits_per_day"]):
                self.habit_strength[habit] += 1
                self.counters["habits"] += 1
                self.award_xp(c["habit_xp"], self.tags["habits"], "habits")
                self.event("habit_log", tags=self.tags["habits"])
            for i in range(c["movement_sessions_per_day"]):
                self.counters["movement_sessions"] += 1
                self.counters["movement_minutes"] += c["movement_minutes"]
                eligible = i < MovementSessionService.DAILY_REWARD_LIMIT
                if eligible:
                    self.award_xp(
                        MovementSessionService.compute_xp_pool(c["movement_minutes"], c["movement_intensity"]),
                        self.tags["movement"],
                        "movement",
                    )
                self.event(
                    "movement_session",
                    {"duration_minutes": c["movement_minutes"]},
                    self.tags["movement"],
                    drops=eligible,
                    evaluate_source_badges=eligible
                    and MovementSessionService.compute_xp_pool(c["movement_minutes"], c["movement_intensity"]) > 0,
                )
            for i in range(c["creations_per_day"]):
                self.counters["creations"] += 1
                eligible = i < CreationService.DAILY_XP_LIMIT
                if eligible:
                    self.award_xp(CreationService.BASELINE_XP, self.tags["creations"], "creations")
                    self.event("creation_logged", tags=self.tags["creations"])
                else:
                    pass  # Saved entries above the cap do not invoke AwardService.
            if c["journal_per_day"]:
                self.counters["journal"] += 1
                self.counters["journal_streak"] = (
                    self.counters["journal_streak"] + 1 if self.counters["journal_day"] == day - 1 else 1
                )
                self.counters["journal_day"] = day
                self.counters["journal_best_streak"] = max(
                    self.counters["journal_best_streak"], self.counters["journal_streak"]
                )
                self.award_xp(JOURNAL_XP_POOL, self.tags["journal"], "journal")
                # Native journal XP evaluates badges before its daily Coins;
                # the game-loop hook does not evaluate them a second time.
                self.evaluate_badges(scopes=None if self.tags["journal"] else {"chronicle", "badges"})
                self.coin_award(GRATITUDE_FIRST_OF_DAY_COINS, "journal")
                self.event("journal_entry", evaluate_source_badges=False)
            self.feed_and_hatch()
            self.launch_expeditions()
            if self.economy:
                self.economy.visit(self)
        else:
            self.habit_strength = [max(0, s - 1) for s in self.habit_strength]
        self.update_progress()
        if self.economy:
            self.economy.close_day(self)
        expired = sum(
            not q.is_repeatable
            and q.pk in self.quest_windows
            and not self.quest_windows[q.pk]["paid"]
            and day >= self.quest_windows[q.pk]["start"] + q.duration_days
            for q in self.quests
        )
        self.trace.append(
            {
                "day": day,
                "active_days": self.active_days,
                "coins": self.coins,
                "total_xp": self.total_xp,
                "level": self.level,
                "inventory_units": sum(self.inventory.values()),
                "pets": len(self.pets),
                "mounts": len(self.mounts),
                "incubating_eggs": int(self.pending_incubation is not None and not self.incubation_is_ready),
                "ready_eggs": int(self.incubation_is_ready),
                "badges": len(self.badges),
                "challenge_completions": self.counters["quest_completions"],
                "expired_oneoff_challenges": expired,
                "finite_completed": len(self.completed_finite),
                "finite_remaining": len(self.finite_keys) - len(self.completed_finite),
                **{f"reward_budget_{key}": self.reward_budget.totals[key] for key in REWARD_BUDGET_METRICS},
                **self.expedition_budget.trace(self),
                **({"reward_commitment_expedition_today": self.reward_commitment.expedition_today,
                    "reward_commitment_activity_pouch_today": self.reward_commitment.activity_pouch_today,
                    **{f"reward_commitment_{key}": value for key, value in self.reward_commitment.gauges(self).items()}}
                   if self.reward_commitment.enabled else {}),
                **({
                    "coins_earned": self.economy.totals["coins_earned"],
                    "coins_exchanged": self.economy.totals["coins_exchanged"],
                    "coins_spent": self.economy.totals["coins_spent"],
                    "money_remaining_cents": self.economy.money,
                    "family_cost_cents": self.economy.totals["family_cost_cents"],
                    "purchases": self.economy.totals["purchases"],
                } if self.economy else {}),
            }
        )

    def report(self):
        return {
            "seed": self.seed,
            "milestones": self.milestones,
            "trace": self.trace,
            "sources": dict(self.source_totals),
            "sinks": dict(self.sink_totals),
            "finite_total": len(self.finite_keys),
            "finite_completed": len(self.completed_finite),
            "finite_breakdown": dict(Counter(key.split(":")[0] for key in self.finite_keys)),
            "events": self.events,
            "event_count": self.event_count,
            "longest_novelty_gap": max(self.longest_novelty_gap, self.day - self.last_novelty_day),
            "eligible_challenges": len(self.quests),
            "economy": self.economy.report() if self.economy else {"enabled": False},
            "reward_budget": self.reward_budget.report(),
            "reward_commitment": self.reward_commitment.report(self),
            "expedition_budget": self.expedition_budget.report(self),
            "challenge_gates": self.challenge_gates.report(self),
        }


def run_trial(config, catalog, seed, *, incubation_policy=None):
    trial = Trial(config, catalog, seed, incubation_policy=_capture_incubation_policy(incubation_policy))
    for day in range(1, trial.config["horizon_days"] + 1):
        trial.daily(day)
    return trial.report()


def percentile(values, fraction):
    """Nearest rank; never interpolate a fictional fractional visit day."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def describe_progression():
    policy = pet_incubation_policy()
    catalog = load_catalog()
    return {
        "schema_version": SCHEMA_VERSION,
        "pet_incubation_policy": dict(policy),
        "defaults": deepcopy(DEFAULTS),
        "limits": LIMITS,
        "economy_defaults": deepcopy(ECONOMY_DEFAULTS),
        "economy_offer_defaults": dict(OFFER_DEFAULTS),
        "economy_limits": deepcopy(ECONOMY_LIMITS),
        "reward_budget_defaults": dict(REWARD_BUDGET_DEFAULTS),
        "reward_budget_limits": deepcopy(REWARD_BUDGET_LIMITS),
        "reward_budget_sources": list(REWARD_BUDGET_SOURCES),
        "reward_commitment_defaults": dict(COMMITMENT_DEFAULTS),
        "reward_commitment_policy": deepcopy(COMMITMENT_POLICY),
        "reward_commitment_assumptions": list(COMMITMENT_ASSUMPTIONS),
        "expedition_budget_defaults": dict(EXPEDITION_BUDGET_DEFAULTS),
        "expedition_budget_limits": deepcopy(EXPEDITION_BUDGET_LIMITS),
        "expedition_budget_assumptions": list(EXPEDITION_BUDGET_ASSUMPTIONS),
        "challenge_gates_defaults": deepcopy(CHALLENGE_GATES_DEFAULTS),
        "challenge_gates_limits": deepcopy(CHALLENGE_GATES_LIMITS),
        "challenge_gates_assumptions": list(CHALLENGE_GATES_ASSUMPTIONS),
        "challenge_gate_choices": challenge_gate_choices(catalog),
        "catalog": catalog.summary(),
        "coverage": coverage(catalog),
        "audit": audit_catalog(catalog),
        "rules_fingerprint": rules_fingerprint(incubation_policy=policy),
        "engine_version": ENGINE_VERSION,
        "source_commit": getattr(settings, "SOURCE_COMMIT", "") or "unavailable",
        "work_budget": {
            "max_units": MAX_WORK_UNITS,
            "default_units": estimate_work(DEFAULTS),
            "description": "trials × (calendar days + active visits × requested daily activity/expedition sources and enabled offer/cash-policy evaluations); conservative, before catalog reads",
        },
        "presets": [
            {
                "name": "Light",
                "config": {**DEFAULTS, "active_days_per_week": 3, "chores_per_day": 1, "journal_per_day": False},
            },
            {"name": "Typical", "config": dict(DEFAULTS)},
            {
                "name": "Frequent",
                "config": {
                    **DEFAULTS,
                    "trials": 10,
                    "active_days_per_week": 7,
                    "chores_per_day": 3,
                    "movement_sessions_per_day": 1,
                    "creations_per_day": 1,
                },
            },
        ],
    }


def simulate_progression(config=None, *, catalog=None, incubation_policy=None):
    config = normalize_config(config)
    policy = _capture_incubation_policy(incubation_policy)
    catalog = load_catalog() if catalog is None else catalog
    validate_challenge_gate_catalog(config["challenge_gates"], catalog)
    runs = [run_trial(config, catalog, config["seed"] + index, incubation_policy=policy) for index in range(config["trials"])]
    milestones = []
    milestone_labels = {**MILESTONES, **({"first_purchase": "First fulfilled purchase"} if config["economy"]["enabled"] else {})}
    for key, label in milestone_labels.items():
        values = [run["milestones"][key] for run in runs if key in run["milestones"]]
        milestones.append(
            {
                "key": key,
                "label": label,
                "completion_rate": len(values) / len(runs),
                "completed_trials": len(values),
                "trials": len(runs),
                "p10_days": percentile(values, 0.10),
                "p50_days": percentile(values, 0.50),
                "p90_days": percentile(values, 0.90),
            }
        )
    trace = []
    for day in range(config["horizon_days"]):
        row = {"day": day + 1}
        for key in runs[0]["trace"][day]:
            if key != "day":
                values = [run["trace"][day][key] for run in runs]
                for suffix, quantile in (("p10", 0.10), ("p50", 0.50), ("p90", 0.90)):
                    row[f"{key}_{suffix}"] = percentile(values, quantile)
        trace.append(row)
    flows = {}
    for kind in ("sources", "sinks"):
        names = sorted({name for run in runs for name in run[kind]})
        flows[kind] = [
            {
                "source": name,
                **{
                    metric: round(sum(run[kind].get(name, {}).get(metric, 0) for run in runs) / len(runs), 2)
                    for metric in ("coins", "xp", "items")
                },
            }
            for name in names
        ]
    finite_total = runs[0]["finite_total"]
    summary = {
        "horizon_days": config["horizon_days"],
        "trials": len(runs),
        "work_units": estimate_work(config),
        "max_work_units": MAX_WORK_UNITS,
        "active_days": runs[0]["trace"][-1]["active_days"],
        "finite_content_total": finite_total,
        "finite_completed_p50": trace[-1]["finite_completed_p50"],
        "finite_remaining_p50": trace[-1]["finite_remaining_p50"],
        "completion_fraction_p50": trace[-1]["finite_completed_p50"] / finite_total if finite_total else None,
        "coins_p50": trace[-1]["coins_p50"],
        "total_xp_p50": trace[-1]["total_xp_p50"],
        "pets_p50": trace[-1]["pets_p50"],
        "mounts_p50": trace[-1]["mounts_p50"],
        "longest_novelty_gap_p50": percentile([run["longest_novelty_gap"] for run in runs], 0.5),
        "eligible_challenges": runs[0]["eligible_challenges"],
        "finite_breakdown": runs[0]["finite_breakdown"],
        "level_p50": trace[-1]["level_p50"],
        "inventory_units_p50": trace[-1]["inventory_units_p50"],
        "expired_oneoff_challenges_p50": trace[-1]["expired_oneoff_challenges_p50"],
        "percentile_basis": "Calendar days among trials completing within the horizon; completion_rate includes every trial",
    }
    audit = audit_catalog(catalog)
    if config["economy"]["enabled"]:
        audit = [row for row in audit if row["code"] != "no_coin_spending"]
        audit.append({"severity": "info", "code": "hypothetical_purchasing",
                      "message": "Purchases, wages and costs use entered synthetic assumptions. No household offers, prices, budget records or money balances are read."})
    if config["reward_budget"]["daily_coins"] is not None:
        audit.append({"severity": "info", "code": "hypothetical_reward_budget",
                      "message": "The entered daily reward envelope omits excess expedition, expedition-salvage and Coin-pouch income in this simulation only. It does not defer rewards or change live payout promises."})
    if config["reward_commitment"]["enabled"]:
        audit.append({"severity": "warning", "code": "new_commitment_experiment",
                      "message": "The fixed 100-Coin new commitment design preserves established payouts. Filtered item paths are unavailable content, not longer runway; boosts and live concurrency are outside this model."})
    if any(value is not None for value in config["expedition_budget"].values()):
        audit.append({"severity": "warning", "code": "new_expedition_budget_experiment",
                      "message": "Expedition quotas bound new launches and item promises, while preserving frozen claims. The unlimited target denominator retains the same Coin policy; excluded targets are unavailable content, not extended runway."})
    for key, label in (("first_pet", "First companion"), ("first_mount", "First grown companion")):
        rate = next(row["completion_rate"] for row in milestones if row["key"] == key)
        if rate < 0.9:
            audit.append(
                {
                    "severity": "warning",
                    "code": f"{key}_bottleneck",
                    "message": f"{label} is reached in {rate:.0%} of these trials within the horizon. Inspect ingredient supply and care policy.",
                }
            )
    audit.append(
        {
            "severity": "info",
            "code": "subset_denominator",
            "message": f"{finite_total} finite targets belong to this modeled source subset. Unmodeled badges and activities are not treated as consumed.",
        }
    )
    if summary["expired_oneoff_challenges_p50"]:
        audit.append(
            {
                "severity": "warning",
                "code": "permanent_window_expired",
                "message": f"The median trial has {summary['expired_oneoff_challenges_p50']} expired unfinished one-off challenges. These and dependent targets must not be read as future playable runway.",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "pet_incubation_policy": dict(policy),
        "config": config,
        "catalog": catalog.summary(),
        "rules_fingerprint": rules_fingerprint(incubation_policy=policy),
        "engine_version": ENGINE_VERSION,
        "source_commit": getattr(settings, "SOURCE_COMMIT", "") or "unavailable",
        "coverage": coverage(catalog),
        "milestones": milestones,
        "trace": trace,
        "summary": summary,
        "flows": flows,
        "audit": audit,
        "journey": {
            "seed": runs[0]["seed"],
            "events": runs[0]["events"],
            "event_count": runs[0]["event_count"],
            "truncated": runs[0]["event_count"] > len(runs[0]["events"]),
        },
        "economy": aggregate_economy(runs, config["economy"]),
        "reward_budget": aggregate_reward_budget(runs, config["reward_budget"]),
        "reward_commitment": aggregate_commitment(runs, config["reward_commitment"]),
        "expedition_budget": aggregate_expedition_budget(runs, config["expedition_budget"]),
        "challenge_gates": aggregate_challenge_gates(runs, config["challenge_gates"]),
    }
