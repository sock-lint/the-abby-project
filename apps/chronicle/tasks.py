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


from apps.chronicle.services import ChronicleService


@shared_task(name="apps.chronicle.tasks.chronicle_chapter_transition")
def chronicle_chapter_transition() -> dict:
    """Fires daily at 00:25 local. No-op except on Aug 1 or Jun 1.

    - Aug 1: for each child with DOB, record_chapter_start(user, current_chapter_year).
    - Jun 1: for each child with DOB, record_chapter_end + freeze_recap for the chapter
      that just closed. If that chapter corresponds to grade 12, mark the recap's
      metadata.is_graduation=True and also emit a standalone MILESTONE entry
      with event_slug='graduated_high_school'.
    """
    today = date.today()
    if (today.month, today.day) not in ((8, 1), (6, 1)):
        return {"noop": True}

    children = User.objects.filter(role=User.Role.CHILD, date_of_birth__isnull=False)
    results = {"starts": 0, "ends": 0, "recaps": 0, "graduations": 0}

    for user in children:
        if (today.month, today.day) == (8, 1):
            ChronicleService.record_chapter_start(user, today.year)
            results["starts"] += 1
        else:  # Jun 1
            closing_chapter_year = today.year - 1  # Aug (year-1) → Jun year
            ChronicleService.record_chapter_end(user, closing_chapter_year)
            recap = ChronicleService.freeze_recap(user, closing_chapter_year)
            results["ends"] += 1
            results["recaps"] += 1

            # If the closing chapter was grade 12, flag + emit graduation milestone.
            if user.grade_entry_year is not None:
                grade_of_closing_chapter = 9 + (closing_chapter_year - user.grade_entry_year)
                if grade_of_closing_chapter == 12:
                    recap.metadata["is_graduation"] = True
                    recap.save(update_fields=["metadata"])
                    ChronicleEntry.objects.get_or_create(
                        user=user,
                        kind=ChronicleEntry.Kind.MILESTONE,
                        event_slug="graduated_high_school",
                        defaults={
                            "chapter_year": closing_chapter_year,
                            "occurred_on": today,
                            "title": "🎓 Graduated high school",
                            "icon_slug": "graduation-cap",
                        },
                    )
                    results["graduations"] += 1

    return results
