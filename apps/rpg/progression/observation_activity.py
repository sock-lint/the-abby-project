"""Content-free, bounded dates of surviving selected work for economy reports.

These are work records, rather than telemetry or reward receipts. Reading
corrections and source removal therefore affect activity without rewriting any
reward. Private writing, visits and automatic reward cascades are not queried.
"""
from django.db.models import F, Max, Q
from django.utils import timezone

from apps.chores.models import ChoreCompletion
from apps.creations.models import Creation
from apps.habits.models import HabitLog
from apps.homework.models import HomeworkSubmission
from apps.movement.models import MovementSession
from apps.reading.models import ReadingSession
from apps.timecards.models import TimeEntry


class ActivityCapacityExceeded(Exception):
    """The selected source rows exceed the report's all-or-nothing bound."""


def meaningful_activity_days(*, family_id, child_ids, since, until, zone,
                             starts_at, ends_before, max_rows):
    """Return private child/day keys; callers expose anonymous counts only.

    Explicit work dates own reading, movement and creation days. Submission,
    habit and completed work timestamps use the family's current timezone.
    Nothing here validates payouts, advances challenges or reads source prose.
    """
    owners = {"user_id__in": child_ids, "user__family_id": family_id}
    dates = {"occurred_on__gte": since, "occurred_on__lte": until}
    saved = {"created_at__gte": starts_at, "created_at__lt": ends_before}
    sources = (
        (ReadingSession.objects.filter(
            **owners, **dates, book__user_id=F("user_id"),
        ), "occurred_on", False),
        (MovementSession.objects.filter(
            **owners, **dates, duration_minutes__gt=0,
        ), "occurred_on", False),
        (Creation.objects.filter(
            **owners, **dates, status__in=[Creation.Status.LOGGED, Creation.Status.PENDING, Creation.Status.APPROVED],
        ), "occurred_on", False),
        (HabitLog.objects.filter(
            **owners, **saved, direction=1, habit__user_id=F("user_id"),
        ), "created_at", True),
        (TimeEntry.objects.filter(
            **owners, status=TimeEntry.Status.COMPLETED, duration_minutes__gt=0,
            clock_out__gte=starts_at, clock_out__lt=ends_before,
        ).filter(
            Q(project__assigned_to__family_id=family_id)
            | Q(project__assigned_to__isnull=True, project__created_by__family_id=family_id),
        ), "clock_out", True),
        (HomeworkSubmission.objects.filter(
            **owners, **saved, status__in=[HomeworkSubmission.Status.PENDING, HomeworkSubmission.Status.APPROVED],
            assignment__assigned_to_id=F("user_id"),
        ), "created_at", True),
        (ChoreCompletion.objects.filter(
            **owners, **saved, status__in=[ChoreCompletion.Status.PENDING, ChoreCompletion.Status.APPROVED],
            chore__family_id=family_id,
        ), "created_at", True),
    )
    days = set()
    inspected_rows = 0
    for query, date_field, timestamp in sources:
        # A ceiling fixes each source's insert boundary without claiming a
        # repeatable-read snapshot across source tables or later corrections.
        ceiling = query.aggregate(value=Max("pk"))["value"] or 0
        remaining = max_rows - inspected_rows
        rows = list(query.filter(pk__lte=ceiling).order_by().values_list(
            "user_id", date_field,
        )[:remaining + 1])
        if len(rows) > remaining:
            raise ActivityCapacityExceeded
        inspected_rows += len(rows)
        for child_id, day in rows:
            if timestamp:
                day = timezone.localdate(day, timezone=zone)
            days.add((child_id, day))
    return days
