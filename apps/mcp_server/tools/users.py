"""User management MCP tools."""
from __future__ import annotations

from typing import Any

from apps.projects.models import User

from ..context import get_current_user, require_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import GetUserIn, ListChildrenIn
from ..server import mcp
from ..shapes import child_to_dict, user_to_dict


@mcp.tool()
@safe_tool
def list_children(params: ListChildrenIn) -> dict[str, Any]:
    """Return every child user in the family (parent-only).

    Essential for parents: every other tool that takes a ``user_id`` /
    ``assigned_to_id`` requires a child ID, and this is the lookup table.
    """
    del params  # schema has no fields
    require_parent()
    children = list(User.objects.filter(role="child").order_by("display_name", "username"))
    return {"children": [child_to_dict(c) for c in children]}


@mcp.tool()
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
    return user_to_dict(target)
