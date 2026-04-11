"""Root ASGI application.

This module keeps the whole service on a single origin (``:8000``). Django
is the primary handler for every request except those whose path begins
with ``/mcp``; those are dispatched to a FastMCP-backed Starlette sub-app
before Django's URL router ever sees them.

Why ASGI-level dispatch (instead of a Django URL view or a Starlette
``Mount``)?

* FastMCP's Streamable HTTP transport is a full Starlette app that speaks
  JSON-RPC 2.0 over long-lived responses. Shoehorning that through a Django
  sync view would lose streaming and the per-session anyio task group.
* A Starlette ``Mount("/mcp", app=mcp_app)`` strips ``/mcp`` from the
  inbound path before forwarding, which would then fail to match FastMCP's
  own internal ``/mcp`` route. Forwarding at the ASGI level with the path
  intact sidesteps that.

Lifespan handling: FastMCP's ``StreamableHTTPSessionManager`` must be
entered via a lifespan context or the first request raises
``RuntimeError: Task group is not initialized.``. Django's own ASGI app
treats lifespan as a no-op, so we forward lifespan events to the MCP
sub-app only.
"""
from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

_django_app = get_asgi_application()
_mcp_app: Any = None


def _get_mcp_app() -> Any:
    """Lazy-build the mounted MCP Starlette sub-app.

    Deferred until the first request so that Django's app registry is fully
    populated before FastMCP tool modules touch the ORM at import time.
    """
    global _mcp_app
    if _mcp_app is None:
        from apps.mcp_server import server as mcp_server

        _mcp_app = mcp_server.build_mounted_mcp_app()
    return _mcp_app


def _is_mcp_path(path: str) -> bool:
    """True for ``/mcp`` and any ``/mcp/...`` descendant path."""
    return path == "/mcp" or path.startswith("/mcp/")


async def application(scope, receive, send):
    scope_type = scope.get("type")

    if scope_type == "lifespan":
        # Forward lifespan to the MCP sub-app so its session manager's
        # anyio task group is started. Django's ASGI lifespan is a no-op
        # for our purposes.
        mcp_app = _get_mcp_app()
        await mcp_app(scope, receive, send)
        return

    if scope_type in ("http", "websocket"):
        path = scope.get("path", "")
        if _is_mcp_path(path):
            mcp_app = _get_mcp_app()
            await mcp_app(scope, receive, send)
            return
        await _django_app(scope, receive, send)
        return

    # Unknown scope types fall through to Django.
    await _django_app(scope, receive, send)
