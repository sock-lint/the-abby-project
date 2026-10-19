"""First detail presentations and bounded household evidence, never rewards."""
from datetime import datetime, time, timedelta
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Max, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.families.models import LiveTestFamily
from apps.families.queries import children_in
from .activity import household_timezone
from .goals import lock_user
from .models import ChallengeEnrollment, ChallengeOccurrence


MAX_COHORT_CHILDREN = 100
MAX_OCCURRENCES = 10_000
COHORT_DAYS = 90
WINDOW_DAYS = 30
COUNT_FIELDS = (
    "cohort_materialized", "opened", "completed", "opened_and_completed",
    "completed_without_recorded_opening", "opening_recorded_after_completion",
)
NOTES = [
    "This measures catalog challenge detail openings, not reading, attention, enjoyment, visits or retention. Opening grants no progress or rewards.",
    "Only one-time catalog windows first materialized within this period are counted. Materialization can follow a parent read or saved activity; it is not a child impression or the exact time of eligibility.",
    "The cohort contains currently active nonstaff children in your family registered within 90 inclusive days ending today. Only enrollments created with discovery tracking contribute window counts. Old or missing tracking is unknown, never evidence that content was not opened.",
    "Opened and completed counts overlap. Completion is automatic from qualifying activity and does not prove that a child opened the details. Recorded openings after completion are shown separately.",
    "Dates use the family's current timezone and include the last date through exclusive next local midnight. Current membership and active status are not reconstructed historically. Future-dated evidence is excluded.",
    "Trusted provisioned test families are excluded. Counts contain no child identities, authored descriptions, reading details or private journal text. No cross-family or story-specific inference is made.",
    "An occurrence ID ceiling excludes later inserts but is not a repeatable-read snapshot. Capacity failures return unknown counts rather than partial totals.",
]


@transaction.atomic
def record_details_opened(actor, goal_id):
    """Record one self-scoped presentation without materializing any goal."""
    try:
        current = lock_user(actor)
    except get_user_model().DoesNotExist:
        raise PermissionDenied("Active children may record their own detail openings only.") from None
    if (not current.is_active or current.role != "child"
            or current.family_id != getattr(actor, "family_id", None)):
        raise PermissionDenied("Active children may record their own detail openings only.")
    match = re.fullmatch(r"goal:([1-9][0-9]{0,18})", goal_id or "")
    if match is None or int(match[1]) > 9223372036854775807:
        raise NotFound("Challenge not found.")
    now = timezone.now()
    rows = ChallengeOccurrence.objects.filter(
        pk=int(match[1]), goal__user=current, goal__family_id=current.family_id,
        goal__is_catalog=True, starts_at__lte=now,
    )
    if not rows.exists():
        raise NotFound("Challenge not found.")
    # CAS changes this one observation only, including when a source payout
    # just completed under the same user lock. Do not touch updated_at.
    rows.filter(first_details_opened_at__isnull=True).update(first_details_opened_at=now)
    opened_at = rows.values_list("first_details_opened_at", flat=True).get()
    return {"id": f"goal:{int(match[1])}", "first_details_opened_at": opened_at.isoformat()}


def _authorized_observer(actor):
    current = get_user_model().objects.select_related("family").filter(
        pk=getattr(actor, "pk", None), family_id=getattr(actor, "family_id", None),
        is_active=True, is_staff=True, role="parent",
    ).first()
    if current is None:
        raise PermissionDenied("Active staff parents only.")
    return current


def discovery_observations(actor):
    """Read same-family new-child counts without listing/materializing goals."""
    actor = _authorized_observer(actor)
    now = timezone.now()
    zone = household_timezone(actor)
    until = timezone.localdate(now, timezone=zone)
    since = until - timedelta(days=WINDOW_DAYS - 1)
    starts_at = datetime.combine(since, time.min, tzinfo=zone)
    ends_before = datetime.combine(until + timedelta(days=1), time.min, tzinfo=zone)
    cohort_starts_at = datetime.combine(until - timedelta(days=COHORT_DAYS - 1), time.min, tzinfo=zone)
    # Today's boundary retains calendar semantics; as-of-now additionally
    # excludes corrupt or future-dated openings/completions/materializations.
    as_of = min(now, ends_before)
    observer_excluded = LiveTestFamily.objects.filter(family_id=actor.family_id).exists()
    children = children_in(actor.family).filter(
        is_staff=False, date_joined__gte=cohort_starts_at, date_joined__lt=ends_before,
        date_joined__lte=as_of,
    )
    # Freeze a bounded set once: re-evaluating this lazy membership query after
    # its count could expand the cohort and even make untracked totals negative.
    child_ids = [] if observer_excluded else list(children.values_list("pk", flat=True)[:MAX_COHORT_CHILDREN + 1])
    child_count = len(child_ids)
    result = {
        "schema_version": 1, "status": "insufficient_evidence",
        "period": {"since": since.isoformat(), "until": until.isoformat(), "timezone": str(zone),
                   "starts_at": starts_at.isoformat(), "ends_before": ends_before.isoformat(),
                   "as_of": as_of.isoformat()},
        "cohort": {"registered_within_days": COHORT_DAYS, "eligible_children": child_count,
                   "tracked_children": 0, "untracked_children": 0, "max_children": MAX_COHORT_CHILDREN,
                   "truncated": False, "observer_family_excluded": observer_excluded},
        "catalog_occurrences": dict.fromkeys(COUNT_FIELDS, 0), "notes": list(NOTES),
    }
    if child_count > MAX_COHORT_CHILDREN:
        result["cohort"]["eligible_children"] = None
        return _limited(result, "cohort_limit_exceeded")
    if not child_count:
        return result
    tracked = ChallengeEnrollment.objects.filter(
        user_id__in=child_ids, user__family_id=actor.family_id,
        user__is_active=True, user__is_staff=False, user__role="child",
        discovery_tracking_started_at__isnull=False,
        discovery_tracking_started_at__lte=as_of,
    )
    tracked_ids = list(tracked.values_list("user_id", flat=True))
    result["cohort"]["tracked_children"] = len(tracked_ids)
    result["cohort"]["untracked_children"] = child_count - len(tracked_ids)
    rows = ChallengeOccurrence.objects.filter(
        goal__user_id__in=tracked_ids, goal__family_id=actor.family_id, goal__is_catalog=True,
        goal__user__family_id=actor.family_id, goal__user__is_active=True,
        goal__user__is_staff=False, goal__user__role="child",
        goal__repeat_days=0, goal__repeat_weekly=False,
        created_at__gte=starts_at, created_at__lte=as_of, created_at__lt=ends_before,
    ).filter(created_at__gte=F("goal__user__challengeenrollment__discovery_tracking_started_at"))
    maximum_id = rows.aggregate(value=Max("pk"))["value"] or 0
    rows = rows.filter(pk__lte=maximum_id)
    if rows.count() > MAX_OCCURRENCES:
        return _limited(result, "occurrence_limit_exceeded")
    opened = Q(first_details_opened_at__lte=as_of, first_details_opened_at__lt=ends_before)
    completed = Q(completed_at__lte=as_of, completed_at__lt=ends_before)
    result["catalog_occurrences"] = rows.aggregate(
        cohort_materialized=Count("pk"), opened=Count("pk", filter=opened),
        completed=Count("pk", filter=completed), opened_and_completed=Count("pk", filter=opened & completed),
        completed_without_recorded_opening=Count("pk", filter=completed & ~opened),
        opening_recorded_after_completion=Count("pk", filter=opened & completed & Q(first_details_opened_at__gt=F("completed_at"))),
    )
    if result["catalog_occurrences"]["cohort_materialized"]:
        result["status"] = "observations_available"
    return result


def _limited(result, status):
    result["status"] = status
    result["cohort"].update(truncated=True, tracked_children=None, untracked_children=None)
    result["catalog_occurrences"] = dict.fromkeys(COUNT_FIELDS)
    return result
