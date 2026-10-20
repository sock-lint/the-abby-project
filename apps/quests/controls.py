"""Explicit attempts and versioned future setup; account locks own every write."""
from copy import deepcopy
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Prefetch
from django.utils import timezone
from rest_framework.exceptions import NotFound

from .models import ChallengeActivity, ChallengeGoal, ChallengeOccurrence, ChallengePin, ChallengeSchedule, Quest, QuestDefinition
from .queries import active_system_definitions


def control_context(user):
    """One batched read shared by every result/history/receipt representation."""
    goals = list(ChallengeGoal.objects.filter(user=user, family_id=user.family_id).select_related(
        "catalog_definition", "movement_type",
    ).annotate(
        control_paid=Exists(ChallengeOccurrence.objects.filter(goal_id=OuterRef("pk"), awarded_at__isnull=False)),
        control_retried=Exists(ChallengeOccurrence.objects.filter(goal_id=OuterRef("pk"), retry_of__isnull=False)),
    ).prefetch_related(
        Prefetch("occurrences", queryset=ChallengeOccurrence.objects.filter(goal__is_catalog=True)
                 .order_by("-starts_at", "-pk")[:1], to_attr="control_occurrences"),
        Prefetch("schedules", queryset=ChallengeSchedule.objects.order_by("-starts_at", "-pk")[:2],
                 to_attr="control_schedules"),
    ))
    definitions = dict(QuestDefinition.objects.values_list("pk", "superseded_by_id"))
    from apps.rpg.models import ItemDefinition
    from .goals import _snapshot
    item_ids = {row["item_id"] for goal in goals if not goal.is_catalog and goal.repeat_weekly for row in goal.reward_items}
    items = ItemDefinition.objects.select_related("pet_species", "potion_type").in_bulk(item_ids)
    offered = {row.pk: row for row in active_system_definitions().select_related(
        "prerequisite_quest", "required_skill", "required_badge",
    )}
    ctx = {"goals": {row.pk: row for row in goals}, "groups": {}, "group_goals": {}, "legacy": {},
           "paid": set(), "retried": set(),
           "definitions": definitions, "offered": set(offered),
           "cooperative": {pk for pk, row in offered.items() if row.is_cooperative},
           "repeatable": {pk for pk, row in offered.items() if row.is_repeatable},
           "now": timezone.now()}
    ctx["base"] = {goal.pk: _snapshot(goal, item_catalog=items) for goal in goals
                   if not goal.is_catalog and goal.repeat_weekly}
    for goal in goals:
        if goal.is_catalog:
            key = identity(goal, ctx)
            ctx["groups"].setdefault(key, []).extend(goal.control_occurrences)
            ctx["group_goals"].setdefault(key, []).append(goal.pk)
            if goal.control_paid:
                ctx["paid"].add(key)
            if goal.control_retried:
                ctx["retried"].add(key)
    for definition_id, status in Quest.objects.filter(participants__user=user).values_list("definition_id", "status"):
        canonical = definitions.get(definition_id) or definition_id
        ctx["legacy"].setdefault(canonical, []).append(status)
    from .milestone_eligibility import has_milestone_gate, retry_milestone_states
    current_definitions = {identity(goal, ctx) for goal in goals if goal.is_catalog}
    gated = [row for pk, row in offered.items() if pk in current_definitions and has_milestone_gate(row)]
    ctx["milestone_retry"] = retry_milestone_states(
        user, gated, catalog=offered, identities=definitions, legacy=ctx["legacy"],
    )
    return ctx


def identity(goal, ctx):
    definition_id = goal.catalog_definition_id
    return (ctx["definitions"].get(definition_id) or definition_id) if definition_id else ("retired", goal.pk)


def retry_state(occurrence, ctx):
    goal = ctx["goals"].get(occurrence.goal_id, occurrence.goal)
    rows = ctx["groups"].get(identity(goal, ctx), [])
    latest = max(rows, key=lambda row: (row.starts_at, row.pk), default=occurrence)
    result = {"allowed": False, "reason": None, "latest_attempt_id": f"goal:{latest.pk}"}
    definition = goal.catalog_definition
    canonical = identity(goal, ctx)
    legacy = ctx["legacy"].get(canonical, [])
    if not goal.is_catalog:
        reason = "not_catalog"
        result["latest_attempt_id"] = None
    elif (goal.repeat_days or goal.repeat_weekly or (definition and definition.is_repeatable)
          or canonical in ctx["repeatable"]):
        reason = "repeatable"
    elif (definition and definition.is_cooperative) or canonical in ctx["cooperative"]:
        reason = "cooperative"
    elif definition is None or canonical not in ctx["offered"]:
        reason = "retired"
    elif canonical in ctx["paid"] or "completed" in legacy:
        reason = "already_awarded"
    elif occurrence.status == "closed":
        reason = "closed"
    elif "active" in legacy:
        reason = "legacy_active"
    elif any(row.status == "active" and row.ends_at > ctx["now"] for row in rows):
        reason = "not_expired" if occurrence.ends_at > ctx["now"] else "active_attempt"
    elif latest.pk != occurrence.pk:
        reason = "newer_attempt"
    elif occurrence.ends_at > ctx["now"]:
        reason = "not_expired"
    else:
        reason = "milestone_locked" if ctx["milestone_retry"].get(canonical) is False else None
    result.update(allowed=reason is None, reason=reason)
    return result


def lifetime_context(occurrence, user):
    goal = occurrence.goal
    if not goal.is_catalog or goal.repeat_days or goal.repeat_weekly:
        return None
    ctx = control_context(user)
    # Existing grandfathered duplicate promises keep their accepted policy.
    # An explicit retry is the transition to one lifetime reward per identity.
    return ctx if identity(goal, ctx) in ctx["retried"] else None


def lifetime_paid(occurrence, ctx):
    key = identity(occurrence.goal, ctx)
    return (key in ctx["paid"]
            or "completed" in ctx["legacy"].get(key, []))


def close_unpaid_attempts(occurrence, ctx, *, include_current=False):
    goals = ctx["group_goals"].get(identity(occurrence.goal, ctx), [])
    rows = ChallengeOccurrence.objects.filter(goal_id__in=goals, awarded_at__isnull=True)
    if not include_current:
        rows = rows.exclude(pk=occurrence.pk)
    rows.update(
        status="closed", closed_reason="reward_already_awarded",
    )


def _authorized_goal(actor, goal_id):
    from .goals import lock_user
    goal = ChallengeGoal.objects.select_related("user__family").filter(
        pk=goal_id, family_id=actor.family_id, user__family_id=actor.family_id,
        user__role="child", user__is_active=True,
    ).first()
    if goal is None or (actor.role != "parent" and (actor.role != "child" or goal.user_id != actor.pk)):
        raise NotFound("Challenge not found")
    members = {member.pk: lock_user(member) for member in sorted(
        {actor.pk: actor, goal.user_id: goal.user}.values(), key=lambda member: member.pk,
    )}
    fresh_actor, child = members[actor.pk], members[goal.user_id]
    if (not fresh_actor.is_active or not child.is_active or child.role != "child" or fresh_actor.family_id != child.family_id
            or child.family_id != goal.family_id or fresh_actor.role != actor.role):
        raise NotFound("Challenge not found")
    return ChallengeGoal.objects.select_related("user__family", "catalog_definition", "movement_type").get(pk=goal.pk)


@transaction.atomic
def retry_challenge(actor, occurrence_id):
    original = ChallengeOccurrence.objects.filter(pk=occurrence_id).first()
    if original is None:
        raise NotFound("Challenge not found")
    goal = _authorized_goal(actor, original.goal_id)
    original = ChallengeOccurrence.objects.select_related("goal__catalog_definition").get(pk=original.pk)
    successor = ChallengeOccurrence.objects.filter(retry_of=original).first()
    if successor is not None:
        return successor, False
    state = retry_state(original, control_context(goal.user))
    if not state["allowed"]:
        raise ValueError(state["reason"])
    zone = ZoneInfo(goal.timezone_name)
    start = timezone.now().astimezone(zone)
    duration = (original.ends_at.astimezone(zone).replace(tzinfo=None)
                - original.starts_at.astimezone(zone).replace(tzinfo=None))
    snapshot = deepcopy(original.snapshot)
    snapshot["_retry_after_activity_id"] = ChallengeActivity.objects.filter(user_id=goal.user_id).aggregate(
        last=Max("pk"),
    )["last"] or 0
    successor = ChallengeOccurrence.objects.create(
        goal=goal, retry_of=original, starts_at=start, ends_at=start + duration,
        snapshot=snapshot,
    )
    ChallengePin.objects.filter(user_id=goal.user_id, occurrence_id=original.pk).update(occurrence=successor)
    return successor, True


def week_start(goal, at):
    zone = ZoneInfo(goal.timezone_name)
    day = at.astimezone(zone).date()
    return datetime.combine(day - timedelta(days=day.weekday()), time.min, tzinfo=zone)


def effective_setup(goal, at, base=None, rows=None):
    from .goals import _snapshot
    if rows is None:
        row = goal.schedules.filter(starts_at__lte=at).order_by("-starts_at", "-pk").first()
    else:
        applicable = [row for row in rows if row.starts_at <= at]
        row = max(applicable, key=lambda value: (value.starts_at, value.pk), default=None)
    return (row.snapshot, row.paused) if row else (base if base is not None else _snapshot(goal), False)


def schedule_payload(goal, ctx=None):
    if goal.is_catalog or not goal.repeat_weekly:
        return None
    if ctx is not None:
        goal = ctx["goals"].get(goal.pk, goal)
    now = ctx["now"] if ctx is not None else timezone.now()
    current_start = week_start(goal, now)
    next_start = current_start + timedelta(days=7)
    base = ctx["base"].get(goal.pk) if ctx is not None else None
    rows = goal.control_schedules if ctx is not None else None
    _, current_paused = effective_setup(goal, current_start, base, rows)
    setup, next_paused = effective_setup(goal, next_start, base, rows)
    return {"revision": goal.schedule_revision, "paused": current_paused, "next_week": {
        "starts_at": next_start.isoformat(), "paused": next_paused,
        "name": setup["name"], "description": setup["description"], "metric": setup["metric"],
        "target": format(Decimal(setup["target"]).normalize(), "f"), "unit": setup["unit"],
        "trigger_type": next(iter(setup.get("filter", {}).get("allowed_triggers") or []), None),
        "movement_type_id": setup.get("movement_type_id"), "coin_reward": setup["coins"],
        "xp_reward": setup["xp"], "skill_tags": setup.get("skill_tags", []),
    }}


@transaction.atomic
def update_schedule(actor, goal_id, data):
    from types import SimpleNamespace
    from .goal_serializers import GoalWriteSerializer
    if actor.role != "parent":
        raise NotFound("Challenge not found")
    goal = _authorized_goal(actor, goal_id)
    if goal.is_catalog or not goal.repeat_weekly:
        raise ValueError("Only recurring parent goals have a future weekly setup.")
    if data["expected_revision"] != goal.schedule_revision:
        raise ValueError("The future setup changed. Refresh and review the saved version.")
    start = week_start(goal, timezone.now()) + timedelta(days=7)
    snapshot, paused = effective_setup(goal, start)
    snapshot = deepcopy(snapshot)
    changes = data.get("next_week", {})
    for field in ("name", "description", "target", "skill_tags"):
        if field in changes:
            snapshot[field] = str(changes[field]) if field == "target" else changes[field]
    for field, source in (("coins", "coin_reward"), ("xp", "xp_reward")):
        if source in changes:
            snapshot[field] = changes[source]
    validation = {"user_id": goal.user_id, "name": snapshot["name"], "description": snapshot["description"],
                  "metric": snapshot["metric"], "target": snapshot["target"], "unit": snapshot["unit"],
                  "trigger_type": next(iter(snapshot.get("filter", {}).get("allowed_triggers") or []), None), "period": "this_week",
                  "repeat_weekly": True, "coin_reward": snapshot["coins"], "xp_reward": snapshot["xp"],
                  "skill_tags": snapshot.get("skill_tags", [])}
    if goal.movement_type_id:
        validation["movement_type_id"] = goal.movement_type_id
    # Stopping future offers must remain possible when an old saved skill
    # was deleted. Resuming or changing setup still validates the full rule.
    if changes or data.get("paused") is not True:
        validator = GoalWriteSerializer(data=validation, context={"request": SimpleNamespace(user=goal.user)})
        validator.is_valid(raise_exception=True)
    ChallengeSchedule.objects.update_or_create(goal=goal, starts_at=start, defaults={
        "snapshot": snapshot, "paused": data.get("paused", paused),
    })
    goal.schedule_revision += 1
    goal.save(update_fields=["schedule_revision", "updated_at"])
    return {"goal_definition_id": goal.pk, "schedule": schedule_payload(goal)}
