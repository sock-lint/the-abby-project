"""Celery tasks for the Chronicle app."""
from __future__ import annotations

import logging
from datetime import date

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.chronicle.models import ChronicleEntry

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(name="apps.chronicle.tasks.chronicle_birthday_check")
def chronicle_birthday_check() -> dict:
    """Fires daily. For each child whose DOB month/day == today:
    - idempotently create a BIRTHDAY entry
    - on first creation, grant BIRTHDAY_COINS_PER_YEAR × age_years coins
    - fire a BIRTHDAY notification
    """
    today = date.today()
    coins_per_year = getattr(settings, "BIRTHDAY_COINS_PER_YEAR", 100)

    children = User.objects.filter(
        role=User.Role.CHILD,
        date_of_birth__month=today.month,
        date_of_birth__day=today.day,
    )

    results = {"birthdays": 0, "gifts": 0}
    for user in children:
        with transaction.atomic():
            entry, created = ChronicleEntry.objects.get_or_create(
                user=user,
                kind=ChronicleEntry.Kind.BIRTHDAY,
                occurred_on=today,
                defaults={
                    "chapter_year": today.year if today.month >= 8 else today.year - 1,
                    "title": f"Turned {user.age_years}" if user.age_years else "Birthday",
                    "icon_slug": "birthday-candle",
                },
            )
            results["birthdays"] += 1
            if created and user.age_years:
                amount = coins_per_year * user.age_years
                _award_birthday_coins(user, amount)
                entry.metadata["gift_coins"] = amount
                entry.save(update_fields=["metadata"])
                results["gifts"] += 1
                _send_birthday_notification(user, amount)

    return results


def _award_birthday_coins(user, amount: int) -> None:
    """Create a CoinLedger ADJUSTMENT row for the birthday gift."""
    from apps.rewards.models import CoinLedger
    CoinLedger.objects.create(
        user=user,
        amount=amount,
        reason=CoinLedger.Reason.ADJUSTMENT,
        description="birthday_gift",
    )


def _send_birthday_notification(user, coin_amount: int) -> None:
    try:
        from apps.notifications.models import Notification, NotificationType
        Notification.objects.create(
            user=user,
            notification_type=NotificationType.BIRTHDAY,
            title=f"Happy birthday, {user.display_label}!",
            message=f"Your Yearbook has a new entry and {coin_amount} coins are in your treasury.",
        )
    except Exception:
        logger.exception("Birthday notification failed")
