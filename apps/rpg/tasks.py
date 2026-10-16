import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


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
    User.objects.select_for_update(no_key=True).get(pk=child.pk)
    profile = CharacterProfile.objects.select_for_update().filter(user=child).first()
    if not profile or profile.last_active_date != today:
        return False

    available = ChoreService.get_available_chores(child, today)
    daily_chores = [c for c in available if c.recurrence == Chore.Recurrence.DAILY]
    # Availability treats pending submissions as done to prevent duplicate
    # submissions. Reward eligibility requires actual parent approval instead.
    if not daily_chores or not all(
        c.today_completion_status == ChoreCompletion.Status.APPROVED
        for c in daily_chores
    ):
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
    """Award approved daily chores once per child and configured local date.

    Chore completions and streak activity currently save this same configured
    day. Keep the eligibility and receipt date on that shared producer contract.
    """
    from apps.families.queries import children_across_families

    awarded = 0
    seen = 0
    today = timezone.localdate()
    for _family, child in children_across_families():
        seen += 1
        awarded += _award_perfect_day(child, today)
    return f"Perfect day evaluated: {awarded}/{seen} children awarded."


# Streaks of at least this length get the evening at-risk warning —
# below it there isn't enough invested to be worth a nudge.
STREAK_AT_RISK_MIN = 3


@shared_task
def streak_at_risk_warning_task():
    """Warn children whose streak will break tonight if they stay idle.

    Runs at 19:00 local (before the 23:55 perfect-day tick) so there's
    still real evening left to act on it. Gentle-nudge doctrine: child
    only — no parent fan-out — and at most one warning per local day.
    Kids holding an armed streak freeze that covers today are skipped;
    the freeze means tonight's miss won't break anything.
    """
    from apps.families.queries import children_across_families
    from apps.notifications.models import Notification, NotificationType
    from apps.notifications.services import notify
    from apps.rpg.models import CharacterProfile

    today = timezone.localdate()
    warned = 0
    seen = 0

    for _family, child in children_across_families():
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
                "you log something — a duty, a ritual tap, or a quick study "
                "counts."
            ),
            notification_type=NotificationType.STREAK_AT_RISK,
            link="/quests",
        )
        warned += 1

    return f"Streak at-risk evaluated: {warned}/{seen} children warned."
