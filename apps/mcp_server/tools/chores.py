"""Chores-related MCP tools."""
from __future__ import annotations

from typing import Any


from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreService
from apps.projects.models import User

from ..context import get_current_user, require_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    CompleteChoreIn,
    CreateChoreIn,
    DecideChoreCompletionIn,
    GetChoreIn,
    ListChoreCompletionsIn,
    ListChoresIn,
    UpdateChoreIn,
)
from ..server import tool
from ..shapes import chore_completion_to_dict, chore_to_dict, many


def _resolve_user_id(user, requested_id: int | None) -> User:
    if requested_id is None or requested_id == user.id:
        return user
    if user.role != "parent":
        raise MCPPermissionDenied("Children can only view their own data.")
    try:
        return User.objects.get(pk=requested_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {requested_id} not found.")


@tool()
@safe_tool
def list_chores(params: ListChoresIn) -> dict[str, Any]:
    """List chores. Parents see all; children see assigned + unassigned active chores with today's availability."""
    user = get_current_user()

    if user.role == "child":
        chores = ChoreService.get_available_chores(user)
        results = []
        for c in chores:
            d = chore_to_dict(c)
            d["is_available"] = not c.is_done_today
            d["today_status"] = c.today_completion_status
            results.append(d)
        return {"chores": results}

    qs = Chore.objects.all()
    if params.assigned_to_id:
        qs = qs.filter(assigned_to_id=params.assigned_to_id)
    return {"chores": many(qs[: params.limit], chore_to_dict)}


@tool()
@safe_tool
def get_chore(params: GetChoreIn) -> dict[str, Any]:
    """Get details for a single chore."""
    get_current_user()
    try:
        chore = Chore.objects.get(pk=params.chore_id)
    except Chore.DoesNotExist:
        raise MCPNotFoundError(f"Chore {params.chore_id} not found.")
    return chore_to_dict(chore)


@tool()
@safe_tool
def create_chore(params: CreateChoreIn) -> dict[str, Any]:
    """Create a new chore (parent-only)."""
    parent = require_parent()

    assigned_to = None
    if params.assigned_to_id:
        try:
            assigned_to = User.objects.get(pk=params.assigned_to_id, role="child")
        except User.DoesNotExist:
            raise MCPNotFoundError(f"Child {params.assigned_to_id} not found.")

    chore = Chore.objects.create(
        title=params.title,
        description=params.description,
        icon=params.icon,
        reward_amount=params.reward_amount,
        coin_reward=params.coin_reward,
        recurrence=params.recurrence,
        week_schedule=params.week_schedule,
        schedule_start_date=params.schedule_start_date,
        assigned_to=assigned_to,
        created_by=parent,
        is_active=params.is_active,
        order=params.order,
    )
    return chore_to_dict(chore)


@tool()
@safe_tool
def update_chore(params: UpdateChoreIn) -> dict[str, Any]:
    """Update an existing chore (parent-only)."""
    require_parent()
    try:
        chore = Chore.objects.get(pk=params.chore_id)
    except Chore.DoesNotExist:
        raise MCPNotFoundError(f"Chore {params.chore_id} not found.")

    updates = params.model_dump(exclude={"chore_id"}, exclude_unset=True)

    if "assigned_to_id" in updates:
        aid = updates.pop("assigned_to_id")
        if aid is None:
            chore.assigned_to = None
        else:
            try:
                chore.assigned_to = User.objects.get(pk=aid, role="child")
            except User.DoesNotExist:
                raise MCPNotFoundError(f"Child {aid} not found.")

    for field, value in updates.items():
        setattr(chore, field, value)
    chore.save()
    return chore_to_dict(chore)


@tool()
@safe_tool
def complete_chore(params: CompleteChoreIn) -> dict[str, Any]:
    """Mark a chore as done (creates a pending completion for parent approval)."""
    user = get_current_user()
    try:
        chore = Chore.objects.get(pk=params.chore_id)
    except Chore.DoesNotExist:
        raise MCPNotFoundError(f"Chore {params.chore_id} not found.")

    completion = ChoreService.submit_completion(user, chore, notes=params.notes)
    return chore_completion_to_dict(completion)


@tool()
@safe_tool
def list_chore_completions(params: ListChoreCompletionsIn) -> dict[str, Any]:
    """List chore completions. Parents see all; children see their own."""
    user = get_current_user()
    target = _resolve_user_id(user, params.user_id)

    qs = ChoreCompletion.objects.select_related("chore", "user")
    if user.role != "parent":
        qs = qs.filter(user=target)
    elif params.user_id:
        qs = qs.filter(user=target)

    if params.status:
        qs = qs.filter(status=params.status)

    return {
        "completions": many(
            qs.order_by("-created_at")[: params.limit],
            chore_completion_to_dict,
        ),
    }


@tool()
@safe_tool
def approve_chore_completion(params: DecideChoreCompletionIn) -> dict[str, Any]:
    """Approve a pending chore completion (parent-only). Awards money and coins."""
    parent = require_parent()
    try:
        completion = ChoreCompletion.objects.select_related("chore", "user").get(
            pk=params.completion_id,
        )
    except ChoreCompletion.DoesNotExist:
        raise MCPNotFoundError(f"Completion {params.completion_id} not found.")

    updated = ChoreService.approve_completion(completion, parent)
    return chore_completion_to_dict(updated)


@tool()
@safe_tool
def reject_chore_completion(params: DecideChoreCompletionIn) -> dict[str, Any]:
    """Reject a pending chore completion (parent-only)."""
    parent = require_parent()
    try:
        completion = ChoreCompletion.objects.select_related("chore", "user").get(
            pk=params.completion_id,
        )
    except ChoreCompletion.DoesNotExist:
        raise MCPNotFoundError(f"Completion {params.completion_id} not found.")

    updated = ChoreService.reject_completion(completion, parent)
    return chore_completion_to_dict(updated)
