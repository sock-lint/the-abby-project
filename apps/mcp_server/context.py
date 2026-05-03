"""Request-scoped user context for MCP tool calls.

Each incoming request (HTTP or stdio) sets the current user in a
`contextvars.ContextVar` via `auth.TokenAuthMiddleware`. Tool handlers read
from it via `get_current_user()` and gate parent-only operations through
`require_parent()`. Using contextvars (rather than thread-locals) keeps this
correct under asyncio, which Starlette / Streamable HTTP use.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import TYPE_CHECKING, Iterator, Optional

from .errors import MCPNotFoundError, MCPPermissionDenied

if TYPE_CHECKING:
    from apps.accounts.models import User


_CURRENT_USER: contextvars.ContextVar[Optional["User"]] = contextvars.ContextVar(
    "mcp_current_user", default=None,
)


def set_current_user(user: Optional["User"]) -> contextvars.Token:
    """Set the user for the current context. Returns a token for reset()."""
    return _CURRENT_USER.set(user)


def reset_current_user(token: contextvars.Token) -> None:
    _CURRENT_USER.reset(token)


def get_current_user() -> "User":
    """Return the authenticated user, or raise MCPPermissionDenied."""
    user = _CURRENT_USER.get()
    if user is None:
        raise MCPPermissionDenied("No authenticated user in context.")
    return user


def require_parent() -> "User":
    """Return the current user if they are a parent, else raise."""
    user = get_current_user()
    if getattr(user, "role", None) != "parent":
        raise MCPPermissionDenied("This tool is restricted to parent accounts.")
    return user


def is_parent() -> bool:
    user = _CURRENT_USER.get()
    return user is not None and getattr(user, "role", None) == "parent"


def resolve_target_user(user: "User", requested_id: int | None) -> "User":
    """Return the target user, enforcing child → self + same-family scoping.

    If ``requested_id`` is ``None`` or matches the caller, return the caller.
    Otherwise the caller must be a parent and the requested user must (a)
    exist and (b) belong to the same family. A cross-family request raises
    ``MCPNotFoundError`` (NOT permission-denied — don't leak existence).
    """
    from apps.accounts.models import User as UserModel
    if requested_id is None or requested_id == user.id:
        return user
    if getattr(user, "role", None) != "parent":
        raise MCPPermissionDenied("Children can only view their own data.")
    try:
        target = UserModel.objects.get(pk=requested_id)
    except UserModel.DoesNotExist:
        raise MCPNotFoundError(f"User {requested_id} not found.")
    if target.family_id != getattr(user, "family_id", None):
        raise MCPNotFoundError(f"User {requested_id} not found.")
    return target


def resolve_child_in_family(parent: "User", child_id: int) -> "User":
    """Resolve a child by id, enforcing parent + same-family scope.

    Companion to ``resolve_target_user`` for the parent-targets-child write
    path (``record_payout``, ``adjust_coins``, ``adjust_payment``,
    ``create_habit`` on-behalf, ``export_portfolio``). The semantics differ
    from ``resolve_target_user``:

      * The caller MUST be a parent (no self-resolve).
      * The target MUST be a child (filters ``role="child"`` on the lookup).
      * Cross-family / non-existent / wrong-role ids all raise
        ``MCPNotFoundError`` — never permission-denied — so probing tools
        can't distinguish "doesn't exist" from "exists in another family"
        from "exists but is a parent".

    Use this anywhere an MCP tool currently does
    ``User.objects.get(pk=params.user_id)`` for a parent-on-behalf write.
    """
    from apps.accounts.models import User as UserModel
    if getattr(parent, "role", None) != "parent":
        raise MCPPermissionDenied("This tool is restricted to parent accounts.")
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        # Defense in depth — every parent should have a family by now, but
        # if one slips through (legacy data, broken migration), fail closed.
        raise MCPNotFoundError(f"User {child_id} not found.")
    try:
        target = UserModel.objects.get(
            pk=child_id, role="child", family_id=family_id,
        )
    except UserModel.DoesNotExist:
        raise MCPNotFoundError(f"User {child_id} not found.")
    return target


@contextlib.contextmanager
def override_user(user: Optional["User"]) -> Iterator[None]:
    """Temporarily pin the current user (used in tests and stdio --as-user)."""
    token = set_current_user(user)
    try:
        yield
    finally:
        reset_current_user(token)
