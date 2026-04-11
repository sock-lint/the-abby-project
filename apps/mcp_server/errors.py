"""MCP-specific exception types and a safe-tool wrapper.

Domain services raise their own exceptions (`InsufficientCoinsError`,
`RewardUnavailableError`, `ValueError` from `ClockService`, etc.). The MCP
transport needs those surfaced to Claude as structured, non-crashing errors.
`safe_tool` catches the known domain exceptions and re-raises them as
`MCPValidationError` so FastMCP produces a JSON-RPC error response instead
of a 500.
"""
from __future__ import annotations

import functools
from typing import Any, Callable


class MCPError(Exception):
    """Base class for MCP server errors surfaced to Claude."""


class MCPPermissionDenied(MCPError):
    """Raised when the current user's role is insufficient for a tool."""


class MCPValidationError(MCPError):
    """Raised when tool input fails domain validation."""


class MCPNotFoundError(MCPError):
    """Raised when a referenced object does not exist or is inaccessible."""


def safe_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a tool handler so domain exceptions become MCPValidationError.

    The inner function can raise any of:
      - `InsufficientCoinsError`, `RewardUnavailableError` (rewards)
      - `ValueError` (ClockService and other service-layer validations)
      - Django `ObjectDoesNotExist` for missing FK targets
    and the caller will see a single `MCPValidationError` /
    `MCPNotFoundError`. `MCPPermissionDenied` is passed through unchanged.
    """
    # Imported lazily so this module stays importable without Django set up.
    from django.core.exceptions import ObjectDoesNotExist
    from apps.rewards.services import InsufficientCoinsError, RewardUnavailableError

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (MCPPermissionDenied, MCPValidationError, MCPNotFoundError):
            raise
        except ObjectDoesNotExist as exc:
            raise MCPNotFoundError(str(exc) or "Object not found") from exc
        except (InsufficientCoinsError, RewardUnavailableError) as exc:
            raise MCPValidationError(str(exc)) from exc
        except ValueError as exc:
            raise MCPValidationError(str(exc)) from exc

    return wrapper
