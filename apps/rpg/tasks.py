import logging
from datetime import timedelta
from itertools import chain
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


def _personal_participants():
    """Child accounts and parents who have entered their own progression space."""
    from apps.families.queries import children_across_families, parents_across_families
    return chain(children_across_families(), parents_across_families(challengeenrollment__isnull=False))


def _completion_accounting_day(completion):
    """Map saved daily submission evidence to the configured worker day.

    Legacy rows have only the original configured-day period identity. New
    rows keep a household period and must use their captured submission instant,
    independently of a later database insert, parent approval or zone edit.
    """
    snapshot = completion.timing_snapshot
    if snapshot is None:
        return completion.completed_date
    if (
        not isinstance(snapshot, dict)
        or type(snapshot.get("version")) is not int
        or snapshot["version"] != 1
        or snapshot.get("schedule") != "daily"
        or not isinstance(snapshot.get("submitted_at"), str)
        or not isinstance(snapshot.get("timezone"), str)
    ):
        return None
    try:
        submitted_at = parse_datetime(snapshot["submitted_at"])
        if submitted_at is None or timezone.is_naive(submitted_at):
            return None
        household_day = timezone.localdate(submitted_at, ZoneInfo(snapshot["timezone"]))
        worker_day = timezone.localdate(submitted_at, timezone.get_default_timezone())
    except (ValueError, OverflowError, ZoneInfoNotFoundError):
        return None
    period = completion.completed_date.isoformat()
    if household_day != completion.completed_date or any(
        snapshot.get(key) != period for key in ("submitted_on", "period_start", "period_end")
    ):
        return None
    return worker_day


@transaction.atomic
def _award_perfect_day(child, today):
    from apps.accounts.models import User
    from apps.activity.services import ActivityLogService, activity_scope
    from apps.chores.models import Chore, ChoreCompletion
    from apps.chores.services import ChoreService
    from apps.notifications.services import notify
    from apps.rewards.models import CoinLedger
    from apps.rewards.services import CoinService
    from apps.rpg.models import CharacterProfile, PerfectDayReceipt

    # Use the same user -> profile lock order as the other reward paths.
    child = User.objects.select_for_update(no_key=True).get(pk=child.pk)
    profile = CharacterProfile.objects.select_for_update().filter(user=child).first()
    if not profile or profile.last_active_date != today:
        return False

    # Parents can complete only their assigned personal chores. Shared family
    # chores remain part of the child's existing daily requirements.
    assignments = Q(assigned_to=child)
    if child.role == "child":
        assignments |= Q(assigned_to__isnull=True)
    daily_chores = [chore for chore in Chore.objects.filter(
        assignments,
        family_id=child.family_id, is_active=True, pending_parent_review=False,
        recurrence=Chore.Recurrence.DAILY,
    ) if ChoreService.is_active_this_week(chore, today)]
    if not daily_chores:
        return False
    daily_ids = {chore.pk for chore in daily_chores}
    # IANA household/worker offsets can cross up to two calendar dates.
    # The active-completion constraint bounds this to five approved rows per
    # chore, without scanning its history or trusting a versioned period as
    # an accounting date. Pending/rejected rows cannot satisfy the set.
    completions = ChoreCompletion.objects.filter(
        user=child, chore_id__in=daily_ids, status=ChoreCompletion.Status.APPROVED,
        completed_date__range=(today - timedelta(days=2), today + timedelta(days=2)),
    ).only("chore_id", "completed_date", "timing_snapshot").order_by()
    approved_ids = {
        completion.chore_id for completion in completions
        if _completion_accounting_day(completion) == today
    }
    if approved_ids != daily_ids:
        return False

    _receipt, created = PerfectDayReceipt.objects.get_or_create(user=child, day=today)
    if not created:
        return False

    profile.perfect_days_count += 1
    profile.save(update_fields=["perfect_days_count"])
    with activity_scope(suppress_inner_ledger=True):
        CoinService.award_coins(
            child, 15, CoinLedger.Reason.ADJUSTMENT,
            description="Perfect Day bonus!",
        )
    ActivityLogService.record(
        category="system",
        event_type="system.perfect_day",
        summary="Perfect Day: +15 coins",
        actor=None,
        subject=child,
        coins_delta=15,
        breakdown=[
            {"label": "daily chores done", "value": len(daily_chores), "op": "="},
            {"label": "bonus", "value": 15, "op": "note"},
            {"label": "perfect days total", "value": profile.perfect_days_count, "op": "note"},
        ],
        extras={
            "day": today.isoformat(),
            "daily_chores_done": len(daily_chores),
            "perfect_days_count": profile.perfect_days_count,
        },
    )
    from apps.rpg.constants import TriggerType
    from apps.rpg.services import DropService
    DropService.award_accomplishment(child, TriggerType.PERFECT_DAY)
    from apps.chronicle.recognition import safe_record_firsts
    safe_record_firsts(child, TriggerType.PERFECT_DAY)
    from apps.achievements.services import BadgeService
    BadgeService.evaluate_badges(child, scopes={"time", "badges"})
    notify(
        child,
        title="Perfect Day!",
        message="You completed all your daily tasks. +15 coins!",
        notification_type="perfect_day",
        link="/",
    )
    return True


@shared_task
def evaluate_perfect_day_task():
    """Award approved daily chores once per participant and configured local date.

    Household chore periods stay distinct from this worker/streak day. New
    completions use their captured submission instant; legacy rows retain
    their configured-day completed_date fallback.
    """
    awarded = 0
    seen = 0
    today = timezone.localdate(timezone=timezone.get_default_timezone())
    for _family, child in _personal_participants():
        seen += 1
        awarded += _award_perfect_day(child, today)
    return f"Perfect day evaluated: {awarded}/{seen} participants awarded."


# Streaks of at least this length get the evening at-risk warning —
# below it there isn't enough invested to be worth a nudge.
STREAK_AT_RISK_MIN = 3


@shared_task
def streak_at_risk_warning_task():
    """Warn participating accounts whose streak will break tonight if idle.

    Runs at 19:00 local (before the 23:55 perfect-day tick) so there's
    still real evening left to act on it. Reminders address only the account
    with its own streak, at most once per local day; there is no family fan-out.
    Accounts holding an armed streak freeze that covers today are skipped;
    the freeze means tonight's miss won't break anything.
    """
    from apps.notifications.models import Notification, NotificationType
    from apps.notifications.services import notify
    from apps.rpg.models import CharacterProfile

    today = timezone.localdate()
    warned = 0
    seen = 0

    for _family, child in _personal_participants():
        seen += 1
        profile = CharacterProfile.objects.filter(user=child).first()
        if not profile or profile.login_streak < STREAK_AT_RISK_MIN:
            continue
        # Already active today — nothing at risk.
        if profile.last_active_date is None or profile.last_active_date >= today:
            continue
        # An armed freeze covering today absorbs the miss.
        if (
            profile.streak_freeze_expires_at
            and profile.streak_freeze_expires_at >= today
        ):
            continue
        # One warning per local day, even if the task re-runs.
        already_warned = Notification.objects.filter(
            user=child,
            notification_type=NotificationType.STREAK_AT_RISK,
            created_at__date=today,
        ).exists()
        if already_warned:
            continue

        notify(
            child,
            title="Your streak is at risk!",
            message=(
                f"Your {profile.login_streak}-day streak ends tonight unless "
                "you log something — a chore, a habit tap, or homework "
                "counts."
            ),
            notification_type=NotificationType.STREAK_AT_RISK,
            link="/quests",
        )
        warned += 1

    return f"Streak at-risk evaluated: {warned}/{seen} participants warned."
