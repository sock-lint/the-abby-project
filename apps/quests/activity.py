"""Resolve persisted work to retryable challenge facts, without private prose."""
import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def household_timezone(user):
    try:
        return ZoneInfo(user.family.timezone)
    except (ZoneInfoNotFoundError, AttributeError, ValueError):
        return timezone.get_default_timezone()


def _tags(manager, weight="xp_weight"):
    return [{"skill_id": tag.skill_id, "xp_weight": getattr(tag, weight, 1)} for tag in manager.all()]


def _homework_work_day(submission):
    snapshot = submission.timing_snapshot
    if (isinstance(snapshot, dict) and snapshot.get("version") == 1
            and snapshot.get("schedule") == "homework"):
        try:
            return date.fromisoformat(snapshot.get("submitted_on"))
        except (TypeError, ValueError):
            pass
    # Older homework used the configured Django day when submitted. Its
    # original household timezone was not saved; today's family/request zone
    # cannot recover it. Existing challenge facts keep their already saved day.
    return timezone.localdate(submission.created_at, timezone=timezone.get_default_timezone())


def resolve_activity(user, trigger_type, context):
    """Only accepted source records count; incoming arbitrary quantities do not."""
    trigger = str(trigger_type)
    sources = {
        "clock_out": ("time_entry_id", "timecards.TimeEntry", {"user": user, "status": "completed"}),
        "chore_complete": ("completion_id", "chores.ChoreCompletion", {"user": user, "status": "approved"}),
        "homework_complete": ("submission_id", "homework.HomeworkSubmission", {"user": user, "status": "approved"}),
        "homework_created": ("assignment_id", "homework.HomeworkAssignment", {"assigned_to": user, "is_active": True}),
        "habit_log": ("habit_log_id", "habits.HabitLog", {"user": user, "direction": 1}),
        "movement_session": ("session_id", "movement.MovementSession", {"user": user}),
        "project_complete": ("project_id", "projects.Project", {"assigned_to": user, "status": "completed"}),
        "milestone_complete": ("milestone_id", "projects.ProjectMilestone", {"project__assigned_to": user, "is_completed": True}),
        "creation_logged": ("creation_id", "creations.Creation", {"user": user}),
        "journal_entry": ("entry_id", "chronicle.ChronicleEntry", {"user": user, "kind": "journal"}),
        "savings_goal_complete": ("savings_goal_id", "projects.SavingsGoal", {"user": user, "completed_at__isnull": False}),
        "expedition_returned": ("expedition_id", "pets.MountExpedition", {"mount__user": user, "status": "claimed"}),
        "reading_logged": ("reading_reward_id", "reading.ReadingDailyReward", {
            "user": user, "awarded_at__isnull": False,
        }),
    }
    if trigger not in sources:
        return None
    key, model_name, filters = sources[trigger]
    pk = context.get(key)
    if not pk:
        return None
    source = apps.get_model(model_name).objects.filter(pk=pk, **filters).first()
    if source is None:
        return None
    safe_context = {}
    occurred_at = getattr(source, "created_at", timezone.now())
    occurred_on = getattr(source, "occurred_on", None)
    if trigger == "clock_out":
        occurred_at = source.clock_out
        safe_context = {"project_id": source.project_id, "duration_minutes": source.duration_minutes,
                        "hours": source.duration_minutes / 60, "skill_tags": _tags(source.project.skill_tags)}
    elif trigger == "chore_complete":
        occurred_at = source.decided_at or occurred_at
        occurred_on = source.completed_date
        safe_context = {"chore_id": source.chore_id, "skill_tags": _tags(source.chore.skill_tags)}
    elif trigger == "homework_complete":
        occurred_on = _homework_work_day(source)
        occurred_at = source.decided_at or occurred_at
        safe_context = {"assignment_id": source.assignment_id, "on_time": source.timeliness in ("early", "on_time"),
                        "skill_tags": _tags(source.assignment.skill_tags, "xp_amount")}
    elif trigger == "homework_created":
        safe_context = {"assignment_id": source.pk}
    elif trigger == "habit_log":
        safe_context = {"habit_id": source.habit_id, "skill_tags": _tags(source.habit.skill_tags)}
    elif trigger == "movement_session":
        safe_context = {"movement_type_id": source.movement_type_id, "duration_minutes": source.duration_minutes,
                        "distance_meters": str(source.distance_meters) if source.distance_meters is not None else None,
                        "skill_tags": _tags(source.movement_type.skill_tags)}
    elif trigger == "project_complete":
        occurred_at = source.completed_at or occurred_at
        safe_context = {"project_id": source.pk, "skill_tags": _tags(source.skill_tags)}
    elif trigger == "milestone_complete":
        occurred_at = source.completed_at or occurred_at
        safe_context = {"project_id": source.project_id, "milestone_id": source.pk,
                        "skill_tags": _tags(source.project.skill_tags)}
    elif trigger == "savings_goal_complete":
        occurred_at = source.completed_at
        safe_context = {"savings_goal_id": source.pk}
    elif trigger == "expedition_returned":
        occurred_at = source.claimed_at or occurred_at
    elif trigger == "reading_logged":
        # The earned daily receipt is immutable even if its source log is
        # corrected or deleted. Arbitrary session IDs and minute claims do
        # not establish another opportunity or expose private reading prose.
        occurred_at = source.awarded_at
        occurred_on = source.day
    # Keep the actual saved timestamp for enrollment/cutover, alongside the
    # source's calendar date for household weekly goals and late approvals.
    zone = household_timezone(user)
    if occurred_on is None:
        occurred_on = timezone.localdate(occurred_at, timezone=zone)
    return {"source_type": trigger, "source_id": str(source.pk), "trigger_type": trigger,
            "occurred_at": occurred_at, "occurred_on": occurred_on, "context": safe_context}


@transaction.atomic
def freeze_catalog_eligibility(user, trigger_type, context, *, eligible):
    """Freeze the source service's daily-counter decision before any evaluator.

    This attestation is internal: the normal source resolver discards incoming
    eligibility flags. Facts without an attestation cannot earn capped catalog
    credit, while parent-authored goals still count their saved work.
    """
    from .models import ChallengeActivity
    if str(trigger_type) not in {"homework_created", "creation_logged"} or user.role != "child":
        return
    get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    data = resolve_activity(user, trigger_type, context)
    if data is None:
        return
    identity = {field: data[field] for field in ("source_type", "source_id", "trigger_type")}
    ChallengeActivity.objects.get_or_create(user=user, **identity, defaults={
        "occurred_at": data["occurred_at"], "occurred_on": data["occurred_on"],
        "context": {**data["context"], "catalog_eligible": bool(eligible)},
    })


@transaction.atomic
def record_activity(user, trigger_type, context=None):
    """Persist before evaluation so a failed downstream step stays retryable."""
    from .models import ChallengeActivity
    data = resolve_activity(user, trigger_type, context or {})
    if data is None or user.role != "child":
        return {"goals": [], "daily_bonus": None}
    get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    identity = {field: data[field] for field in ("source_type", "source_id", "trigger_type")}
    activity, _ = ChallengeActivity.objects.get_or_create(user=user, **identity, defaults={
        key: data[key] for key in ("occurred_at", "occurred_on", "context")
    })
    try:
        with transaction.atomic():
            from .goals import ingest_activity
            from .daily_bonus import process_daily_bonus
            result = ingest_activity(user, **data)
            bonus = process_daily_bonus(user, result["activity"])
            activity = result["activity"]
            previous_receipt = activity.context.get("_receipt")
            receipt = previous_receipt or {"id": f"activity:{activity.pk}", "goals": result["goals"], "daily_bonus": bonus}
            if not previous_receipt and (result["goals"] or bonus):
                activity.context = {**activity.context, "_receipt": receipt}
                activity.save(update_fields=["context"])
            return {"goals": receipt["goals"], "daily_bonus": receipt["daily_bonus"],
                    "challenge_receipts": [receipt] if receipt["goals"] or receipt["daily_bonus"] else []}
    except Exception:
        logger.exception("Automatic challenge processing pending for activity=%s user=%s", activity.pk, user.pk)
        # The savepoint rolled back any partial completion/payout. The fact
        # remains pending and a bounded repair can resume only this evaluator.
        activity.processed_at = None
        activity.save(update_fields=["processed_at"])
        return {"goals": [], "daily_bonus": None}


def retry_pending_activity(user=None, limit=100):
    from .models import ChallengeActivity
    from .goals import ingest_activity
    from .daily_bonus import process_daily_bonus
    query = ChallengeActivity.objects.filter(
        processed_at__isnull=True, voided=False, user__is_active=True, user__role="child",
    ).select_related("user__family")
    if user is not None:
        query = query.filter(user=user)
    repaired = 0
    for activity in query.order_by("pk")[:max(1, min(limit, 1000))]:
        try:
            with transaction.atomic():
                get_user_model().objects.select_for_update(no_key=True).get(pk=activity.user_id)
                result = ingest_activity(activity.user, source_type=activity.source_type, source_id=activity.source_id,
                                         trigger_type=activity.trigger_type, occurred_at=activity.occurred_at,
                                         occurred_on=activity.occurred_on, context=activity.context)
                bonus = process_daily_bonus(activity.user, result["activity"])
                fact = result["activity"]
                if not fact.context.get("_receipt") and (result["goals"] or bonus):
                    fact.context = {**fact.context, "_receipt": {"id": f"activity:{fact.pk}",
                                    "goals": result["goals"], "daily_bonus": bonus}}
                    fact.save(update_fields=["context"])
                repaired += 1
        except Exception:
            # Keep a failed fact pending without starving other families in
            # this bounded repair batch. Its own savepoint rolls back awards.
            logger.exception("Challenge repair remains pending for activity=%s user=%s", activity.pk, activity.user_id)
    return repaired


def backfill_goal_activity(goal):
    """Explicit current-period parent goals can count already saved work.

    This only records facts. The caller attaches them to the newly created
    goal, without replaying historical catalog, daily, drop or XP awards.
    """
    from .models import ChallengeActivity
    zone = ZoneInfo(goal.timezone_name)
    start_day = timezone.localdate(goal.starts_at, timezone=zone)
    end_day = timezone.localdate(goal.ends_at, timezone=zone)
    # Homework can have been submitted in a different household timezone.
    # Bound the scan to this calendar range plus one UTC day on each side,
    # covering every source offset, then compare its frozen work day below.
    homework_start = datetime.combine(start_day - timedelta(days=1), time.min, tzinfo=UTC)
    homework_end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=UTC)
    allowed = goal.trigger_filter.get("allowed_triggers") or []
    scans = {
        "movement_session": ("movement.MovementSession", "session_id", {
            "user": goal.user, "occurred_on__gte": start_day, "occurred_on__lt": end_day}),
        "chore_complete": ("chores.ChoreCompletion", "completion_id", {
            "user": goal.user, "status": "approved", "completed_date__gte": start_day, "completed_date__lt": end_day}),
        "homework_complete": ("homework.HomeworkSubmission", "submission_id", {
            "user": goal.user, "status": "approved", "created_at__gte": homework_start, "created_at__lt": homework_end}),
        "clock_out": ("timecards.TimeEntry", "time_entry_id", {
            "user": goal.user, "status": "completed", "clock_out__gte": goal.starts_at, "clock_out__lt": goal.ends_at}),
        "homework_created": ("homework.HomeworkAssignment", "assignment_id", {
            "assigned_to": goal.user, "is_active": True, "created_at__gte": goal.starts_at, "created_at__lt": goal.ends_at}),
        "habit_log": ("habits.HabitLog", "habit_log_id", {
            "user": goal.user, "direction": 1, "created_at__gte": goal.starts_at, "created_at__lt": goal.ends_at}),
        "project_complete": ("projects.Project", "project_id", {
            "assigned_to": goal.user, "status": "completed", "completed_at__gte": goal.starts_at, "completed_at__lt": goal.ends_at}),
        "milestone_complete": ("projects.ProjectMilestone", "milestone_id", {
            "project__assigned_to": goal.user, "is_completed": True, "completed_at__gte": goal.starts_at, "completed_at__lt": goal.ends_at}),
        "creation_logged": ("creations.Creation", "creation_id", {
            "user": goal.user, "occurred_on__gte": start_day, "occurred_on__lt": end_day}),
        "journal_entry": ("chronicle.ChronicleEntry", "entry_id", {
            "user": goal.user, "kind": "journal", "occurred_on__gte": start_day, "occurred_on__lt": end_day}),
        "savings_goal_complete": ("projects.SavingsGoal", "savings_goal_id", {
            "user": goal.user, "completed_at__gte": goal.starts_at, "completed_at__lt": goal.ends_at}),
        "reading_logged": ("reading.ReadingDailyReward", "reading_reward_id", {
            "user": goal.user, "awarded_at__isnull": False, "day__gte": start_day, "day__lt": end_day}),
    }
    for trigger in allowed:
        if trigger not in scans:
            continue
        model, key, filters = scans[trigger]
        if trigger == "movement_session" and goal.movement_type_id:
            filters["movement_type_id"] = goal.movement_type_id
        for source in apps.get_model(model).objects.filter(**filters).iterator(chunk_size=100):
            data = resolve_activity(goal.user, trigger, {key: source.pk})
            if trigger == "homework_complete" and data and not start_day <= data["occurred_on"] < end_day:
                continue
            if data:
                identity = {field: data[field] for field in ("source_type", "source_id", "trigger_type")}
                ChallengeActivity.objects.get_or_create(user=goal.user, **identity, defaults={
                    key: data[key] for key in ("occurred_at", "occurred_on", "context")
                } | {"processed_at": timezone.now()})
