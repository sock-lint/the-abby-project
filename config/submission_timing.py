"""Server-owned date context saved with a submitted piece of work."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone


def submission_context(user, at=None):
    at = at or timezone.now()
    family = getattr(user, "family", None)
    name = getattr(family, "timezone", None) or "America/Phoenix"
    try:
        zone = ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        zone = ZoneInfo("America/Phoenix")
    return at, zone, at.astimezone(zone).date()


def build_timing_snapshot(user, *, schedule, at, due_on=None,
                          period_start=None, period_end=None, timeliness=None):
    at, zone, submitted_on = submission_context(user, at)
    return {
        "version": 1,
        "timezone": str(zone),
        "submitted_at": at.isoformat(),
        "submitted_on": submitted_on.isoformat(),
        "schedule": schedule,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "due_on": due_on.isoformat() if due_on else None,
        "timeliness": timeliness,
    }
