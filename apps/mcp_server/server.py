"""FastMCP server wiring for the-abby-project.

Exposes a module-level ``mcp`` instance that tool modules decorate; also
provides ``build_http_app()`` (self-contained Starlette app with token auth
middleware, used by ``runmcp --transport http``), ``build_mounted_mcp_app()``
(same Starlette app minus the ``/health`` route, for mounting inside the
Django ASGI application), and ``run_stdio()`` for local development.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from django.conf import settings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


def _build_transport_security() -> TransportSecuritySettings:
    """Build DNS-rebinding-protection settings from Django settings.

    The MCP SDK ships ``TransportSecurityMiddleware`` which validates the
    incoming ``Host`` header against an allow-list. If a ``transport_security``
    instance isn't passed, the SDK auto-enables protection with loopback-only
    hosts, so every request reaching the server through a reverse proxy
    (Traefik/Caddy/Cloudflare) is rejected with HTTP 421.

    ``MCP_ALLOWED_HOSTS`` / ``MCP_ALLOWED_ORIGINS`` are sourced in
    ``config.settings`` from env vars, falling back to Django's
    ``ALLOWED_HOSTS`` + ``CSRF_TRUSTED_ORIGINS``. A single ``*`` entry in
    either list is interpreted as "disable DNS rebinding protection".
    """
    allowed_hosts = list(getattr(settings, "MCP_ALLOWED_HOSTS", []) or [])
    allowed_origins = list(getattr(settings, "MCP_ALLOWED_ORIGINS", []) or [])
    if "*" in allowed_hosts or "*" in allowed_origins:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


# Single FastMCP instance. ``stateless_http=True`` avoids per-session state
# so the mcp service can scale horizontally without shared storage. Tool
# modules register themselves on import via the @mcp.tool() decorator.
#
# ``transport_security`` is computed from Django settings so the MCP SDK's
# DNS rebinding middleware whitelists the public hostname this service runs
# behind. Without it the SDK auto-enables a loopback-only allow-list.
mcp = FastMCP(
    name=getattr(settings, "MCP_SERVER_NAME", "abby"),
    stateless_http=True,
    transport_security=_build_transport_security(),
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


def _build_mcp_starlette_app(include_health: bool) -> Any:
    """Shared builder for the token-authed Starlette wrapper around FastMCP.

    ``include_health`` controls whether the outer app exposes ``/health``;
    the standalone HTTP transport ships it for Docker healthchecks, but the
    Django-mounted variant doesn't need a second one (``/health`` is already
    served by Django itself).
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from .auth import TokenAuthMiddleware

    # Refresh transport_security from current Django settings so that
    # ``@override_settings(MCP_ALLOWED_HOSTS=...)`` in tests takes effect.
    # FastMCP reads ``mcp.settings.transport_security`` when it lazily
    # builds the session manager inside ``streamable_http_app()``.
    mcp.settings.transport_security = _build_transport_security()

    # The FastMCP SDK builds its own Starlette sub-app that handles the MCP
    # JSON-RPC 2.0 protocol over Streamable HTTP. Calling ``streamable_http_app``
    # also lazily creates ``mcp.session_manager``; we must run its async context
    # manager as part of the outer app's lifespan so the underlying anyio task
    # group is initialized before any request is dispatched. Without this the
    # first MCP request fails with
    # ``RuntimeError: Task group is not initialized. Make sure to use run().``.
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    routes: list = []
    if include_health:
        async def health(_request):
            return JSONResponse({"status": "ok"})

        routes.append(Route("/health", health, methods=["GET"]))
    routes.append(Mount("/", app=mcp_app))

    outer = Starlette(routes=routes, lifespan=lifespan)
    outer.add_middleware(TokenAuthMiddleware)
    return outer


def build_http_app() -> Any:
    """Return a standalone Starlette ASGI app for the Streamable HTTP transport.

    The returned app:
      * mounts FastMCP's streamable-HTTP handler at the configured path,
      * wraps it in ``TokenAuthMiddleware`` so every request is authenticated
        against DRF tokens,
      * exposes an unauthenticated ``/health`` endpoint for Docker healthchecks.

    Used by ``python manage.py runmcp --transport http`` when running MCP
    as its own uvicorn process. The in-Django ASGI mount uses
    ``build_mounted_mcp_app()`` instead.
    """
    return _build_mcp_starlette_app(include_health=True)


def build_mounted_mcp_app() -> Any:
    """Return a Starlette ASGI sub-app for mounting inside Django's ASGI app.

    Identical to ``build_http_app()`` except it omits the ``/health`` route
    (Django already exposes one at the same path) so the Django-hosted
    MCP endpoint stays on a single origin (port 8000) with no reverse-proxy
    changes.

    Dispatched to from ``config.asgi`` when the request path begins with
    ``/mcp``. The sub-app is NOT a Starlette ``Mount`` with a prefix — it's
    invoked directly so FastMCP's internal ``/mcp`` route still matches
    without path rewriting.
    """
    return _build_mcp_starlette_app(include_health=False)


def run_stdio() -> None:
    """Run the MCP server over stdio (local dev / tests)."""
    mcp.run("stdio")
