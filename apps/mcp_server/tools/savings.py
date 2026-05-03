"""Savings goal MCP tools."""
from __future__ import annotations

from typing import Any

from apps.projects.models import SavingsGoal

from ..context import get_current_user, resolve_target_user
from ..errors import MCPNotFoundError, safe_tool
from ..schemas import (
    CreateSavingsGoalIn,
    DeleteSavingsGoalIn,
    ListSavingsGoalsIn,
    UpdateSavingsGoalIn,
)
from ..server import tool
from ..shapes import savings_goal_to_dict


@tool()
@safe_tool
def list_savings_goals(params: ListSavingsGoalsIn) -> dict[str, Any]:
    """List a user's savings goals (children forced to self)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)

    qs = SavingsGoal.objects.filter(user=target)
    if not params.include_completed:
        qs = qs.filter(is_completed=False)
    return {"goals": [savings_goal_to_dict(g) for g in qs.order_by("-created_at")]}


@tool()
@safe_tool
def create_savings_goal(params: CreateSavingsGoalIn) -> dict[str, Any]:
    """Create a savings goal for the current user."""
    user = get_current_user()
    goal = SavingsGoal.objects.create(
        user=user,
        title=params.title,
        target_amount=params.target_amount,
        icon=params.icon,
    )
    return savings_goal_to_dict(goal)


@tool()
@safe_tool
def update_savings_goal(params: UpdateSavingsGoalIn) -> dict[str, Any]:
    """Edit a savings goal's metadata (owner or parent only).

    Audit C8: parent path scopes by family. Children stay scoped to their
    own goals.
    """
    user = get_current_user()
    qs = SavingsGoal.objects.all()
    if user.role == "child":
        qs = qs.filter(user=user)
    else:
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            raise MCPNotFoundError(f"Savings goal {params.goal_id} not found.")
        qs = qs.filter(user__family_id=family_id)
    try:
        goal = qs.get(pk=params.goal_id)
    except SavingsGoal.DoesNotExist:
        raise MCPNotFoundError(f"Savings goal {params.goal_id} not found.")
    data = params.model_dump(exclude={"goal_id"}, exclude_unset=True)
    for field, value in data.items():
        setattr(goal, field, value)
    goal.save()
    return savings_goal_to_dict(goal)


@tool()
@safe_tool
def delete_savings_goal(params: DeleteSavingsGoalIn) -> dict[str, Any]:
    """Delete a savings goal (owner or parent only).

    Audit C8: parent path scopes by family.
    """
    user = get_current_user()
    qs = SavingsGoal.objects.all()
    if user.role == "child":
        qs = qs.filter(user=user)
    else:
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            raise MCPNotFoundError(f"Savings goal {params.goal_id} not found.")
        qs = qs.filter(user__family_id=family_id)
    try:
        goal = qs.get(pk=params.goal_id)
    except SavingsGoal.DoesNotExist:
        raise MCPNotFoundError(f"Savings goal {params.goal_id} not found.")
    goal_id = goal.pk
    goal.delete()
    return {"goal_id": goal_id, "deleted": True}
