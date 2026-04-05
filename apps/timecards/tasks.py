from datetime import timedelta

from celery import shared_task
from django.utils import timezone


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

    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday() + 7)

    children = User.objects.filter(role="child")
    created = 0
    for child in children:
        timecard = TimecardService.generate_weekly_timecard(child, week_start)
        if timecard:
            created += 1
    return f"Generated {created} timecards"
