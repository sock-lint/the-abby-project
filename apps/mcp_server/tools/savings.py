"""Savings goal MCP tools."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import SavingsGoal

from ..context import get_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    ContributeToGoalIn,
    CreateSavingsGoalIn,
    DeleteSavingsGoalIn,
    ListSavingsGoalsIn,
    UpdateSavingsGoalIn,
)
from ..server import tool
from ..shapes import savings_goal_to_dict


def _resolve_target(user, requested_id: int | None) -> User:
    if requested_id is None or requested_id == user.id:
        return user
    if user.role != "parent":
        raise MCPPermissionDenied("Children can only view their own savings goals.")
    try:
        return User.objects.get(pk=requested_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {requested_id} not found.")


@tool()
@safe_tool
def list_savings_goals(params: ListSavingsGoalsIn) -> dict[str, Any]:
    """List a user's savings goals (children forced to self)."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

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
def contribute_to_goal(params: ContributeToGoalIn) -> dict[str, Any]:
    """Add to the current amount on a savings goal.

    Marks the goal complete when ``current_amount`` reaches ``target_amount``.
    Children may only contribute to their own goals.
    """
    user = get_current_user()
    try:
        goal = SavingsGoal.objects.get(pk=params.goal_id)
    except SavingsGoal.DoesNotExist:
        raise MCPNotFoundError(f"Savings goal {params.goal_id} not found.")

    if goal.user_id != user.id and user.role != "parent":
        raise MCPPermissionDenied("Cannot contribute to another user's goal.")

    goal.current_amount = Decimal(str(goal.current_amount)) + params.amount
    if goal.current_amount >= goal.target_amount and not goal.is_completed:
        goal.is_completed = True
        goal.completed_at = timezone.now()
    goal.save()
    return savings_goal_to_dict(goal)


@tool()
@safe_tool
def update_savings_goal(params: UpdateSavingsGoalIn) -> dict[str, Any]:
    """Edit a savings goal's metadata (owner or parent only)."""
    user = get_current_user()
    try:
        goal = SavingsGoal.objects.get(pk=params.goal_id)
    except SavingsGoal.DoesNotExist:
        raise MCPNotFoundError(f"Savings goal {params.goal_id} not found.")
    if goal.user_id != user.id and user.role != "parent":
        raise MCPPermissionDenied("Cannot edit another user's goal.")
    data = params.model_dump(exclude={"goal_id"}, exclude_unset=True)
    for field, value in data.items():
        setattr(goal, field, value)
    goal.save()
    return savings_goal_to_dict(goal)


@tool()
@safe_tool
def delete_savings_goal(params: DeleteSavingsGoalIn) -> dict[str, Any]:
    """Delete a savings goal (owner or parent only)."""
    user = get_current_user()
    try:
        goal = SavingsGoal.objects.get(pk=params.goal_id)
    except SavingsGoal.DoesNotExist:
        raise MCPNotFoundError(f"Savings goal {params.goal_id} not found.")
    if goal.user_id != user.id and user.role != "parent":
        raise MCPPermissionDenied("Cannot delete another user's goal.")
    goal_id = goal.pk
    goal.delete()
    return {"goal_id": goal_id, "deleted": True}
