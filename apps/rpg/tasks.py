import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def evaluate_perfect_day_task():
    """Award 'Perfect Day' bonus to children who completed all daily chores."""
    from apps.chores.models import Chore
    from apps.chores.services import ChoreService
    from apps.families.queries import children_across_families
    from apps.notifications.services import notify
    from apps.rewards.models import CoinLedger
    from apps.rewards.services import CoinService
    from apps.rpg.models import CharacterProfile

    today = timezone.localdate()
    awarded = 0
    seen = 0

    for _family, child in children_across_families():
        seen += 1
        profile = CharacterProfile.objects.filter(user=child).first()
        if not profile or profile.last_active_date != today:
            continue

        available = ChoreService.get_available_chores(child, today)
        daily_chores = [c for c in available if c.recurrence == Chore.Recurrence.DAILY]

        # Require at least one daily chore AND every one of them done.
        if not daily_chores or not all(c.is_done_today for c in daily_chores):
            continue

        # Award perfect day
        profile.perfect_days_count += 1
        profile.save(update_fields=["perfect_days_count"])

        from apps.activity.services import (
            ActivityLogService, activity_scope,
        )
        with activity_scope(suppress_inner_ledger=True):
            CoinService.award_coins(
                child,
                15,
                CoinLedger.Reason.ADJUSTMENT,
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
        awarded += 1

    return f"Perfect day evaluated: {awarded}/{seen} children awarded."
