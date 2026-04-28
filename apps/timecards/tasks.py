import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _week_start(day):
    """Return the Monday on or before ``day``."""
    return day - timedelta(days=day.weekday())


@shared_task
def auto_clock_out_task():
    """Auto clock-out stale entries (runs every 30 minutes)."""
    from .services import ClockService
    count = ClockService.auto_clock_out()
    return f"Auto clocked out {count} entries"


@shared_task
def generate_weekly_timecards_task():
    """Generate weekly timecards for all child users (runs Sunday midnight)."""
    from apps.projects.models import User
    from .services import TimecardService

    week_start = _week_start(timezone.localdate())

    children = User.objects.filter(role="child")
    created = 0
    for child in children:
        timecard = TimecardService.generate_weekly_timecard(child, week_start)
        if timecard:
            created += 1
    return f"Generated {created} timecards"


@shared_task
def send_weekly_email_summaries():
    """Send weekly summary emails to all users (runs Sunday morning)."""
    from django.core.mail import send_mail
    from django.conf import settings as django_settings
    from apps.projects.models import User
    from apps.payments.services import PaymentService
    from apps.achievements.models import UserBadge
    from apps.timecards.models import TimeEntry
    from django.db.models import Sum

    week_start = _week_start(timezone.localdate())
    week_end = week_start + timedelta(days=6)

    for child in User.objects.filter(role="child"):
        entries = TimeEntry.objects.filter(
            user=child, status="completed",
            clock_in__date__gte=week_start,
            clock_in__date__lte=week_end,
        )
        total_minutes = entries.aggregate(total=Sum("duration_minutes"))["total"] or 0
        hours = round(total_minutes / 60, 1)
        balance = PaymentService.get_balance(child)
        badges = UserBadge.objects.filter(
            user=child, earned_at__date__gte=week_start,
        ).select_related("badge")

        if hours == 0 and not badges.exists():
            continue

        badge_text = ""
        if badges.exists():
            badge_text = "\nBadges earned: " + ", ".join(
                f"{ub.badge.icon} {ub.badge.name}" for ub in badges
            )

        try:
            send_mail(
                subject=f"The Abby Project Weekly Summary — {week_start.strftime('%b %d')}",
                message=(
                    f"Hi {child.display_label}!\n\n"
                    f"This week you worked {hours} hours.{badge_text}\n"
                    f"Current balance: ${balance}\n\n"
                    f"Keep up the great work!"
                ),
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[child.email] if child.email else [],
            )
        except Exception:
            logger.exception("Failed to send weekly summary email to child %s", child.pk)

    # Parent summary — scoped per family so a parent only sees their own
    # household's children + their own pending timecard queue.
    from apps.families.models import Family
    from apps.timecards.models import Timecard

    for family in Family.objects.all():
        family_children = User.objects.filter(family=family, role="child")
        child_summaries = []
        for child in family_children:
            entries = TimeEntry.objects.filter(
                user=child, status="completed",
                clock_in__date__gte=week_start,
                clock_in__date__lte=week_end,
            )
            total_minutes = entries.aggregate(total=Sum("duration_minutes"))["total"] or 0
            hours = round(total_minutes / 60, 1)
            if hours > 0:
                child_summaries.append(f"  {child.display_label}: {hours}h")

        if not child_summaries:
            continue

        pending = Timecard.objects.filter(
            status="pending", user__family=family,
        ).count()

        for parent in User.objects.filter(role="parent", family=family, is_active=True):
            try:
                send_mail(
                    subject=f"The Abby Project Parent Summary — {week_start.strftime('%b %d')}",
                    message=(
                        f"Hi {parent.display_label}!\n\n"
                        f"This week:\n" + "\n".join(child_summaries) + "\n\n"
                        f"Pending timecards: {pending}\n"
                    ),
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[parent.email] if parent.email else [],
                )
            except Exception:
                logger.exception("Failed to send weekly summary email to parent %s", parent.pk)

    return "Weekly emails sent"
