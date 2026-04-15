import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def evaluate_perfect_day_task():
    """Award 'Perfect Day' bonus to children who completed all daily chores."""
    from apps.chores.models import Chore
    from apps.chores.services import ChoreService
    from apps.notifications.services import notify
    from apps.projects.models import User
    from apps.rewards.models import CoinLedger
    from apps.rewards.services import CoinService
    from apps.rpg.models import CharacterProfile

    today = timezone.localdate()
    children = User.objects.filter(role="child")
    awarded = 0

    for child in children:
        profile = CharacterProfile.objects.filter(user=child).first()
        if not profile or profile.last_active_date != today:
            continue

        available = ChoreService.get_available_chores(child, today)
        daily_chores = [c for c in available if c.recurrence == Chore.Recurrence.DAILY]

        # If daily chores exist, all must be done
        if daily_chores and not all(c.is_done_today for c in daily_chores):
            continue

        # Award perfect day
        profile.perfect_days_count += 1
        profile.save(update_fields=["perfect_days_count"])

        CoinService.award_coins(
            child,
            15,
            CoinLedger.Reason.ADJUSTMENT,
            description="Perfect Day bonus!",
        )

        notify(
            child,
            title="Perfect Day!",
            message="You completed all your daily tasks. +15 coins!",
            notification_type="perfect_day",
            link="/",
        )
        awarded += 1

    return f"Perfect day evaluated: {awarded}/{children.count()} children awarded."
