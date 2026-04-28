"""User management MCP tools."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User

from ..context import get_current_user, require_parent
from ..errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
    safe_tool,
)
from ..schemas import GetUserIn, ListChildrenIn, UpdateChildIn
from ..server import tool
from ..shapes import child_to_dict, user_to_dict


@tool()
@safe_tool
def list_children(params: ListChildrenIn) -> dict[str, Any]:
    """Return every child user in the family (parent-only).

    Essential for parents: every other tool that takes a ``user_id`` /
    ``assigned_to_id`` requires a child ID, and this is the lookup table.
    """
    del params  # schema has no fields
    caller = require_parent()
    children = list(
        User.objects.filter(role="child", family=caller.family)
        .order_by("display_name", "username")
    )
    return {"children": [child_to_dict(c) for c in children]}


@tool()
@safe_tool
def get_user(params: GetUserIn) -> dict[str, Any]:
    """Return a user profile. Children may only look up themselves."""
    user = get_current_user()
    target_id = params.user_id if params.user_id is not None else user.id
    if target_id != user.id and user.role != "parent":
        raise MCPPermissionDenied("Children can only look up their own profile.")
    try:
        target = User.objects.get(pk=target_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {target_id} not found.")
    if target.id != user.id and target.family_id != getattr(user, "family_id", None):
        raise MCPNotFoundError(f"User {target_id} not found.")
    return user_to_dict(target)


@tool()
@safe_tool
def update_child(params: UpdateChildIn) -> dict[str, Any]:
    """Update a child's profile fields (parent-only).

    Editable: ``hourly_rate``, ``display_name``, ``theme``. No create or
    delete — children are sensitive accounts managed only via Django
    admin. The ``avatar`` image is parent-UI-only (MCP can't upload
    files).
    """
    caller = require_parent()
    try:
        target = User.objects.get(
            pk=params.user_id, role="child", family=caller.family,
        )
    except User.DoesNotExist:
        raise MCPNotFoundError(f"Child {params.user_id} not found.")
    data = params.model_dump(exclude={"user_id"}, exclude_unset=True)
    if not data:
        raise MCPValidationError(
            "Pass at least one of hourly_rate, display_name, theme.",
        )
    for field, value in data.items():
        setattr(target, field, value)
    target.save()
    return user_to_dict(target)
