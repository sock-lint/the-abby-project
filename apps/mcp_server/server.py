"""FastMCP server wiring for the-abby-project.

Exposes a module-level ``mcp`` instance that tool modules decorate; also
provides ``build_http_app()`` (Starlette app with token auth middleware)
and ``run_stdio()`` for local development.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from django.conf import settings
from mcp.server.fastmcp import FastMCP


# Single FastMCP instance. ``stateless_http=True`` avoids per-session state
# so the mcp service can scale horizontally without shared storage. Tool
# modules register themselves on import via the @mcp.tool() decorator.
mcp = FastMCP(
    name=getattr(settings, "MCP_SERVER_NAME", "abby"),
    stateless_http=True,
)


def _load_tool_modules() -> None:
    """Import every tool module so its @mcp.tool() decorators fire."""
    # noqa: F401 - imports-for-side-effects
    from .tools import (  # noqa: F401
        achievements,
        dashboard,
        ingestion,
        notifications,
        payments,
        portfolio,
        projects,
        rewards,
        savings,
        timecards,
        users,
    )


_load_tool_modules()


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------


def build_http_app() -> Any:
    """Return a Starlette ASGI app for the Streamable HTTP transport.

    The returned app:
      * mounts FastMCP's streamable-HTTP handler at the configured path,
      * wraps it in ``TokenAuthMiddleware`` so every request is authenticated
        against DRF tokens,
      * exposes an unauthenticated ``/health`` endpoint for Docker healthchecks.
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from .auth import TokenAuthMiddleware

    # The FastMCP SDK builds its own Starlette sub-app that handles the MCP
    # JSON-RPC 2.0 protocol over Streamable HTTP. Calling ``streamable_http_app``
    # also lazily creates ``mcp.session_manager``; we must run its async context
    # manager as part of the outer app's lifespan so the underlying anyio task
    # group is initialized before any request is dispatched. Without this the
    # first MCP request fails with
    # ``RuntimeError: Task group is not initialized. Make sure to use run().``.
    mcp_app = mcp.streamable_http_app()

    async def health(_request):
        return JSONResponse({"status": "ok"})

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    outer = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        lifespan=lifespan,
    )
    outer.add_middleware(TokenAuthMiddleware)
    return outer


def run_stdio() -> None:
    """Run the MCP server over stdio (local dev / tests)."""
    mcp.run("stdio")
