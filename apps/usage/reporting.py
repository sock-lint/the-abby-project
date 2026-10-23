"""Bounded, aggregate-only usage reports; no household/person drill-down."""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from statistics import median

from django.db.models import Count, Min, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.chores.models import ChoreCompletion
from apps.families.models import Family, LiveTestFamily
from apps.homework.models import HomeworkSubmission

from .models import UsageCollectionState, UsageEvent, UsageVisit
from .services import COMPLETED_ACTIONS, RETENTION_DAYS

UTC = datetime_timezone.utc


def _midnight(day):
    return datetime.combine(day, time.min, tzinfo=UTC)


def _metrics(events, visits, start, end):
    values = events.filter(occurred_at__gte=start, occurred_at__lt=end).aggregate(
        active_families=Count("family_id", distinct=True),
        active_children=Count("actor_id", distinct=True, filter=Q(role="child")),
        active_parents=Count("actor_id", distinct=True, filter=Q(role="parent")),
        completed_activities=Count("pk", filter=Q(action__in=COMPLETED_ACTIONS)),
        actions=Count("pk"),
    )
    values["visitors"] = visits.filter(occurred_on__gte=start.date(), occurred_on__lt=end.date()).values("actor_id").distinct().count()
    return values


def _trend(events, visits, start, end):
    action_rows = events.filter(occurred_at__gte=start, occurred_at__lt=end).annotate(
        day=TruncDate("occurred_at", tzinfo=UTC),
    ).values("day").annotate(
        active_families=Count("family_id", distinct=True),
        active_people=Count("actor_id", distinct=True),
        completed_activities=Count("pk", filter=Q(action__in=COMPLETED_ACTIONS)),
    )
    actions = {row.pop("day"): row for row in action_rows}
    visit_rows = visits.filter(occurred_on__gte=start.date(), occurred_on__lt=end.date()).values("occurred_on").annotate(visitors=Count("actor_id", distinct=True))
    daily_visits = {row["occurred_on"]: row["visitors"] for row in visit_rows}
    rows = []
    day = start.date()
    while day < end.date():
        rows.append({
            "date": day.isoformat(),
            **actions.get(day, {"active_families": 0, "active_people": 0, "completed_activities": 0}),
            "visitors": daily_visits.get(day, 0),
        })
        day += timedelta(days=1)
    return rows


def _features(events, start, end, feature):
    rows = events.filter(occurred_at__gte=start, occurred_at__lt=end).values("feature").annotate(
        actors=Count("actor_id", distinct=True), actions=Count("pk"),
        completed_activities=Count("pk", filter=Q(action__in=COMPLETED_ACTIONS)),
    )
    by_feature = {row["feature"]: row for row in rows}
    features = UsageEvent.Feature.values if feature == "all" else [feature]
    return [by_feature.get(name, {"feature": name, "actors": 0, "actions": 0, "completed_activities": 0}) for name in features]


def _onboarding(families, all_events, start, end, observed_start):
    cohorts = families.filter(created_at__gte=max(start, observed_start), created_at__lt=end).annotate(
        first_child=Min("members__date_joined", filter=Q(members__role="child", members__date_joined__lt=end)),
    )
    members = {row["id"]: row["first_child"] for row in cohorts.values("id", "first_child")}
    actions = defaultdict(list)
    for event in all_events.filter(family_id__in=members, occurred_at__lt=end).values("family_id", "occurred_at", "action", "role"):
        actions[event["family_id"]].append(event)
    child_added = first_activity = first_approval = 0
    for family_id, child_at in members.items():
        if child_at is None:
            continue
        child_added += 1
        performed = [event["occurred_at"] for event in actions[family_id] if event["action"] in COMPLETED_ACTIONS and event["occurred_at"] >= child_at]
        if not performed:
            continue
        first_activity += 1
        first_at = min(performed)
        if any(event["action"] == "approved" and event["role"] == "parent" and event["occurred_at"] >= first_at for event in actions[family_id]):
            first_approval += 1
    return {
        "families_created": len(members), "child_added": child_added,
        "first_activity": first_activity, "first_parent_approval": first_approval,
        "coverage": "Families created during the selected period after collection began; steps progress through the report end. All roles and features are included. Deleted accounts and families are excluded.",
    }


def _retention(all_events, observed_start, today, has_collection):
    # Compare whole Monday–Sunday weeks, including existing households. A
    # signup-only denominator would omit the owner's existing families.
    return_end = _midnight(today - timedelta(days=today.weekday()))
    return_start = return_end - timedelta(days=7)
    returned = set(all_events.filter(occurred_at__gte=return_start, occurred_at__lt=return_end).values_list("family_id", flat=True).distinct())
    result = {}
    for week in (1, 4):
        cohort_start = return_start - timedelta(weeks=week)
        cohort_end = return_end - timedelta(weeks=week)
        complete = bool(has_collection and observed_start <= cohort_start)
        cohort = set(all_events.filter(occurred_at__gte=cohort_start, occurred_at__lt=cohort_end).values_list("family_id", flat=True).distinct()) if complete else set()
        result[f"week_{week}"] = {
            "cohort_start": cohort_start.date().isoformat(), "cohort_end": (cohort_end.date() - timedelta(days=1)).isoformat(),
            "return_start": return_start.date().isoformat(), "return_end": (return_end.date() - timedelta(days=1)).isoformat(),
            "history_complete": complete,
            "eligible_families": len(cohort) if complete else None,
            "returned_families": len(cohort & returned) if complete else None,
            "rate": len(cohort & returned) / len(cohort) if cohort else None,
        }
    result["definition"] = "Families active in the week one or four weeks before the latest fully completed UTC Monday–Sunday week, returning in that latest week. Activity requires a meaningful human action. Both full weeks need observed history. Scope applies; date-range, role and feature filters do not alter these whole-family cohorts."
    return result


def _friction(families, start, end, role, feature):
    pending = 0
    decision_hours = []
    coverage = []
    for name, model in (("homework", HomeworkSubmission), ("chores", ChoreCompletion)):
        if feature not in {"all", name}:
            continue
        coverage.append(name)
        query = model.objects.filter(user__family_id__in=families.values("pk"))
        if name == "homework":
            query = query.filter(assignment__assigned_to__family_id__in=families.values("pk"))
        else:
            query = query.filter(chore__family_id__in=families.values("pk"))
        pending += query.filter(status="pending").count()
        if role == "child":
            continue
        approved = query.filter(
            status="approved", decided_at__gte=start, decided_at__lt=end,
            decided_by__role="parent", decided_by__family_id__in=families.values("pk"),
        ).values_list("created_at", "decided_at")
        decision_hours.extend((decided - created).total_seconds() / 3600 for created, decided in approved if decided >= created)
    return {
        "pending_reviews": pending if coverage else None,
        "median_approval_hours": round(median(decision_hours), 2) if decision_hours else None,
        "coverage": coverage,
        "notes": "Pending reviews are the current backlog regardless of date or role. Median approval time covers parent-approved homework and chores decided during the selected period; the child role filter has no approvals. Both honor the feature filter.",
        "unavailable": ["workflow_abandonment", "failed_saves", "sign_in_failures", "request_latency"],
    }


def build_usage_report(actor, *, scope="family", days=28, role="all", feature="all", now=None):
    """Build a report for an authorized staff parent, using UTC calendar days."""
    if not actor.is_active or actor.role != "parent" or not actor.is_staff:
        raise PermissionDenied("Staff parents only.")
    if scope == "deployment" and not actor.is_superuser:
        raise PermissionDenied("Deployment usage is restricted to superusers.")
    now = (now or timezone.now()).astimezone(UTC)
    today = now.date()
    end = _midnight(today + timedelta(days=1))
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    retained_start = _midnight(today - timedelta(days=RETENTION_DAYS - 1))
    state = UsageCollectionState.objects.filter(pk=1).first()
    observed_start = max(state.started_at, retained_start) if state else now
    families = Family.objects.exclude(pk__in=LiveTestFamily.objects.values("family_id"))
    if scope == "family":
        families = families.filter(pk=actor.family_id)
    all_events = UsageEvent.objects.filter(
        family_id__in=families.values("pk"), occurred_at__gte=observed_start, occurred_at__lte=now,
    )
    events = all_events
    visits = UsageVisit.objects.filter(family_id__in=families.values("pk"), occurred_on__gte=observed_start.astimezone(UTC).date(), occurred_on__lte=today)
    if role != "all":
        events = events.filter(role=role)
        visits = visits.filter(role=role)
    if feature != "all":
        events = events.filter(feature=feature)
    week_start = end - timedelta(days=7)
    weekly = _metrics(events, visits, week_start, end)
    return {
        "scope": scope,
        "can_view_deployment": bool(actor.is_superuser),
        "filters": {"days": days, "role": role, "feature": feature},
        "period": {"start": start.date().isoformat(), "end": today.isoformat(), "previous_start": previous_start.date().isoformat(), "previous_end": (start.date() - timedelta(days=1)).isoformat(), "timezone": "UTC"},
        "collection": {
            "started_at": state.started_at.isoformat() if state else None,
            "retention_days": RETENTION_DAYS,
            "history_complete": bool(state and observed_start <= start),
            "previous_history_complete": bool(state and observed_start <= previous_start),
            "notes": [
                "Meaningful activity is an accepted human action; visits are separate. Completed activities are submitted homework, chores or projects and logged reading, movement or positive habits. Rewards and approvals are engagement but not additional completed activities.",
                "Collection begins with this deployment; earlier activity is not reconstructed. Empty or partial history does not establish zero earlier usage. Live-check families, MCP and background automation are excluded.",
                "Raw usage is retained for 90 UTC calendar days with daily cleanup. Account and family deletion also remove linked usage; historical totals can change after deletion.",
                "Visits count accounts seen in the foreground once per UTC day, including multiple devices. Visits have no feature attribution; a feature filter does not change visit counts.",
                "The weekly summary is the latest seven UTC days including today and honors role and feature filters. Onboarding and family retention include all roles and features.",
                "Reliability counts and workflow abandonment are unavailable here; use the existing error monitoring for error investigations.",
            ],
        },
        "summary": {"current": _metrics(events, visits, start, end), "previous": _metrics(events, visits, previous_start, start)},
        "trend": _trend(events, visits, start, end),
        "features": _features(events, start, end, feature),
        "onboarding": _onboarding(families, all_events, start, end, observed_start),
        "retention": _retention(all_events, observed_start, today, state is not None),
        "friction": _friction(families, start, min(end, now), role, feature),
        "weekly_summary": {"start": week_start.date().isoformat(), "end": today.isoformat(), **weekly},
    }
