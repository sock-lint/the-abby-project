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

from .errors import MCPPermissionDenied

if TYPE_CHECKING:
    from apps.projects.models import User


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


@contextlib.contextmanager
def override_user(user: Optional["User"]) -> Iterator[None]:
    """Temporarily pin the current user (used in tests and stdio --as-user)."""
    token = set_current_user(user)
    try:
        yield
    finally:
        reset_current_user(token)
