"""Bounded, same-family accounting observations; never a reward experiment.

The anonymous Lab has no user selector. This separate read surface observes
persisted ledger amounts for the caller's active child cohort, with explicit
coverage and denominators. It reads no journals or free-text descriptions.
"""
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.families.models import LiveTestFamily
from apps.families.queries import children_in
from apps.quests.activity import household_timezone
from apps.rewards.availability import reward_is_available
from apps.rewards.models import CoinLedger, Reward
from apps.rpg.catalog_support import preload_legacy_references

from .observation_activity import ActivityCapacityExceeded, meaningful_activity_days


MAX_COHORT_CHILDREN = 100
MAX_LEDGER_ROWS = 100_000
MAX_ACTIVITY_ROWS = 100_000
MAX_SHOP_REWARDS = 200
WINDOW_DAYS = 30
AUTOMATIC_SOURCES = (
    CoinLedger.Source.EXPEDITION,
    CoinLedger.Source.EXPEDITION_SALVAGE,
    CoinLedger.Source.COIN_POUCH,
)
NOTES = [
    "Observed amounts use the installed uncapped economy. The 100-Coin Lab hypothesis is not live and these observations cannot validate an undeployed policy.",
    "The cohort contains all currently active, nonstaff children in your family registered by the period's end. Trusted provisioned test families are excluded.",
    "Ledger-active children and child-days count any persisted Coin transaction. They are not an engagement or retention measure and do not count visits without a Coin transaction.",
    "Eligible child-days count calendar days from registration or the start of the period, whichever is later; no transaction is required. Account activity and family membership are their current values, not reconstructed historical states.",
    "Meaningful child-days count surviving selected reading, movement, creation, positive habit, completed positive work-session, homework submission and chore submission records, including activities that earn no Coins. They exclude visits, private writing, assignments, savings events, expeditions and reward cascades. This is a selected saved-work measure, not complete app engagement or proof of who entered a child's work.",
    "Reading, movement and creation use their saved work dates. Habits, work-session closes and chore/homework submissions use the family's current local date of the saved timestamp; an approval does not create another active day. Corrections and removal change this work history without changing reward receipts.",
    "Typed attribution identifies new adjustment awards. Blank historical adjustments remain unknown; their text and receipt subtotals are never used to guess a source or reconstruct past payouts.",
    "Daily acknowledgments and bonuses share one accounting bucket, without identifying a private writing action or adding private work to meaningful-day counts.",
    "Automatic-source totals are a measured lower bound when attribution is incomplete. Child-days over 100 compare credited typed-source amounts within the current family calendar, not launch-day commitments or withheld rewards.",
    "Amounts are actual CoinLedger entries including applied boosts. Refunds and exchanges stay separate by reason; no activity-log deltas or receipt subtotals are added to the ledger.",
    "All dates use the family's current timezone, with an inclusive last date and exclusive next local midnight. This does not reconstruct past timezone settings. An ID ceiling excludes later inserts but is not a repeatable-read database snapshot.",
    "Earning pace divides identified recurring Coin credits in the period by meaningful child-days in that same period. Credits may arrive on a later approval or expedition day. Occasional bonuses, exchanges, refunds, manual grants and unknown adjustments are excluded. Actual boosts and old promised payouts remain in their recorded amounts; this is not an unboosted or future-policy forecast.",
    "Shop estimates round up the full current offer price at the observed family earning pace, starting from zero and assuming all those earnings are saved. Existing balances, spending, promised redemption prices and other purchases do not change the estimate. A stocked offer is not a delivery guarantee; an estimate with fewer than seven meaningful child-days is provisional.",
    "Observations available means selected work or ledger evidence exists, not that sample size is sufficient to approve an economy or predict retention. Unknown attribution makes the identified earning pace incomplete. No family-cost or purchase-timing guarantee is inferred.",
]


# Adjustment is shared by many unrelated writers. Only explicit server-owned
# source tags distinguish them; descriptions and receipt amounts are not proof.
ADJUSTMENT_SOURCES = {
    "expedition_salvage": ("Expedition cosmetic salvage", "recurring"),
    "coin_pouch": ("Coin pouches", "recurring"),
    "daily_check_in": ("Daily activity check-ins", "recurring"),
    "perfect_day": ("Perfect Days", "recurring"),
    "writing": ("Daily writing acknowledgment", "recurring"),
    "cosmetic_salvage": ("Random cosmetic salvage", "recurring"),
    "consumable_salvage": ("Consumable salvage", "recurring"),
    "automatic_challenge": ("Automatic challenge rewards", "occasional"),
    "legacy_quest": ("Legacy quest rewards", "occasional"),
    "savings": ("Savings milestones", "occasional"),
    "birthday": ("Birthday gifts", "occasional"),
    "manual_grant": ("Parent grants", "manual"),
}
REASON_SOURCES = {
    CoinLedger.Reason.HOURLY: ("Tracked project work", "recurring"),
    CoinLedger.Reason.CHORE_REWARD: ("Chores", "recurring"),
    CoinLedger.Reason.READING: ("Reading Adventures", "recurring"),
    CoinLedger.Reason.DAILY_CHALLENGE: ("Daily challenges", "recurring"),
    CoinLedger.Reason.EXPEDITION: ("Expedition returns", "recurring"),
    CoinLedger.Reason.PROJECT_BONUS: ("Project completion bonuses", "occasional"),
    CoinLedger.Reason.BOUNTY_BONUS: ("Bounty bonuses", "occasional"),
    CoinLedger.Reason.MILESTONE_BONUS: ("Milestone bonuses", "occasional"),
    CoinLedger.Reason.BADGE_BONUS: ("Badge bonuses", "occasional"),
    CoinLedger.Reason.EXCHANGE: ("Money exchanged for Coins", "transfer"),
    CoinLedger.Reason.REFUND: ("Refunds", "refund"),
}
DAILY_ACTIVITY_SOURCES = {"daily_check_in", "perfect_day", "writing", CoinLedger.Reason.DAILY_CHALLENGE}


def _earning_sources(entries):
    totals = {}
    groups = entries.filter(amount__gt=0).order_by().values("reason", "source").annotate(
        coins=Sum("amount"), entries=Count("pk"),
    )
    for row in groups:
        reason, source = row["reason"], row["source"]
        if reason == CoinLedger.Reason.ADJUSTMENT and source in ADJUSTMENT_SOURCES:
            key, (label, kind) = source, ADJUSTMENT_SOURCES[source]
        elif reason in REASON_SOURCES and (
            (reason == CoinLedger.Reason.EXPEDITION and source == CoinLedger.Source.EXPEDITION)
            or (reason != CoinLedger.Reason.EXPEDITION and not source)
        ):
            key, (label, kind) = reason, REASON_SOURCES[reason]
        else:
            key, label, kind = "unattributed", "Unattributed credits", "unattributed"
        if key in DAILY_ACTIVITY_SOURCES:
            key, label = "daily_activity", "Daily activity bonuses"
        summary = totals.setdefault(key, {"key": key, "label": label, "kind": kind, "coins": 0, "entries": 0})
        summary["coins"] += row["coins"]
        summary["entries"] += row["entries"]
    return [totals[key] for key in sorted(totals)]


def _add_earning_estimates(result, sources, meaningful_days):
    credits = result["ledger"]["credits"]
    recurring = sum(row["coins"] for row in sources if row["kind"] == "recurring")
    available = meaningful_days > 0 and recurring > 0
    result["earning_sources"] = sources
    result["earning_pace"] = {
        "status": "available" if available else "insufficient_evidence",
        "recurring_coins": recurring, "active_child_days": meaningful_days,
        "coins_per_active_day": recurring / meaningful_days if available else None,
        "excluded_credits": credits - recurring,
        "attribution_complete": credits > 0 and not any(row["kind"] == "unattributed" for row in sources),
        "provisional": meaningful_days < 7,
    }
    if available:
        for reward in result["shop_rewards"]:
            # Integer ceiling avoids an overstated/understated day at a
            # floating-point boundary. Balances and saved requests are absent.
            numerator = reward["cost_coins"] * meaningful_days
            if reward["catalog_available"]:
                reward["days_to_earn"] = (numerator + recurring - 1) // recurring


def _legacy_catalog_references(model, keys):
    """Batch the same exact legacy lookups used by the availability policy."""
    keys = sorted({key.strip() for key in keys if isinstance(key, str) and key.strip()})
    rows = {}
    for start in range(0, len(keys), 50):
        batch = keys[start:start + 50]
        names = Q()
        for key in batch:
            names |= Q(name__iexact=key)
        for row in model.objects.filter(Q(slug__in=batch) | names).only("pk", "name", "slug", "sprite_key"):
            rows[row.pk] = row
    return preload_legacy_references(model, rows.values(), keys)


def _shop_reward_rows(offers):
    """Use the real acquisition policy without querying once per legacy egg."""
    from apps.pets.models import PetSpecies, PotionType

    items = [reward.item_definition for reward in offers if reward.item_definition_id is not None]
    metadata = [item.metadata for item in items if isinstance(item.metadata, dict)]
    species = _legacy_catalog_references(PetSpecies, [row.get("species") for row in metadata])
    potions = _legacy_catalog_references(PotionType, [row.get("variant") for row in metadata])
    return [
        {"reward_id": reward.pk, "name": reward.name, "cost_coins": reward.cost_coins,
         "stock": reward.stock, "days_to_earn": None,
         "catalog_available": reward_is_available(reward, legacy_species=species, legacy_potions=potions)}
        for reward in offers
    ]


def _authorized_actor(actor):
    # The API also authenticates, but callers of this service cannot rely on a
    # stale actor object after deactivation, role or household changes.
    current = User.objects.select_related("family").filter(
        pk=getattr(actor, "pk", None), family_id=getattr(actor, "family_id", None),
        is_active=True, is_staff=True, role=User.Role.PARENT,
    ).first()
    if current is None:
        raise PermissionDenied("Active staff parents only.")
    return current


def _period(actor, since, until):
    zone = household_timezone(actor)
    today = timezone.localdate(timezone.now(), timezone=zone)
    if any(value is not None and type(value) is not date for value in (since, until)):
        raise ValueError("Observation dates must be calendar dates.")
    try:
        until = until or today
        since = since or until - timedelta(days=WINDOW_DAYS - 1)
        if until > today or until < since or (until - since).days >= WINDOW_DAYS:
            raise ValueError("Use an ordered period of at most 30 inclusive days ending no later than today.")
        starts_at = datetime.combine(since, time.min, tzinfo=zone)
        ends_before = datetime.combine(until + timedelta(days=1), time.min, tzinfo=zone)
    except OverflowError:
        raise ValueError("Observation dates cannot form a bounded local-day interval.") from None
    return since, until, zone, starts_at, ends_before


def _empty_result(since, until, zone, starts_at, ends_before, observer_excluded, child_count):
    return {
        "schema_version": 1,
        "status": "insufficient_evidence",
        "period": {"since": since.isoformat(), "until": until.isoformat(), "timezone": str(zone),
                   "starts_at": starts_at.isoformat(), "ends_before": ends_before.isoformat()},
        "cohort": {"registered_within_days": None, "scope": "active_family_children", "eligible_children": child_count,
                   "eligible_child_days": 0, "max_children": MAX_COHORT_CHILDREN,
                   "truncated": False, "observer_family_excluded": observer_excluded},
        "activity": {"ledger_active_children": 0, "ledger_active_child_days": 0,
                     "meaningful_active_children": 0, "meaningful_active_child_days": 0},
        "ledger": {"opening_balance": 0, "credits": 0, "debits": 0, "net_change": 0,
                   "closing_balance": 0, "by_reason": {}},
        "automatic_sources": {
            "coins": 0, "by_source": {str(source): 0 for source in AUTOMATIC_SOURCES},
            "unattributed_positive_adjustments": 0, "unattributed_expedition_coins": 0,
            "attribution_complete": False, "child_days_over_100": 0,
        },
        "policy": {"installed_daily_automatic_coin_cap": None, "selected_lab_daily_coins": 100,
                   "is_live_experiment": False, "coins_per_dollar": settings.COINS_PER_DOLLAR},
        "earning_sources": [],
        "earning_pace": {"status": "insufficient_evidence", "recurring_coins": 0, "active_child_days": 0,
                         "coins_per_active_day": None, "excluded_credits": 0,
                         "attribution_complete": False, "provisional": True},
        "shop_rewards": [],
        "notes": list(NOTES),
    }


def _limit_result(result, status):
    # Capacity failures are not zero-activity observations or partial samples.
    result["status"] = status
    result["cohort"]["truncated"] = True
    result["cohort"]["eligible_child_days"] = None
    result["activity"] = {key: None for key in result["activity"]}
    result["ledger"] = {key: ({} if key == "by_reason" else None) for key in result["ledger"]}
    result["automatic_sources"] = {
        "coins": None, "by_source": {str(source): None for source in AUTOMATIC_SOURCES},
        "unattributed_positive_adjustments": None, "unattributed_expedition_coins": None,
        "attribution_complete": False, "child_days_over_100": None,
    }
    result["earning_sources"] = []
    result["earning_pace"] = {"status": "capacity_exceeded", "recurring_coins": None, "active_child_days": None,
                             "coins_per_active_day": None, "excluded_credits": None,
                             "attribution_complete": False, "provisional": True}
    result["shop_rewards"] = []
    result["notes"].append("The bounded observation capacity was exceeded; no partial cohort, activity, shop or ledger totals are reported.")
    return result


def economy_observations(actor, *, since=None, until=None):
    """Read anonymous aggregates for active children in actor's family.

    Explicit periods are available to synthetic verification callers. The web
    surface uses the fixed last-30-day default and accepts no user selectors.
    """
    actor = _authorized_actor(actor)
    since, until, zone, starts_at, ends_before = _period(actor, since, until)
    observer_excluded = LiveTestFamily.objects.filter(family=actor.family).exists()
    children = children_in(actor.family).filter(
        is_staff=False, date_joined__lt=ends_before,
    )
    child_count = 0 if observer_excluded else children.count()
    result = _empty_result(since, until, zone, starts_at, ends_before, observer_excluded, child_count)
    if observer_excluded:
        return result
    if child_count > MAX_COHORT_CHILDREN:
        return _limit_result(result, "cohort_limit_exceeded")
    offers = Reward.objects.filter(family=actor.family, is_active=True)
    shop_ceiling = offers.aggregate(value=Max("pk"))["value"] or 0
    shop = list(offers.filter(pk__lte=shop_ceiling).select_related(
        "item_definition__pet_species", "item_definition__potion_type",
    ).order_by("order", "cost_coins", "name", "pk").only(
        "pk", "name", "cost_coins", "stock", "fulfillment_kind", "item_definition",
        "item_definition__item_type", "item_definition__slug", "item_definition__metadata",
        "item_definition__pet_species__slug", "item_definition__pet_species__sprite_key",
        "item_definition__potion_type__slug",
    )[:MAX_SHOP_REWARDS + 1])
    if len(shop) > MAX_SHOP_REWARDS:
        return _limit_result(result, "shop_limit_exceeded")
    result["shop_rewards"] = _shop_reward_rows(shop)
    if child_count == 0:
        return result

    cohort = list(children.values("pk", "date_joined")[:MAX_COHORT_CHILDREN + 1])
    if len(cohort) > MAX_COHORT_CHILDREN:
        return _limit_result(result, "cohort_limit_exceeded")
    result["cohort"]["eligible_children"] = len(cohort)
    child_ids = [row["pk"] for row in cohort]
    result["cohort"]["eligible_child_days"] = sum(
        (until - max(since, timezone.localdate(row["date_joined"], timezone=zone))).days + 1
        for row in cohort
    )
    try:
        meaningful_days = meaningful_activity_days(
            family_id=actor.family_id, child_ids=child_ids, since=since, until=until, zone=zone,
            starts_at=starts_at, ends_before=ends_before, max_rows=MAX_ACTIVITY_ROWS,
        )
    except ActivityCapacityExceeded:
        return _limit_result(result, "activity_limit_exceeded")
    registered_on = {row["pk"]: timezone.localdate(row["date_joined"], timezone=zone) for row in cohort}
    meaningful_days = {(child_id, day) for child_id, day in meaningful_days if day >= registered_on[child_id]}
    all_ledger = CoinLedger.objects.filter(user_id__in=child_ids, user__family=actor.family)
    maximum_id = all_ledger.aggregate(value=Max("pk"))["value"] or 0
    ledger = all_ledger.filter(pk__lte=maximum_id, created_at__lt=ends_before)
    if ledger.count() > MAX_LEDGER_ROWS:
        return _limit_result(result, "ledger_limit_exceeded")
    entries = ledger.filter(created_at__gte=starts_at)
    grouped = list(entries.values("reason").annotate(
        entries=Count("pk"), credits=Sum("amount", filter=Q(amount__gt=0), default=0),
        signed_debits=Sum("amount", filter=Q(amount__lt=0), default=0), net=Sum("amount", default=0),
    ).order_by("reason"))
    by_reason = {
        row["reason"]: {"entries": row["entries"], "credits": row["credits"],
                        "debits": -row["signed_debits"], "net": row["net"]}
        for row in grouped
    }
    credits = sum(row["credits"] for row in grouped)
    debits = -sum(row["signed_debits"] for row in grouped)
    opening = ledger.filter(created_at__lt=starts_at).aggregate(value=Sum("amount", default=0))["value"]
    result["ledger"] = {"opening_balance": opening, "credits": credits, "debits": debits,
                        "net_change": credits - debits, "closing_balance": opening + credits - debits,
                        "by_reason": by_reason}
    active_days = entries.order_by().annotate(local_day=TruncDate("created_at", tzinfo=zone)).values("user_id", "local_day").distinct()
    result["activity"] = {"ledger_active_children": entries.order_by().values("user_id").distinct().count(),
                          "ledger_active_child_days": active_days.count(),
                          "meaningful_active_children": len({child_id for child_id, _ in meaningful_days}),
                          "meaningful_active_child_days": len(meaningful_days)}

    automatic = entries.filter(amount__gt=0).filter(
        Q(source=CoinLedger.Source.EXPEDITION, reason=CoinLedger.Reason.EXPEDITION)
        | Q(source__in=[CoinLedger.Source.EXPEDITION_SALVAGE, CoinLedger.Source.COIN_POUCH],
            reason=CoinLedger.Reason.ADJUSTMENT)
    )
    source_totals = dict(automatic.values("source").annotate(coins=Sum("amount")).values_list("source", "coins"))
    by_source = {str(source): source_totals.get(source, 0) for source in AUTOMATIC_SOURCES}
    unattributed_adjustments = entries.filter(
        amount__gt=0, reason=CoinLedger.Reason.ADJUSTMENT,
    ).exclude(source__in=ADJUSTMENT_SOURCES).aggregate(value=Sum("amount", default=0))["value"]
    unattributed_expeditions = entries.filter(
        amount__gt=0, reason=CoinLedger.Reason.EXPEDITION,
    ).exclude(source=CoinLedger.Source.EXPEDITION).aggregate(value=Sum("amount", default=0))["value"]
    over_budget = automatic.order_by().annotate(local_day=TruncDate("created_at", tzinfo=zone)).values(
        "user_id", "local_day",
    ).annotate(coins=Sum("amount")).filter(coins__gt=100).count()
    has_entries = bool(grouped)
    result["automatic_sources"] = {
        "coins": sum(by_source.values()), "by_source": by_source,
        "unattributed_positive_adjustments": unattributed_adjustments,
        "unattributed_expedition_coins": unattributed_expeditions,
        "attribution_complete": has_entries and unattributed_adjustments == 0 and unattributed_expeditions == 0,
        "child_days_over_100": over_budget,
    }
    _add_earning_estimates(result, _earning_sources(entries), len(meaningful_days))
    result["status"] = "observations_available" if has_entries or meaningful_days else "insufficient_evidence"
    return result
