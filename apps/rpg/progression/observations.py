"""Bounded, same-family accounting observations; never a reward experiment.

The anonymous Lab has no user selector. This separate read surface observes
persisted ledger amounts for the caller's recent child cohort, with explicit
coverage and denominators. It reads no journals or free-text descriptions.
"""
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.families.models import LiveTestFamily
from apps.families.queries import children_in
from apps.quests.activity import household_timezone
from apps.rewards.models import CoinLedger


MAX_COHORT_CHILDREN = 100
MAX_LEDGER_ROWS = 100_000
COHORT_DAYS = 90
WINDOW_DAYS = 30
AUTOMATIC_SOURCES = (
    CoinLedger.Source.EXPEDITION,
    CoinLedger.Source.EXPEDITION_SALVAGE,
    CoinLedger.Source.COIN_POUCH,
)
NOTES = [
    "Observed amounts use the installed uncapped economy. The 100-Coin Lab hypothesis is not live and these observations cannot validate an undeployed policy.",
    "The cohort contains only currently active, nonstaff children in your family registered within 90 inclusive days ending on the observation period's last day. Trusted provisioned test families are excluded.",
    "Ledger-active children and child-days count any persisted Coin transaction. They are not an engagement or retention measure and do not count visits without a Coin transaction.",
    "Eligible child-days count calendar days from registration or the start of the period, whichever is later; no transaction is required. Account activity and family membership are their current values, not reconstructed historical states.",
    "Typed attribution is recorded for new expedition, expedition-salvage and pouch awards only. Blank source is unknown or another source. Positive mixed adjustments can include check-ins, challenges, manual grants and historical pouch or salvage awards; their text is never used to guess a source.",
    "Automatic-source totals are a measured lower bound when attribution is incomplete. Child-days over 100 compare credited typed-source amounts within the current family calendar, not launch-day commitments or withheld rewards.",
    "Amounts are actual CoinLedger entries including applied boosts. Refunds and exchanges stay separate by reason; no activity-log deltas or receipt subtotals are added to the ledger.",
    "All dates use the family's current timezone, with an inclusive last date and exclusive next local midnight. This does not reconstruct past timezone settings. An ID ceiling excludes later inserts but is not a repeatable-read database snapshot.",
    "Observations available means ledger evidence exists, not that sample size is sufficient to approve an economy or predict retention. No family-cost or purchase-timing conclusion is inferred from these Coin totals.",
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
        cohort_starts_at = datetime.combine(until - timedelta(days=COHORT_DAYS - 1), time.min, tzinfo=zone)
    except OverflowError:
        raise ValueError("Observation dates cannot form a bounded local-day interval.") from None
    return since, until, zone, starts_at, ends_before, cohort_starts_at


def _empty_result(since, until, zone, starts_at, ends_before, observer_excluded, child_count):
    return {
        "schema_version": 1,
        "status": "insufficient_evidence",
        "period": {"since": since.isoformat(), "until": until.isoformat(), "timezone": str(zone),
                   "starts_at": starts_at.isoformat(), "ends_before": ends_before.isoformat()},
        "cohort": {"registered_within_days": COHORT_DAYS, "eligible_children": child_count,
                   "eligible_child_days": 0, "max_children": MAX_COHORT_CHILDREN,
                   "truncated": False, "observer_family_excluded": observer_excluded},
        "activity": {"ledger_active_children": 0, "ledger_active_child_days": 0},
        "ledger": {"opening_balance": 0, "credits": 0, "debits": 0, "net_change": 0,
                   "closing_balance": 0, "by_reason": {}},
        "automatic_sources": {
            "coins": 0, "by_source": {str(source): 0 for source in AUTOMATIC_SOURCES},
            "unattributed_positive_adjustments": 0, "unattributed_expedition_coins": 0,
            "attribution_complete": False, "child_days_over_100": 0,
        },
        "policy": {"installed_daily_automatic_coin_cap": None, "selected_lab_daily_coins": 100,
                   "is_live_experiment": False},
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
    result["notes"].append("The bounded observation capacity was exceeded; no partial cohort or partial ledger totals are reported.")
    return result


def economy_observations(actor, *, since=None, until=None):
    """Read anonymous aggregates for recent active children in actor's family.

    Explicit periods are available to synthetic verification callers. The web
    surface uses the fixed last-30-day default and accepts no user selectors.
    """
    actor = _authorized_actor(actor)
    since, until, zone, starts_at, ends_before, cohort_starts_at = _period(actor, since, until)
    observer_excluded = LiveTestFamily.objects.filter(family=actor.family).exists()
    children = children_in(actor.family).filter(
        is_staff=False, date_joined__gte=cohort_starts_at, date_joined__lt=ends_before,
    )
    child_count = 0 if observer_excluded else children.count()
    result = _empty_result(since, until, zone, starts_at, ends_before, observer_excluded, child_count)
    if child_count > MAX_COHORT_CHILDREN:
        return _limit_result(result, "cohort_limit_exceeded")
    if child_count == 0:
        return result

    cohort = list(children.values("pk", "date_joined"))
    child_ids = [row["pk"] for row in cohort]
    result["cohort"]["eligible_child_days"] = sum(
        (until - max(since, timezone.localdate(row["date_joined"], timezone=zone))).days + 1
        for row in cohort
    )
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
                          "ledger_active_child_days": active_days.count()}

    automatic = entries.filter(amount__gt=0).filter(
        Q(source=CoinLedger.Source.EXPEDITION, reason=CoinLedger.Reason.EXPEDITION)
        | Q(source__in=[CoinLedger.Source.EXPEDITION_SALVAGE, CoinLedger.Source.COIN_POUCH],
            reason=CoinLedger.Reason.ADJUSTMENT)
    )
    source_totals = dict(automatic.values("source").annotate(coins=Sum("amount")).values_list("source", "coins"))
    by_source = {str(source): source_totals.get(source, 0) for source in AUTOMATIC_SOURCES}
    unattributed_adjustments = entries.filter(
        amount__gt=0, reason=CoinLedger.Reason.ADJUSTMENT,
    ).exclude(source__in=[CoinLedger.Source.EXPEDITION_SALVAGE, CoinLedger.Source.COIN_POUCH]).aggregate(value=Sum("amount", default=0))["value"]
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
    result["status"] = "observations_available" if has_entries else "insufficient_evidence"
    return result
