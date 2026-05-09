"""Gate helpers for dev-tools commands and (eventual) HTTP endpoints.

The gate model mirrors ``apps/mcp_server/management/commands/runmcp.py`` —
``settings.DEBUG=True`` is the implicit dev-machine signal; an explicit
``DEV_TOOLS_ENABLED=True`` env override exists so a staging deploy can opt
in without flipping the broader DEBUG flag.

Importable as a module so future view code (``apps/dev_tools/views.py``) and
the management commands share one source of truth.
"""
from __future__ import annotations

from django.conf import settings


def is_enabled() -> bool:
    """Return True when dev-tools commands and endpoints are allowed.

    Allowed when EITHER ``DEBUG=True`` OR ``DEV_TOOLS_ENABLED=True`` (default
    False). Production deploys ship with both False.
    """
    if getattr(settings, "DEBUG", False):
        return True
    return bool(getattr(settings, "DEV_TOOLS_ENABLED", False))


def assert_enabled() -> None:
    """Raise if dev-tools are disabled. Use at the top of every command."""
    if not is_enabled():
        from django.core.management.base import CommandError

        raise CommandError(
            "Dev-tools commands are disabled. Set DEBUG=True or "
            "DEV_TOOLS_ENABLED=True to use them."
        )
