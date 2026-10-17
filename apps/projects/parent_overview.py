"""Read-only, body-free household projection for Parent Today.

Queries are batched across the roster. Window limits keep goal previews and
recent accomplishments bounded per child without fetching historical bodies.
No enrollment, progress, awards or other application state changes on this read.
"""
from datetime import datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Count, Exists, F, OuterRef, Q, Sum, Window
from django.db.models.functions import RowNumber
from django.utils import timezone


def _latest(queryset, user_field, timestamp_field, *fields):
    return queryset.annotate(
        _rank=Window(
            expression=RowNumber(), partition_by=[F(user_field)],
            order_by=[F(timestamp_field).desc(), F("pk").desc()],
        ),
    ).filter(_rank=1).values(user_field, timestamp_field, *fields)


def recurring_goal_window(goal, at, fallback_zone):
    """Project the canonical challenge window without creating its occurrence.

    Accept the selected goal values so the overview and heartbeat can reuse
    the same read-only calculation. Match ``quests.goals._occurrence``: weekly
    takes precedence; rolling periods retain their saved local wall clock
    across daylight-saving changes rather than counting UTC-hour blocks.
    """
    if at < goal["starts_at"]:
        return None
    try:
        zone = ZoneInfo(goal["timezone_name"])
    except (ValueError, ZoneInfoNotFoundError):
        zone = fallback_zone
    if goal["repeat_weekly"]:
        day = at.astimezone(zone).date()
        monday = day - timedelta(days=day.weekday())
        return (
            datetime.combine(monday, time.min, tzinfo=zone),
            datetime.combine(monday + timedelta(days=7), time.min, tzinfo=zone),
        )
    start, end = goal["starts_at"], goal["ends_at"]
    if goal["repeat_days"]:
        local_start, local_at = start.astimezone(zone), at.astimezone(zone)
        elapsed = (local_at.replace(tzinfo=None) - local_start.replace(tzinfo=None)).total_seconds()
        cycle = int(elapsed // (goal["repeat_days"] * 86400))
        start = local_start + timedelta(days=cycle * goal["repeat_days"])
        end = start + timedelta(days=goal["repeat_days"])
    return start, end


def build_family_overview(parent):
    from apps.achievements.models import UserBadge
    from apps.chores.models import Chore, ChoreCompletion
    from apps.chores.services import ChoreService
    from apps.families.queries import children_in
    from apps.homework.models import HomeworkAssignment, HomeworkSubmission
    from apps.projects.models import Project
    from apps.quests.goals import family_zone
    from apps.quests.models import ChallengeGoal, ChallengeOccurrence
    from apps.timecards.models import TimeEntry

    now = timezone.now()
    zone = family_zone(parent) if parent.family_id else ZoneInfo("America/Phoenix")
    today = now.astimezone(zone).date()
    result = {"date": today.isoformat(), "timezone": str(zone), "children": []}
    if parent.role != "parent" or not parent.family_id:
        return result

    children = list(children_in(parent.family).only(
        "pk", "username", "display_name", "hourly_rate",
    ).order_by("username", "pk"))
    if not children:
        return result
    child_ids = [child.pk for child in children]
    rows = {child.pk: {
        "kid_id": child.pk, "name": child.display_label,
        "homework": {"due_today": 0, "overdue": 0, "pending_review": 0},
        "chores": {"remaining": 0, "pending_review": 0, "approved": 0, "total": 0},
        "parent_goals": {"active_count": 0, "items": []},
        "recent_accomplishment": None,
        "clocked_week": {"hours": 0, "earnings": 0},
    } for child in children}

    # Submission ownership must match the assignee even for legacy malformed
    # rows. Pending schoolwork waits on the parent, rather than staying overdue.
    submissions = HomeworkSubmission.objects.filter(
        assignment_id=OuterRef("pk"), user_id=OuterRef("assigned_to_id"),
    )
    homework = HomeworkAssignment.objects.filter(
        assigned_to_id__in=child_ids, is_active=True,
    ).annotate(
        awaiting=Exists(submissions.filter(status="pending")),
        approved=Exists(submissions.filter(status="approved")),
    ).values("assigned_to_id").annotate(
        due_today=Count("pk", filter=Q(due_date=today, awaiting=False, approved=False)),
        overdue=Count("pk", filter=Q(due_date__lt=today, awaiting=False, approved=False)),
        pending_review=Count("pk", filter=Q(awaiting=True)),
    )
    for item in homework:
        rows[item["assigned_to_id"]]["homework"] = {
            key: item[key] for key in ("due_today", "overdue", "pending_review")
        }

    monday = today - timedelta(days=today.weekday())
    chores = list(Chore.objects.filter(
        family_id=parent.family_id, is_active=True, pending_parent_review=False,
    ).filter(Q(assigned_to_id__in=child_ids) | Q(assigned_to__isnull=True)))
    # Distinct status/period tuples bound the transfer to current chores rather
    # than loading every historical completion. One-time work remains pending
    # until reviewed; old approved one-time work leaves the current checklist.
    completions = ChoreCompletion.objects.filter(
        chore_id__in=[chore.pk for chore in chores], user_id__in=child_ids,
    ).exclude(status="rejected").filter(
        Q(completed_date__in=[today, monday]) | Q(chore__recurrence="one_time"),
    ).order_by().values_list("user_id", "chore_id", "status", "completed_date").distinct()
    completion_map = {}
    for user_id, chore_id, status, completed_date in completions:
        completion_map.setdefault((user_id, chore_id), []).append((status, completed_date))
    for child in children:
        summary = rows[child.pk]["chores"]
        for chore in chores:
            if chore.assigned_to_id not in (None, child.pk) or not ChoreService.is_active_this_week(chore, today):
                continue
            saved = completion_map.get((child.pk, chore.pk), [])
            if chore.recurrence == "one_time":
                if any(status == "approved" and day != today for status, day in saved):
                    continue
                status = "approved" if any(status == "approved" for status, _ in saved) else (
                    "pending" if saved else None
                )
            else:
                period = monday if chore.recurrence == "weekly" else today
                status = next((status for status, day in saved if day == period), None)
            summary["total"] += 1
            summary[{"pending": "pending_review", "approved": "approved"}.get(status, "remaining")] += 1

    parent_occurrences = ChallengeOccurrence.objects.filter(
        goal__user_id__in=child_ids, goal__family_id=parent.family_id,
        goal__is_catalog=False,
    )
    goals = parent_occurrences.filter(
        status="active", starts_at__lte=now, ends_at__gt=now,
    ).annotate(
        _count=Window(expression=Count("pk"), partition_by=[F("goal__user_id")]),
        _rank=Window(expression=RowNumber(), partition_by=[F("goal__user_id")],
                     order_by=[F("ends_at").asc(), F("pk").asc()]),
    ).filter(_rank__lte=3).values(
        "pk", "goal__user_id", "goal__name", "goal__target", "goal__unit",
        "snapshot", "progress", "ends_at", "_count",
    ).order_by("ends_at", "pk")
    for goal in goals:
        summary = rows[goal["goal__user_id"]]["parent_goals"]
        summary["active_count"] = goal["_count"]
        frozen = goal["snapshot"]
        summary["items"].append({
            "id": f"goal:{goal['pk']}", "name": frozen.get("name", goal["goal__name"]),
            "progress": str(goal["progress"]), "target": str(frozen.get("target", goal["goal__target"])),
            "unit": frozen.get("unit", goal["goal__unit"]), "ends_at": goal["ends_at"].isoformat(),
        })

    # A recurring successor is normally materialized by challenge reads or the
    # child's next saved activity. Parent Today must still show this period's
    # assignment before either happens. Project an unpaid, zero-progress
    # preview without enrolling, inserting an occurrence or awarding anything.
    # Any existing current occurrence (including completed) suppresses it.
    current_occurrence = ChallengeOccurrence.objects.filter(
        goal_id=OuterRef("pk"), starts_at__lte=now, ends_at__gt=now,
    )
    recurring = ChallengeGoal.objects.filter(
        user_id__in=child_ids, family_id=parent.family_id, is_catalog=False,
        starts_at__lte=now,
    ).filter(Q(repeat_weekly=True) | Q(repeat_days__gt=0)).annotate(
        _current=Exists(current_occurrence),
    ).filter(_current=False).annotate(
        _count=Window(expression=Count("pk"), partition_by=[F("user_id")]),
        _rank=Window(expression=RowNumber(), partition_by=[F("user_id")], order_by=F("pk").asc()),
    ).filter(_rank__lte=3).values(
        "pk", "user_id", "name", "target", "unit", "timezone_name", "_count",
        "starts_at", "ends_at", "repeat_weekly", "repeat_days",
    )
    counted_recurring = set()
    for goal in recurring:
        summary = rows[goal["user_id"]]["parent_goals"]
        if goal["user_id"] not in counted_recurring:
            summary["active_count"] += goal["_count"]
            counted_recurring.add(goal["user_id"])
        starts_at, ends_at = recurring_goal_window(goal, now, zone)
        summary["items"].append({
            "id": f"preview:{goal['pk']}:{starts_at.date().isoformat()}", "preview": True,
            "name": goal["name"], "progress": "0", "target": str(goal["target"]),
            "unit": goal["unit"], "ends_at": ends_at.astimezone(dt_timezone.utc).isoformat(),
        })
    for row in rows.values():
        row["parent_goals"]["items"] = sorted(
            row["parent_goals"]["items"], key=lambda goal: (datetime.fromisoformat(goal["ends_at"]), goal["id"]),
        )[:3]

    week_start = datetime.combine(monday, time.min, tzinfo=zone)
    week_end = datetime.combine(monday + timedelta(days=7), time.min, tzinfo=zone)
    clocked = TimeEntry.objects.filter(
        user_id__in=child_ids, status="completed", clock_in__gte=week_start,
        clock_in__lt=week_end, project__in=Project.objects.work_projects(),
    ).order_by().values("user_id").annotate(minutes=Sum("duration_minutes"))
    rates = {child.pk: child.hourly_rate for child in children}
    for item in clocked:
        hours = round((item["minutes"] or 0) / 60, 1)
        rows[item["user_id"]]["clocked_week"] = {
            "hours": hours, "earnings": round(hours * float(rates[item["user_id"]]), 2),
        }

    # Only allowlisted confirmed source metadata may be featured. Never read
    # journal entries, submission notes, activity context, or arbitrary summaries.
    recent = now - timedelta(days=7)
    sources = [
        ("badge", _latest(UserBadge.objects.filter(
            user_id__in=child_ids, earned_at__gte=recent, earned_at__lte=now,
        ), "user_id", "earned_at", "badge__name"), "user_id", "earned_at", "badge__name"),
        ("homework", _latest(HomeworkSubmission.objects.filter(
            user_id__in=child_ids, assignment__assigned_to_id=F("user_id"),
            status="approved", decided_at__gte=recent, decided_at__lte=now,
        ), "user_id", "decided_at", "assignment__title"), "user_id", "decided_at", "assignment__title"),
        ("chore", _latest(ChoreCompletion.objects.filter(
            user_id__in=child_ids, chore__family_id=parent.family_id,
            status="approved", decided_at__gte=recent, decided_at__lte=now,
        ), "user_id", "decided_at", "chore__title"), "user_id", "decided_at", "chore__title"),
        ("goal", _latest(parent_occurrences.filter(
            status="completed", completed_at__gte=recent, completed_at__lte=now,
        ), "goal__user_id", "completed_at", "snapshot", "goal__name"),
         "goal__user_id", "completed_at", "goal__name"),
    ]
    for kind, items, user_key, time_key, title_key in sources:
        for item in items:
            row = rows[item[user_key]]
            candidate = {
                "kind": kind,
                "title": item["snapshot"].get("name", item[title_key]) if kind == "goal" else item[title_key],
                "occurred_at": item[time_key].isoformat(),
            }
            current = row["recent_accomplishment"]
            if current is None or item[time_key] > datetime.fromisoformat(current["occurred_at"]):
                row["recent_accomplishment"] = candidate

    result["children"] = list(rows.values())
    return result
