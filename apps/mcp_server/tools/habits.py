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

from apps.habits.models import Habit
from apps.habits.services import HabitService
from apps.accounts.models import User
from apps.rpg.services import GameLoopService

from ..context import get_current_user, require_parent
from ..errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
    safe_tool,
)
from ..schemas import (
    CreateHabitIn,
    DeleteHabitIn,
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
    """List habits. Parents see all; children see their own only."""
    user = get_current_user()
    qs = Habit.objects.all()
    if user.role == "child":
        qs = qs.filter(user=user)
    elif params.user_id is not None:
        qs = qs.filter(user_id=params.user_id)
    qs = qs.order_by("name")[: params.limit]
    return {"habits": [_habit_to_dict(h) for h in qs]}


@tool()
@safe_tool
def get_habit(params: GetHabitIn) -> dict[str, Any]:
    """Get a single habit with its current strength + color."""
    user = get_current_user()
    try:
        habit = Habit.objects.get(pk=params.habit_id)
    except Habit.DoesNotExist:
        raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
    if user.role != "parent" and habit.user_id != user.id:
        raise MCPPermissionDenied("Habit is not yours.")
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
        try:
            target = User.objects.get(pk=params.user_id)
        except User.DoesNotExist:
            raise MCPValidationError(
                f"user_id {params.user_id} does not match any user.",
            )
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
    """Edit a habit. Parent-only (mirrors REST)."""
    require_parent()
    try:
        habit = Habit.objects.get(pk=params.habit_id)
    except Habit.DoesNotExist:
        raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
    data = params.model_dump(exclude={"habit_id"}, exclude_unset=True)
    for field, value in data.items():
        setattr(habit, field, value)
    habit.save()
    return _habit_to_dict(habit)


@tool()
@safe_tool
def delete_habit(params: DeleteHabitIn) -> dict[str, Any]:
    """Delete a habit (parent-only, mirrors REST)."""
    require_parent()
    try:
        habit = Habit.objects.get(pk=params.habit_id)
    except Habit.DoesNotExist:
        raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
    habit_id = habit.pk
    habit.delete()
    return {"habit_id": habit_id, "deleted": True}


@tool()
@safe_tool
def log_habit(params: LogHabitIn) -> dict[str, Any]:
    """Tap a habit +1 (positive) or -1 (negative).

    Can only be logged by the habit's owner. Positive taps fire the RPG
    game loop (streaks, drops, quest progress).
    """
    user = get_current_user()
    try:
        habit = Habit.objects.get(pk=params.habit_id)
    except Habit.DoesNotExist:
        raise MCPNotFoundError(f"Habit {params.habit_id} not found.")
    if habit.user_id != user.id:
        raise MCPPermissionDenied("You can only log your own habits.")
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
