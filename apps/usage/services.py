"""Private telemetry writes, called explicitly from authenticated API actions.

There are deliberately no signals, middleware, browser completion events or
hooks on reward/XP awards. MCP calls and background jobs never opt in.
"""
import logging
from datetime import timedelta, timezone as datetime_timezone

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.families.models import LiveTestFamily

from .models import UsageCollectionState, UsageEvent, UsageVisit

logger = logging.getLogger(__name__)
RETENTION_DAYS = 90
COMPLETED_ACTIONS = ("submitted", "completed")
SOURCES = {
    "homework.homeworksubmission": ("homework", "user", {"submitted", "approved"}),
    "chores.chorecompletion": ("chores", "user", {"submitted", "approved"}),
    "projects.project": ("projects", "assigned_to", {"submitted", "approved"}),
    "timecards.timeentry": ("projects", "user", {"completed"}),
    "timecards.timecard": ("projects", "user", {"approved"}),
    "reading.readingsession": ("reading", "user", {"completed"}),
    "movement.movementsession": ("movement", "user", {"completed"}),
    "habits.habitlog": ("habits", "user", {"completed", "checked_in"}),
    "rewards.rewardredemption": ("rewards", "user", {"requested", "approved"}),
}


def _eligible_actor(actor):
    if not getattr(actor, "is_authenticated", False) or not getattr(actor, "pk", None):
        return None
    current = get_user_model().objects.filter(pk=actor.pk, is_active=True).only("id", "family_id", "role").first()
    if current is None or current.role not in {"parent", "child"}:
        return None
    if LiveTestFamily.objects.filter(family_id=current.family_id).exists():
        return None
    return current


def record_action(actor, feature, action, *, source, source_id):
    """Record one accepted source action, deduplicated across devices/actors.

    The source is a server-selected, closed model label and persisted key.
    The savepoint keeps a failed telemetry write from poisoning the caller's
    business transaction. Logs contain no account, request or source content.
    """
    try:
        with transaction.atomic():
            spec = SOURCES.get(source)
            if spec is None or spec[0] != feature or action not in spec[2]:
                return None
            if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id < 1:
                return None
            current = _eligible_actor(actor)
            if current is None:
                return None
            source_model = apps.get_model(source)
            sources = source_model.objects.filter(pk=source_id)
            if source == "projects.project":
                # Match the domain's boundary: an unassigned project belongs
                # to its creator's family; assignment takes precedence.
                from config.viewsets import filter_projects_accessible_to
                sources = filter_projects_accessible_to(current, sources)
            else:
                sources = sources.filter(**{f"{spec[1]}__family_id": current.family_id})
            timestamp_field = "clock_out" if source == "timecards.timeentry" else "created_at"
            record = sources.only("pk", timestamp_field).first()
            if record is None:
                return None
            now = timezone.now()
            source_time = getattr(record, timestamp_field)
            if action in {"completed", "requested"} and (source_time is None or source_time < now - timedelta(days=RETENTION_DAYS)):
                return None
            UsageCollectionState.objects.get_or_create(pk=1, defaults={"started_at": now})
            event, _ = UsageEvent.objects.get_or_create(
                feature=feature, action=action, source=source, source_id=source_id,
                defaults={"actor": current, "family_id": current.family_id, "role": current.role, "occurred_at": now},
            )
            return event
    except Exception:
        logger.warning("Usage action recording failed.")
        return None


def record_visit(actor):
    """Record only an explicit foreground visit, never a background fetch."""
    try:
        with transaction.atomic():
            current = _eligible_actor(actor)
            if current is None:
                return None
            now = timezone.now()
            day = now.astimezone(datetime_timezone.utc).date()
            UsageCollectionState.objects.get_or_create(pk=1, defaults={"started_at": now})
            visit, _ = UsageVisit.objects.get_or_create(
                actor=current, occurred_on=day,
                defaults={"family_id": current.family_id, "role": current.role},
            )
            return visit
    except Exception:
        logger.warning("Usage visit recording failed.")
        return None


def prune_usage_data(*, now=None):
    """Expire raw telemetry; leave the deployment's measurement boundary."""
    now = now or timezone.now()
    cutoff_day = now.astimezone(datetime_timezone.utc).date() - timedelta(days=RETENTION_DAYS - 1)
    cutoff = timezone.datetime.combine(cutoff_day, timezone.datetime.min.time(), tzinfo=datetime_timezone.utc)
    with transaction.atomic():
        events, _ = UsageEvent.objects.filter(occurred_at__lt=cutoff).delete()
        visits, _ = UsageVisit.objects.filter(occurred_on__lt=cutoff_day).delete()
    return {"events_deleted": events, "visits_deleted": visits, "retention_days": RETENTION_DAYS}
