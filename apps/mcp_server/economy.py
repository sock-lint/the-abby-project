"""Read-only economy inspection and bounded, anonymous projections.

No helper calls a reward writer, advances a source, rolls randomness or uses a
rollback transaction as a simulation. Projected numbers are conditional on the
explicit scenario; saved ledgers and receipts remain the accounting authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, time, timedelta
from types import SimpleNamespace

from django.conf import settings
from django.core import signing
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.achievements.models import Skill, XP_THRESHOLDS
from apps.achievements.services import SkillService
from apps.creations.services import CreationService
from apps.movement.services import MovementSessionService
from apps.quests.activity import household_timezone
from apps.reading.services import ReadingRewardService
from apps.rewards.models import CoinLedger
from apps.rpg import services as rpg
from apps.rpg.catalog_support import random_item_is_available
from apps.rpg.companion_catalog import companion_drop_weights
from apps.rpg.constants import TriggerType
from apps.rpg import rarity
from apps.rpg.models import DropTable
from apps.timecards.services import ClockService

from .errors import MCPValidationError

CURSOR_SALT = "abby.mcp.coin-ledger.v1"
MAX_AUDIT_DAYS = 366
MAX_DROP_ROWS = 5000
MAX_GOAL_RECEIPTS = 10000


def economy_rules():
    """Return current server configuration, without reading any family's state."""
    rules = {
        "schema_version": 1,
        "coins_per_hour": settings.COINS_PER_HOUR,
        "coins_per_dollar": settings.COINS_PER_DOLLAR,
        "badge_coins_by_rarity": dict(settings.COINS_PER_BADGE_RARITY),
        "birthday_coins_per_year": settings.BIRTHDAY_COINS_PER_YEAR,
        "xp_thresholds": dict(XP_THRESHOLDS),
        "check_in": {
            "base_coins": rpg.BASE_CHECK_IN_COINS,
            "streak_multiplier_per_day": rpg.STREAK_MULTIPLIER_PER_DAY,
            "multiplier_cap": rpg.STREAK_MULTIPLIER_CAP,
            "rounding": "int(base_coins * min(1 + resulting_streak * per_day, cap))",
            "limit": "First qualifying game-loop activity per day; active-day streak increments before calculation.",
            "coin_boost_applies": rpg.is_boostable_coin_reason(CoinLedger.Reason.ADJUSTMENT),
        },
        "boosts": {
            "xp_multiplier": rpg.XP_BOOST_MULTIPLIER,
            "coin_multiplier": rpg.COIN_BOOST_MULTIPLIER,
            "drop_additive": rpg.DROP_BOOST_ADDITIVE,
            "boostable_coin_reasons": sorted(str(reason) for reason in CoinLedger.Reason.values if rpg.is_boostable_coin_reason(reason)),
            "stacking": "Coin/XP boosts multiply the direct eligible pool; drop boost adds to base plus capped streak bonus. Each boost use replaces its expiry with now plus configured duration; repeated use does not multiply the multiplier again.",
        },
        "drops": {
            "base_rate_by_trigger": {str(key): value for key, value in rpg.BASE_DROP_RATES.items()},
            "streak_bonus_per_day": rpg.STREAK_DROP_BONUS_PER_DAY,
            "streak_bonus_cap": rpg.STREAK_DROP_BONUS_CAP,
            "effective_rate_cap": 1.0,
            "rarity_budgets": {"ordinary": dict(rarity.BASE_TIER_WEIGHTS), "accomplishment": dict(rarity.ACCOMPLISHMENT_TIER_WEIGHTS)},
            "accomplishment_triggers": sorted(rarity.ACCOMPLISHMENT_TRIGGERS),
            "eligibility": "Source-owned opportunity gates, fixed character level, supported acquisition policy, companion category weights, then runtime rarity-tier balancing. Anonymous previews assume no owned cosmetics. No eligible entries means no item.",
        },
        "reading": {
            "target_minutes": ReadingRewardService.TARGET_MINUTES,
            "base_xp": ReadingRewardService.BASE_XP,
            "base_coins": ReadingRewardService.BASE_COINS,
            "awards_per_day": 1,
            "required_skill": ReadingRewardService.SKILL_NAME,
        },
        "movement": {
            "rewarded_sessions_per_day": MovementSessionService.DAILY_REWARD_LIMIT,
            "xp_per_ten_minutes": MovementSessionService.XP_PER_10_MIN,
            "maximum_minutes_per_session": MovementSessionService.MAX_DURATION_MINUTES,
            "intensity_multipliers": dict(MovementSessionService.INTENSITY_MULTIPLIER),
        },
        "creations": {
            "rewarded_creations_per_day": CreationService.DAILY_XP_LIMIT,
            "base_xp": CreationService.BASELINE_XP,
            "primary_weight": CreationService.PRIMARY_WEIGHT,
            "secondary_weight": CreationService.SECONDARY_WEIGHT,
        },
        "xp_distribution": "SkillService._iter_tagged_xp rounds each weighted share using Python round; no tags means no direct XP. Sum of rounded shares may differ from the input pool.",
        "preview_supported_sources": ["reading", "movement", "creations", "approved_chores", "explicit_one_off_project", "explicit_one_off_milestone", "explicit_one_off_tracked_work", "explicit_conditional_automatic_challenge"],
        "one_off_inputs": {
            "reward_amounts": "Supplied scenario assumptions, not derived from a real project, saved goal or monetary bonus. Amounts then use actual reason-specific boosts and the shared tagged-XP split.",
            "milestone_xp": "Supplied direct credited XP total, without Scholar boost; the completion signal bypasses AwardService XP multiplication.",
            "automatic_goal": "Supplied hypothetical completed occurrence reward. Coins use non-boostable adjustment; tagged XP honors Scholar boost. Does not create another activity, check-in or drop opportunity.",
            "tracked_work_drop_minimum_daily_minutes": ClockService.DROP_MINUTES_PER_DAY,
            "tracked_work_drop_rolls_per_day": 1,
            "once_only": "Unique source keys and already_rewarded flags model permanent receipts, not repeated rewards for the same source.",
        },
        "source_references": [
            "config.settings", "apps.rpg.services", "apps.achievements.services.SkillService._iter_tagged_xp",
            "apps.reading.services.ReadingRewardService", "apps.movement.services.MovementSessionService.compute_xp_pool",
            "apps.creations.services.CreationService", "apps.chores.services.ChoreService.approve_completion",
        ],
    }
    rules["rules_fingerprint"] = hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()
    return rules


def date_window(user, since=None, until=None, *, default_period=False):
    zone = household_timezone(user)
    if default_period:
        until = until or timezone.localdate(timezone=zone)
        since = since or until - timedelta(days=29)
    if since and until and (until < since or (until - since).days >= MAX_AUDIT_DAYS):
        raise MCPValidationError("Use an ordered period of at most 366 inclusive family-local days.")
    try:
        start = datetime.combine(since, time.min, tzinfo=zone) if since else None
        end = datetime.combine(until + timedelta(days=1), time.min, tzinfo=zone) if until else None
    except (OverflowError, ValueError):
        raise MCPValidationError("The supplied date cannot form a bounded local-day interval.") from None
    return {
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "timezone": str(zone), "starts_at": start, "ends_before": end,
    }


def filter_window(queryset, field, window):
    if window["starts_at"] is not None:
        queryset = queryset.filter(**{f"{field}__gte": window["starts_at"]})
    if window["ends_before"] is not None:
        queryset = queryset.filter(**{f"{field}__lt": window["ends_before"]})
    return queryset


def period_payload(window):
    return {key: value.isoformat() if isinstance(value, datetime) else value for key, value in window.items()}


def coin_ledger_page(target, params):
    window = date_window(target, params.since, params.until)
    if params.reason is not None and params.reason not in CoinLedger.Reason.values:
        raise MCPValidationError("Unknown CoinLedger reason.")
    binding = {
        "user_id": target.pk, "family_id": target.family_id,
        "since": window["since"], "until": window["until"],
        "timezone": window["timezone"], "reason": params.reason,
    }
    all_entries = CoinLedger.objects.filter(user=target)
    before = None
    if params.cursor:
        try:
            payload = signing.loads(params.cursor, salt=CURSOR_SALT, max_age=86400)
            if not isinstance(payload, dict) or payload.get("binding") != binding:
                raise ValueError
            maximum_id = payload["maximum_id"]
            before = parse_datetime(payload["before_time"])
            before_id = payload["before_id"]
            if type(maximum_id) is not int or type(before_id) is not int or before is None or timezone.is_naive(before):
                raise ValueError
        except (signing.BadSignature, TypeError, ValueError, KeyError):
            raise MCPValidationError("Invalid, expired or differently scoped ledger cursor.") from None
    else:
        maximum_id = all_entries.aggregate(value=Max("pk"))["value"] or 0
    queryset = filter_window(all_entries.filter(pk__lte=maximum_id), "created_at", window)
    if params.reason:
        queryset = queryset.filter(reason=params.reason)
    if before:
        queryset = queryset.filter(Q(created_at__lt=before) | Q(created_at=before, pk__lt=before_id))
    rows = list(queryset.order_by("-created_at", "-pk")[: params.limit + 1])
    more = len(rows) > params.limit
    rows = rows[:params.limit]
    next_cursor = None
    if more:
        last = rows[-1]
        next_cursor = signing.dumps({
            "binding": binding, "maximum_id": maximum_id,
            "before_time": last.created_at.isoformat(), "before_id": last.pk,
        }, salt=CURSOR_SALT, compress=True)
    return {
        "user_id": target.pk, "period": period_payload(window), "snapshot_max_id": maximum_id,
        "entries": [{
            "id": entry.pk, "amount": entry.amount, "reason": entry.reason,
            "created_at": entry.created_at.isoformat(), "created_by_id": entry.created_by_id,
            "redemption_id": entry.redemption_id,
        } for entry in rows],
        "next_cursor": next_cursor,
        "description_policy": "Free-text descriptions are omitted; use amounts, typed reasons and receipt links for accounting.",
    }


def _guard_summary(queryset):
    values = queryset.aggregate(total=Count("pk"), historical=Count("pk", filter=Q(historical=True)))
    return {"new_guards": values["total"] - values["historical"], "historical_guards_recorded": values["historical"]}


def receipt_summary(target, window):
    from apps.projects.models import ProjectCompletionRewardReceipt, MilestoneCompletionRewardReceipt
    from apps.quests.models import ChallengeOccurrence, DailyBonus
    from apps.reading.models import ReadingDailyReward
    from apps.rpg.models import PerfectDayReceipt

    reading = filter_window(ReadingDailyReward.objects.filter(user=target, awarded_at__isnull=False), "awarded_at", window)
    bonus = filter_window(DailyBonus.objects.filter(user=target, awarded_at__isnull=False), "awarded_at", window)
    goals = filter_window(ChallengeOccurrence.objects.filter(goal__user=target, awarded_at__isnull=False), "awarded_at", window)
    goal_count = goals.count()
    goal_totals = {"coins_recorded": 0, "xp_recorded": 0, "invalid_receipts": 0}
    for receipt in goals.order_by("pk").values_list("reward_receipt", flat=True)[:MAX_GOAL_RECEIPTS]:
        if not isinstance(receipt, dict) or any(type(receipt.get(key)) is not int or receipt[key] < 0 for key in ("coins", "xp")):
            goal_totals["invalid_receipts"] += 1
            continue
        goal_totals["coins_recorded"] += receipt["coins"]
        goal_totals["xp_recorded"] += receipt["xp"]
    incomplete = goal_count > MAX_GOAL_RECEIPTS or goal_totals["invalid_receipts"] > 0
    if incomplete:
        goal_totals["coins_recorded"] = None
        goal_totals["xp_recorded"] = None
    return {
        "reading": reading.aggregate(count=Count("pk"), coins_recorded=Sum("coins_awarded", default=0), xp_recorded=Sum("xp_awarded", default=0)),
        "daily_bonus": bonus.aggregate(count=Count("pk"), coins_recorded=Sum("coins_awarded", default=0), xp_recorded=Sum("xp_awarded", default=0)),
        "automatic_goals": {"count": goal_count, **goal_totals, "incomplete": incomplete, "scan_limit": MAX_GOAL_RECEIPTS},
        "project_completion_guards": _guard_summary(filter_window(ProjectCompletionRewardReceipt.objects.filter(user=target), "created_at", window)),
        "milestone_completion_guards": _guard_summary(filter_window(MilestoneCompletionRewardReceipt.objects.filter(user=target), "created_at", window)),
        "perfect_day_guards": _guard_summary(filter_window(PerfectDayReceipt.objects.filter(user=target), "created_at", window)),
        "interpretation": "Receipt amounts overlap ledger credits and must not be added to them. Guard-only receipts contain no historic award amounts; historical backfills do not prove payouts in this period. This is not a complete all-source XP ledger or a proof of one-to-one reconciliation.",
    }


def economy_audit(target, since=None, until=None):
    window = date_window(target, since, until, default_period=True)
    maximum_id = CoinLedger.objects.filter(user=target).aggregate(value=Max("pk"))["value"] or 0
    ledger = CoinLedger.objects.filter(user=target, pk__lte=maximum_id)
    entries = filter_window(ledger, "created_at", window)
    grouped = list(entries.values("reason").annotate(
        entries=Count("pk"), credits=Sum("amount", filter=Q(amount__gt=0), default=0),
        signed_debits=Sum("amount", filter=Q(amount__lt=0), default=0), net=Sum("amount", default=0),
    ).order_by("reason"))
    by_reason = {row["reason"]: {"entries": row["entries"], "credits": row["credits"], "debits": -row["signed_debits"], "net": row["net"]} for row in grouped}
    credits = sum(row["credits"] for row in grouped)
    debits = -sum(row["signed_debits"] for row in grouped)
    excluded = {CoinLedger.Reason.ADJUSTMENT, CoinLedger.Reason.REFUND, CoinLedger.Reason.EXCHANGE, CoinLedger.Reason.REDEMPTION}
    earn_reasons = set(CoinLedger.Reason.values) - excluded
    opening = ledger.filter(created_at__lt=window["starts_at"]).aggregate(total=Sum("amount", default=0))["total"]
    return {
        "user_id": target.pk, "period": period_payload(window), "snapshot_max_id": maximum_id,
        "ledger": {
            "opening_balance": opening, "credits": credits, "debits": debits,
            "net_change": credits - debits, "closing_balance": opening + credits - debits,
            "earned_coins": sum(row["credits"] for row in grouped if row["reason"] in earn_reasons),
            "other_credits": sum(row["credits"] for row in grouped if row["reason"] not in set(CoinLedger.Reason.values) or row["reason"] == CoinLedger.Reason.REDEMPTION),
            "refund_credits": by_reason.get("refund", {}).get("credits", 0),
            "exchange_credits": by_reason.get("exchange", {}).get("credits", 0),
            "adjustment_credits": by_reason.get("adjustment", {}).get("credits", 0),
            "redemption_debits": by_reason.get("redemption", {}).get("debits", 0),
            "adjustment_debits": by_reason.get("adjustment", {}).get("debits", 0),
            "by_reason": by_reason,
        },
        "receipts": receipt_summary(target, window),
        "accounting_notes": [
            "Amounts are persisted CoinLedger amounts, including applied boosts; ActivityEvent deltas are not summed.",
            "earned_coins includes only known earn reasons, excluding refund, exchange, adjustment and redemption credits; unknown positive reasons are other_credits. Adjustment mixes check-ins, challenge rewards, salvage and manual grants; its credits are separate and cannot be classified from free text.",
            "Debits include all negative ledger rows; redemption_debits separately identifies reward spending. A debit and later refund both remain visible.",
            "Ledger snapshot_max_id is an ID ceiling for new rows, not a repeatable-read database snapshot; receipt observations can change concurrently.",
            "Bounds use the target family's current timezone, with an inclusive end date and exclusive next local midnight; this does not reconstruct earlier timezone settings.",
        ],
    }


def _distributed_xp(pool, weights, boosted):
    if any(type(weight) is not int or weight < 1 or weight > 10000 for weight in weights):
        raise MCPValidationError("Anonymous XP weights must be integers between 1 and 10000.")
    total = int(pool * (rpg.XP_BOOST_MULTIPLIER if boosted else 1.0))
    tags = [SimpleNamespace(skill=index, xp_weight=weight) for index, weight in enumerate(weights)]
    return sum(value for _, value in SkillService._iter_tagged_xp(tags, total))


def _direct_coins(base, reason, boosted):
    multiplier = rpg.COIN_BOOST_MULTIPLIER if boosted and rpg.is_boostable_coin_reason(reason) else 1.0
    return int(base * multiplier)


def _drop_pools(level, triggers):
    queryset = DropTable.objects.filter(trigger_type__in=triggers, min_level__lte=level).select_related("item", "item__pet_species", "item__potion_type").order_by("pk")
    entries = list(queryset[:MAX_DROP_ROWS + 1])
    if len(entries) > MAX_DROP_ROWS:
        raise MCPValidationError("The eligible drop catalog exceeds the bounded preview limit of 5000 rows.")
    pools = {}
    for trigger in sorted(triggers):
        authored = [entry for entry in entries if entry.trigger_type == trigger]
        eligible = [entry for entry in authored if random_item_is_available(entry.item)]
        budgets = rarity.ACCOMPLISHMENT_TIER_WEIGHTS if trigger in rarity.ACCOMPLISHMENT_TRIGGERS else rarity.BASE_TIER_WEIGHTS
        weights = rarity.tier_balanced_weights(eligible, budgets, authored_weights=companion_drop_weights(eligible))
        if any(not math.isfinite(float(weight)) or weight < 0 for weight in weights):
            raise MCPValidationError("The drop catalog contains invalid effective weights.")
        total = sum(weights)
        if eligible and total <= 0:
            raise MCPValidationError("An eligible drop pool has no positive effective selection weight.")
        outcomes = []
        if total > 0:
            for entry, weight in zip(eligible, weights):
                if weight > 0:
                    outcomes.append({"item_slug": entry.item.slug, "conditional_probability": weight / total})
        pools[trigger] = {"authored_level_eligible_rows": len(authored), "unsupported_rows_excluded": len(authored) - len(eligible), "outcomes": outcomes}
    return pools


def _scenario_projection(scenario):
    reading = scenario.reading_minutes_per_day >= ReadingRewardService.TARGET_MINUTES
    reading_skill = Skill.objects.filter(name=ReadingRewardService.SKILL_NAME, category__name="Language Arts").exists()
    movement = scenario.movement_sessions_per_day[:MovementSessionService.DAILY_REWARD_LIMIT]
    creation_count = min(scenario.creations_per_day, CreationService.DAILY_XP_LIMIT)
    creation_weights = [CreationService.PRIMARY_WEIGHT, CreationService.SECONDARY_WEIGHT] if scenario.creation_secondary_skill else [1]
    # Validate even capped-out submitted rows, rather than silently hiding invalid assumptions.
    for session in scenario.movement_sessions_per_day:
        _distributed_xp(0, session.xp_weights, False)
    direct = []
    if reading:
        direct.append({"source": "reading", "count": 1, "coins": _direct_coins(ReadingRewardService.BASE_COINS, CoinLedger.Reason.READING, scenario.coin_boost), "xp": _distributed_xp(ReadingRewardService.BASE_XP, [1] if reading_skill else [], scenario.xp_boost), "trigger": str(TriggerType.READING_LOGGED)})
    for session in movement:
        direct.append({"source": "movement", "count": 1, "coins": 0, "xp": _distributed_xp(MovementSessionService.compute_xp_pool(session.duration_minutes, session.intensity), session.xp_weights, scenario.xp_boost), "trigger": str(TriggerType.MOVEMENT_SESSION)})
    if creation_count:
        direct.append({"source": "creations", "count": creation_count, "coins": 0, "xp": _distributed_xp(CreationService.BASELINE_XP, creation_weights, scenario.xp_boost), "trigger": str(TriggerType.CREATION_LOGGED)})
    for chore in scenario.chores_per_day:
        direct.append({"source": "approved_chores", "count": chore.count, "coins": _direct_coins(chore.coin_reward, CoinLedger.Reason.CHORE_REWARD, scenario.coin_boost), "xp": _distributed_xp(chore.xp_reward, chore.xp_weights, scenario.xp_boost), "trigger": str(TriggerType.CHORE_COMPLETE)})
    one_off = []
    reasons = {"project": CoinLedger.Reason.PROJECT_BONUS, "milestone": CoinLedger.Reason.MILESTONE_BONUS, "tracked_work": CoinLedger.Reason.HOURLY, "automatic_challenge": CoinLedger.Reason.ADJUSTMENT}
    source_triggers = {"project": str(TriggerType.PROJECT_COMPLETE), "milestone": str(TriggerType.MILESTONE_COMPLETE), "tracked_work": str(TriggerType.CLOCK_OUT), "automatic_challenge": None}
    for award in scenario.one_off_awards:
        xp = award.xp_reward if award.kind == "milestone" else _distributed_xp(award.xp_reward, award.xp_weights, scenario.xp_boost)
        one_off.append({
            "source_key": award.source_key, "kind": award.kind, "day": award.day,
            "coins": 0 if award.already_rewarded else _direct_coins(award.coin_reward, reasons[award.kind], scenario.coin_boost),
            "xp": 0 if award.already_rewarded else xp,
            "trigger": None if award.already_rewarded else source_triggers[award.kind],
            "duration_minutes": award.duration_minutes,
            "qualifying_source_key": award.qualifying_source_key,
            "already_rewarded": award.already_rewarded,
            "amount_basis": "Explicit hypothetical supplied reward, not a lookup or a computed project/goal award.",
        })
    triggers = {row["trigger"] for row in [*direct, *one_off] if row["trigger"] is not None}
    pools = _drop_pools(scenario.character_level, triggers)
    drop_totals = defaultdict(float)
    opportunities = defaultdict(int)
    item_totals = defaultdict(float)
    recurring_coins = sum(row["coins"] * row["count"] for row in direct)
    recurring_xp = sum(row["xp"] * row["count"] for row in direct)
    daily = []
    balance = scenario.initial_coins
    affordable_day = 0 if scenario.target_cost_coins is not None and balance >= scenario.target_cost_coins else None
    resulting_streak = scenario.starting_streak
    last_active_day = 0 if scenario.starting_streak else None
    for day in range(1, scenario.days + 1):
        awards_today = [row for row in one_off if row["day"] == day]
        sources_today = [row for row in awards_today if row["trigger"] is not None]
        active = bool(direct or sources_today)
        if active:
            resulting_streak = resulting_streak + 1 if last_active_day == day - 1 else 1
            last_active_day = day
        check_in = int(rpg.BASE_CHECK_IN_COINS * min(1 + resulting_streak * rpg.STREAK_MULTIPLIER_PER_DAY, rpg.STREAK_MULTIPLIER_CAP)) if active else 0
        direct_coins = recurring_coins + sum(row["coins"] for row in awards_today)
        direct_xp = recurring_xp + sum(row["xp"] for row in awards_today)
        balance += direct_coins + check_in
        daily.append({"day": day, "resulting_streak": resulting_streak, "direct_coins": direct_coins, "check_in_coins": check_in, "distributed_xp": direct_xp, "projected_balance": balance, "one_off_award_count": len([row for row in awards_today if not row["already_rewarded"]]), "game_loop_activity_count": sum(row["count"] for row in direct) + len(sources_today)})
        if affordable_day is None and scenario.target_cost_coins is not None and balance >= scenario.target_cost_coins:
            affordable_day = day
        roll_counts = defaultdict(int)
        for source in direct:
            roll_counts[source["trigger"]] += source["count"]
        for source in sources_today:
            if source["kind"] != "tracked_work":
                roll_counts[source["trigger"]] += 1
        tracked_minutes = sum(row["duration_minutes"] for row in sources_today if row["kind"] == "tracked_work")
        if tracked_minutes >= ClockService.DROP_MINUTES_PER_DAY:
            roll_counts[str(TriggerType.CLOCK_OUT)] = 1
        for trigger, count in roll_counts.items():
            opportunities[trigger] += count
            effective = min(rpg.BASE_DROP_RATES.get(trigger, 0.20) + min(resulting_streak * rpg.STREAK_DROP_BONUS_PER_DAY, rpg.STREAK_DROP_BONUS_CAP) + (rpg.DROP_BOOST_ADDITIVE if scenario.drop_boost else 0), 1.0)
            if pools[trigger]["outcomes"]:
                expected = effective * count
                drop_totals[trigger] += expected
                for outcome in pools[trigger]["outcomes"]:
                    item_totals[(trigger, outcome["item_slug"])] += expected * outcome["conditional_probability"]

    weekly = [{
        "starts_day": block[0]["day"], "ends_day": block[-1]["day"],
        "coins": sum(row["direct_coins"] + row["check_in_coins"] for row in block),
        "distributed_xp": sum(row["distributed_xp"] for row in block),
    } for offset in range(0, len(daily), 7) if (block := daily[offset:offset + 7])]
    return {
        "label": scenario.label, "days": scenario.days, "daily": daily, "weekly_totals": weekly,
        "catalog_fingerprint": hashlib.sha256(json.dumps(pools, sort_keys=True).encode()).hexdigest(),
        "total_projected_coins": balance - scenario.initial_coins,
        "total_distributed_xp": sum(day["distributed_xp"] for day in daily), "projected_balance": balance,
        "time_to_afford": {"target_cost_coins": scenario.target_cost_coins, "day": affordable_day, "within_horizon": (affordable_day is not None) if scenario.target_cost_coins is not None else None, "basis": "Direct, explicitly assumed conditional payouts and check-in Coins only; no predicted drop liquidation or unsupplied conditional rewards."},
        "source_rewards_per_day": direct, "one_off_assumed_rewards": one_off,
        "caps": {"movement_rewarded": len(movement), "movement_skipped": len(scenario.movement_sessions_per_day) - len(movement), "creations_rewarded": creation_count, "creations_skipped": scenario.creations_per_day - creation_count, "reading_rewarded": reading},
        "reading_skill_available": reading_skill,
        "drop_expected_value": {"meaning": "Expected item units, not guaranteed awards or spendable Coins; fixed level and no ownership-dependent salvage.", "expected_item_units": round(sum(drop_totals.values()), 6), "by_trigger": [{"trigger": trigger, "roll_opportunities": opportunities[trigger], "expected_item_units": round(drop_totals[trigger], 6), **{key: value for key, value in pool.items() if key != "outcomes"}} for trigger, pool in sorted(pools.items())], "by_item": [{"trigger": trigger, "item_slug": slug, "expected_units": round(value, 6)} for (trigger, slug), value in sorted(item_totals.items())[:100]], "item_rows_truncated": len(item_totals) > 100},
    }


def preview_scenarios(scenarios):
    rules = economy_rules()
    results = [_scenario_projection(scenario) for scenario in scenarios]
    return {
        "rules_fingerprint": rules["rules_fingerprint"], "scenarios": results,
        "assumptions": [
            "Anonymous recurring plans repeat each modeled day, starting with no same-day claimed rewards. One-off project, milestone, tracked-work and conditional goal rewards occur only on their selected days with explicit assumed amounts. Replayed receipts pay nothing; no account is read or selected.",
            "Selected boosts remain active throughout the horizon. XP/coin multipliers do not stack with themselves; check-in adjustments are not Lucky Coin eligible.",
            "starting_streak assumes activity yesterday. An inactive modeled day breaks the streak before the next qualifying activity; fixed character level determines every drop pool. XP does not change drop eligibility in this preview.",
            "Reading requires genuinely new present-day minutes. Reading XP requires the existing Reading Comprehension skill. Creations assume valid selected creative skills; movement/chore XP assumes valid skills with the supplied anonymous weights.",
            "All successful source and game-loop steps complete. Drop expectations use current supported catalog eligibility, companion category weights and runtime rarity budgets; no owned cosmetics or RNG is executed.",
        ],
        "conditional_rewards_excluded": [
            "Badges, unsupplied modern goal rewards, daily bonuses, legacy quests, perfect-day completion, companion growth/expeditions, creation parent bonuses, birthdays, purchases, exchanges, consumable use and ownership-dependent salvage. A supplied automatic challenge is an assumed conditional payout, not evaluated goal progress.",
            "Project difficulty/bounty formulas, milestone monetary bonuses and tracked-work hourly Coin/XP calculation are not automatically recomputed. Their one-off base amounts are explicit user assumptions; homework and habit rewards are excluded. Milestone XP is an assumed already-distributed total and is not XP-boosted.",
            "Drop values are expected item quantities only. No market price, Coin payout or guaranteed time-to-acquire is inferred from item rarity or coin_value.",
        ],
        "comparison": {"baseline_label": results[0]["label"], "differences_from_first": [{"label": row["label"], "coins": row["total_projected_coins"] - results[0]["total_projected_coins"], "distributed_xp": row["total_distributed_xp"] - results[0]["total_distributed_xp"], "expected_item_units": round(row["drop_expected_value"]["expected_item_units"] - results[0]["drop_expected_value"]["expected_item_units"], 6)} for row in results[1:]]},
    }
