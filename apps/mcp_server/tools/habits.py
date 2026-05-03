"""Habit MCP tools (Tier 2.3).

Habits are trackable micro-behaviors distinct from chores — no parent
approval, multiple taps/day allowed, no dollar rewards. The ``log_habit``
tool fires the RPG game loop (streaks, drops, quest progress) for the
tapping user.

Both parents and children can create habits for themselves; parents
additionally can create (and edit/delete) habits for any child via
``user_id``.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.habits.models import Habit, HabitSkillTag
from apps.habits.services import HabitService
from apps.rpg.services import GameLoopService

from ..context import (
    get_current_user, get_in_family, require_parent, resolve_child_in_family,
)
from ..errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
    safe_tool,
)
from ..schemas import (
    CreateHabitIn,
    DeleteHabitIn,
    SetHabitSkillTagsIn,
    GetHabitIn,
    ListHabitsIn,
    LogHabitIn,
    UpdateHabitIn,
)
from ..server import tool
from ..shapes import to_plain


def _habit_to_dict(habit: Habit) -> dict[str, Any]:
    from apps.habits.serializers import HabitSerializer

    return to_plain(HabitSerializer(habit).data)


@tool()
@safe_tool
def list_habits(params: ListHabitsIn) -> dict[str, Any]:
    """List habits. Parents see their family; children see their own only.

    Audit C8: parent path was previously unscoped — returned every
    household's habits to every parent in the deployment.
    """
    user = get_current_user()
    qs = Habit.objects.all()
    if user.role == "child":
        qs = qs.filter(user=user)
    else:
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            return {"habits": []}
        qs = qs.filter(user__family_id=family_id)
        if params.user_id is not None:
            qs = qs.filter(user_id=params.user_id)
    qs = qs.order_by("name")[: params.limit]
    return {"habits": [_habit_to_dict(h) for h in qs]}


@tool()
@safe_tool
def get_habit(params: GetHabitIn) -> dict[str, Any]:
    """Get a single habit with its current strength + color.

    Audit C8: family-scope for parents; self-scope for children.
    """
    user = get_current_user()
    qs = Habit.objects.all()
    if user.role == "child":
        qs = qs.filter(user=user)
    else:
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
        qs = qs.filter(user__family_id=family_id)
    try:
        habit = qs.get(pk=params.habit_id)
    except Habit.DoesNotExist:
        raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
    return _habit_to_dict(habit)


@tool()
@safe_tool
def create_habit(params: CreateHabitIn) -> dict[str, Any]:
    """Create a new habit.

    Children can only create for themselves (``user_id`` must be None or
    their own id). Parents can create for themselves or any child by
    passing ``user_id``.
    """
    user = get_current_user()
    target = user
    if params.user_id is not None and params.user_id != user.id:
        if user.role != "parent":
            raise MCPPermissionDenied(
                "Children can only create habits for themselves.",
            )
        # Audit C3: family-scope the on-behalf path. Without this, a parent
        # in family A could create habits in family B's children's profiles.
        # ``resolve_child_in_family`` also pins ``role="child"`` so a parent
        # can't author a habit on another parent.
        target = resolve_child_in_family(user, params.user_id)
    habit = Habit.objects.create(
        name=params.name,
        icon=params.icon,
        habit_type=params.habit_type,
        xp_reward=params.xp_reward,
        max_taps_per_day=params.max_taps_per_day,
        user=target,
        created_by=user,
    )
    return _habit_to_dict(habit)


@tool()
@safe_tool
def update_habit(params: UpdateHabitIn) -> dict[str, Any]:
    """Edit a habit. Parent-only (mirrors REST).

    Audit C8: family-scope so a parent can't edit another family's habits.
    """
    parent = require_parent()
    habit = get_in_family(
        Habit, params.habit_id, actor=parent, family_path="user__family",
    )
    data = params.model_dump(exclude={"habit_id"}, exclude_unset=True)
    for field, value in data.items():
        setattr(habit, field, value)
    habit.save()
    return _habit_to_dict(habit)


@tool()
@safe_tool
def delete_habit(params: DeleteHabitIn) -> dict[str, Any]:
    """Delete a habit (parent-only, mirrors REST).

    Audit C8: family-scope so a parent can't delete another family's habits.
    """
    parent = require_parent()
    habit = get_in_family(
        Habit, params.habit_id, actor=parent, family_path="user__family",
    )
    habit_id = habit.pk
    habit.delete()
    return {"habit_id": habit_id, "deleted": True}


@tool()
@safe_tool
def log_habit(params: LogHabitIn) -> dict[str, Any]:
    """Tap a habit +1 (positive) or -1 (negative).

    Can only be logged by the habit's owner. Positive taps fire the RPG
    game loop (streaks, drops, quest progress).

    Audit C8: scope to caller-owned habits up front so a non-owner can't
    even probe habit existence by id.
    """
    user = get_current_user()
    try:
        habit = Habit.objects.get(pk=params.habit_id, user=user)
    except Habit.DoesNotExist:
        raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
    try:
        result = HabitService.log_tap(user, habit, params.amount)
    except ValueError as exc:
        raise MCPValidationError(str(exc))

    game_event = None
    if params.amount == 1:
        from apps.rpg.constants import TriggerType
        game_event = GameLoopService.on_task_completed(
            user, TriggerType.HABIT_LOG, {"habit_id": habit.pk},
        )
    return to_plain({**result, "game_event": game_event})


@tool()
@safe_tool
def set_habit_skill_tags(params: SetHabitSkillTagsIn) -> dict[str, Any]:
    """Replace the skill tags on a habit (parent-only for other users'
    habits; child can tag their own).

    Each positive tap splits the habit's ``xp_reward`` pool across the
    tagged skills by ``xp_weight``. Passing an empty list removes tags
    and makes positive taps skill-neutral (the XP silently drops, which
    was the pre-2026-04-21 behavior for every habit).
    """
    from apps.achievements.models import Skill

    # Audit C8: parent path scopes by family; child path scopes to self.
    user = get_current_user()
    qs = Habit.objects.all()
    if user.role == "child":
        qs = qs.filter(user=user)
    else:
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
        qs = qs.filter(user__family_id=family_id)
    try:
        habit = qs.get(pk=params.habit_id)
    except Habit.DoesNotExist:
        raise MCPNotFoundError(f"Habit {params.habit_id} not found.")

    skill_ids = [t.skill_id for t in params.skill_tags]
    known = set(Skill.objects.filter(id__in=skill_ids).values_list("id", flat=True))
    missing = [s for s in skill_ids if s not in known]
    if missing:
        raise MCPValidationError(f"Unknown skill IDs: {missing}")

    with transaction.atomic():
        HabitSkillTag.objects.filter(habit=habit).delete()
        HabitSkillTag.objects.bulk_create([
            HabitSkillTag(habit=habit, skill_id=t.skill_id, xp_weight=t.xp_weight)
            for t in params.skill_tags
        ])
    habit.refresh_from_db()
    return _habit_to_dict(habit)
