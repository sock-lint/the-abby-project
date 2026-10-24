"""FastMCP server wiring for the-abby-project.

Exposes a module-level ``mcp`` instance plus a ``tool`` decorator that tool
modules use for registration; also provides ``build_http_app()`` (self-
contained Starlette app with token auth middleware, used by
``runmcp --transport http``), ``build_mounted_mcp_app()`` (same Starlette
app minus the ``/health`` route, for mounting inside the Django ASGI
application), and ``run_stdio()`` for local development.
"""
from __future__ import annotations

import functools
import inspect
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator, Callable

from asgiref.sync import sync_to_async
from django.conf import settings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field, StrictBool, ValidationError

from .context import get_current_scopes, require_scope, require_staff_parent
from .errors import MCPError, MCPNotFoundError, MCPValidationError
from .output_schemas import OUTPUT_MODELS
from .tool_policy import AUTHOR_SCOPE, CATALOG_SCOPE, PUBLISH_SCOPE, policy_for


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
# modules register themselves on import via the @tool() decorator defined
# below (NOT @mcp.tool() directly — that would register sync handlers that
# crash under Django's async-safety guard; see the ``tool`` docstring).
#
# ``transport_security`` is computed from Django settings so the MCP SDK's
# DNS rebinding middleware whitelists the public hostname this service runs
# behind. Without it the SDK auto-enables a loopback-only allow-list.
class ScopedFastMCP(FastMCP):
    def _setup_handlers(self):
        super()._setup_handlers()
        # Validate through the registered Pydantic argument model below so
        # schema failures use the same safe error contract as domain failures.
        self._mcp_server.call_tool(validate_input=False)(self.call_tool)

    async def list_tools(self):
        tools = await super().list_tools()
        scopes = get_current_scopes()
        return [tool for tool in tools if policy_for(tool.name).required_scopes <= scopes]

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        try:
            entry = self._tool_manager.get_tool(name)
            if entry is None:
                raise MCPNotFoundError("Unknown tool.", code="unknown_tool")
            for scope in sorted(policy_for(name).required_scopes):
                require_scope(scope)
            try:
                parsed = entry.fn_metadata.pre_parse_json(arguments)
                # Preserve FastMCP's JSON-encoded params compatibility, while
                # retaining the transport's literal-boolean confirmation gate.
                if "confirmation" in arguments:
                    parsed["confirmation"] = arguments["confirmation"]
                entry.fn_metadata.arg_model.model_validate(parsed)
            except ValidationError as exc:
                fields: dict[str, list[str]] = {}
                for item in exc.errors(include_input=False, include_url=False):
                    field = ".".join(str(part) for part in item["loc"])
                    fields.setdefault(field, []).append(item["msg"])
                raise MCPValidationError(
                    "Check the indicated tool arguments.", code="invalid_input", field_errors=fields,
                ) from exc
            return await super().call_tool(name, arguments)
        except Exception as exc:
            # FastMCP wraps handler exceptions in ToolError. Inspect only the
            # trusted exception class; never send an arbitrary traceback,
            # database error or validation input back to an external client.
            cause = exc
            while cause.__cause__ is not None and not isinstance(cause, MCPError):
                cause = cause.__cause__
            if not isinstance(cause, MCPError):
                logging.getLogger(__name__).error("MCP tool %s failed (%s)", name, type(cause).__name__)
                cause = MCPError("The operation could not be completed. Check its saved state before retrying.",
                                 code="internal_error")
            data = {"error": cause.as_dict()}
            return CallToolResult(isError=True, structuredContent=data,
                                  content=[TextContent(type="text", text=json.dumps(data))])


mcp = ScopedFastMCP(
    name=getattr(settings, "MCP_SERVER_NAME", "abby"),
    instructions=(
        "Read abby://mcp/capabilities for granted permissions and workflows. "
        "Catalog access contains no household records. Reuse write request UUIDs "
        "after uncertain responses; server receipts own rewards and saved state."
    ),
    stateless_http=True,
    transport_security=_build_transport_security(),
)


@mcp.resource("abby://mcp/capabilities", description="Granted permissions and available Abby workflows; no household data.")
def mcp_capabilities() -> str:
    require_staff_parent()
    scopes = get_current_scopes()
    workflows = {
        "catalog": {"required_scopes": ["mcp:catalog"], "purpose": "Global references, audits and anonymous economy previews."},
        "reading_history": {"required_scopes": ["mcp:read"], "purpose": "Explicit same-family child shelf and reading summary."},
        "reading_log": {"required_scopes": ["mcp:write"], "purpose": "Save a book or reading session with a stable client_request_id UUID."},
        "content_drafts": {"required_scopes": ["mcp:author"], "purpose": "Family-owned drafts and publication previews."},
        "reading_maintenance": {"required_scopes": ["mcp:read", "mcp:write"], "purpose": "Inspect saved sessions, correct books/sessions, mark book status and delete without rearming rewards."},
        "reviewed_content_editing": {"required_scopes": ["mcp:catalog", "mcp:author", "mcp:publish"], "purpose": "Select existing definitions, save a private revision, preview, compare progression and publish the exact reviewed plan."},
        "challenge_reconciliation": {"required_scopes": ["mcp:author", "mcp:publish"], "purpose": "Preview one explicit global challenge source and canonical pair with a stable client_request_id UUID, inspect its private receipt, then publish the exact digest with confirmation and any required cooperation acknowledgement."},
        "editorial_content": {"required_scopes": ["mcp:catalog", "mcp:author", "mcp:publish"], "purpose": "Draft and publish textual Lorebook/affirmation changes; retirement preserves saved identities."},
        "progression_planning": {"required_scopes": ["mcp:catalog"], "purpose": "Inspect installed rules and run bounded anonymous progression scenarios; no household selectors or awards."},
        "saved_progression_experiments": {"required_scopes": ["mcp:author"], "purpose": "Save private hypotheses, compare server-generated forecasts and record design decisions. Household checkpoints are redacted without mcp:read; decisions never publish or change rewards."},
        "progression_observations": {"required_scopes": ["mcp:read"], "purpose": "Inspect bounded current-family economy aggregates; no account selectors, private notes or inferred policy validation."},
        "progression_checkpoints": {"required_scopes": ["mcp:author", "mcp:read"], "purpose": "Save a bounded current-family observation checkpoint in an actor-owned experiment with a stable request UUID."},
        "household_rpg_management": {"required_scopes": ["mcp:read", "mcp:write"], "purpose": "Inspect and control challenge attempts/future schedules, frozen expeditions and physical reward delivery."},
        "content_publication": {"required_scopes": ["mcp:publish"], "purpose": "Apply the exact reviewed publication plan after confirmation."},
    }
    return json.dumps({
        "schema_version": 1, "granted_scopes": sorted(scopes),
        "workflows": {name: {**workflow, "available": set(workflow["required_scopes"]) <= scopes}
                      for name, workflow in workflows.items()},
        "permissions": "Scopes are independent. New permissions require explicit OAuth reconnection; this resource grants none.",
        "errors": {"fields": ["code", "message", "retryable", "field_errors"],
                   "uncertain_writes": "Inspect saved state and retry with the original UUID; never invent a replacement request ID."},
    })


def tool(*tool_args: Any, **tool_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register an MCP tool, adapting sync Django-ORM handlers to async.

    Use this in place of ``@mcp.tool()`` for every tool module. Purpose:

    FastMCP's ``FuncMetadata.call_fn_with_arg_validation`` (see
    ``mcp/server/fastmcp/utilities/func_metadata.py``) calls sync handlers
    **inline** from inside the asyncio event loop::

        if fn_is_async:
            return await fn(**arguments_parsed_dict)
        else:
            return fn(**arguments_parsed_dict)  # runs on the event-loop thread

    Every MCP tool in this project is a plain ``def`` that hits the Django
    ORM, so that inline call triggers Django's async-safety guard and the
    tool raises ``SynchronousOnlyOperation`` ("You cannot call this from an
    async context - use a thread or sync_to_async.") the first time it
    touches the database.

    This decorator wraps the handler with
    ``asgiref.sync.sync_to_async(fn, thread_sensitive=True)`` and registers
    a true ``async def`` adapter with ``mcp.tool()``. Because
    ``inspect.iscoroutinefunction`` returns True for the adapter, FastMCP
    dispatches via ``await fn(...)``, asgiref runs the sync body on the
    shared sync thread (so Django's per-thread DB connection and
    ``transaction.atomic()`` work normally), and contextvars set earlier by
    the auth middleware (``mcp_current_user``) propagate into that thread.

    The *original* sync function is returned to the calling namespace
    unchanged, so existing synchronous unit tests that call tool handlers
    directly (``tool_module.list_children(ListChildrenIn())``) continue to
    work without an event loop.

    Signature preservation: the adapter uses ``@functools.wraps(fn)`` and
    ``**kwargs``. ``inspect.signature`` follows ``__wrapped__`` by default,
    so FastMCP's ``func_metadata`` sees the *original* function's
    ``(params: SomeSchema)`` signature and builds the argument model
    correctly, while the adapter still accepts any kwargs at runtime.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        name = tool_kwargs.get("name") or fn.__name__
        policy = policy_for(name)  # Unreviewed tool names fail at registration.
        runner = fn if inspect.iscoroutinefunction(fn) else sync_to_async(fn, thread_sensitive=True)

        @functools.wraps(fn)
        async def adapted(**kwargs: Any) -> Any:
            for scope in sorted(policy.required_scopes):
                require_scope(scope)
            if policy.scope in {AUTHOR_SCOPE, CATALOG_SCOPE, PUBLISH_SCOPE}:
                require_staff_parent()
            if policy.destructive:
                confirmation = kwargs.pop("confirmation", False)
                if confirmation is not True:
                    raise MCPValidationError(
                        "This operation changes or removes saved data. Obtain the user's "
                        "confirmation, then call again with confirmation=true.",
                        code="confirmation_required",
                    )
            return await runner(**kwargs)

        if policy.destructive:
            # Advertise the acknowledgement as part of the real input schema,
            # alongside params, while preserving each handler's existing model.
            signature = inspect.signature(fn, eval_str=True)
            confirmation = inspect.Parameter(
                "confirmation", kind=inspect.Parameter.KEYWORD_ONLY, default=False,
                annotation=Annotated[StrictBool, Field(description=(
                    "Set true only after the user confirms this operation and its targets. "
                    "This acknowledgement is required before the tool changes or removes saved data."
                ))],
            )
            adapted.__signature__ = signature.replace(  # type: ignore[attr-defined]
                parameters=[*signature.parameters.values(), confirmation],
            )
        if name in OUTPUT_MODELS:
            signature = inspect.signature(adapted, eval_str=True)
            adapted.__signature__ = signature.replace(return_annotation=OUTPUT_MODELS[name])
        registration = dict(tool_kwargs)
        registration["annotations"] = ToolAnnotations(
            readOnlyHint=policy.read_only,
            destructiveHint=policy.destructive,
            idempotentHint=policy.idempotent,
            openWorldHint=policy.open_world,
        )
        mcp.tool(*tool_args, **registration)(adapted)
        return fn

    return decorator


def _load_tool_modules() -> None:
    """Import every tool module so its @tool() decorators fire."""
    # noqa: F401 - imports-for-side-effects
    from .tools import (  # noqa: F401
        achievements,
        asset_proposals,
        catalog,
        challenge_reconciliation,
        challenges,
        chores,
        chronicle,
        content_packs,
        content_workbench,
        creations,
        daily_challenges,
        dashboard,
        economy,
        editorial,
        exchange,
        habits,
        homework,
        ingestion,
        inventory,
        movement,
        notifications,
        payments,
        pets,
        portfolio,
        projects,
        progression_experiments,
        quests,
        reading,
        reading_maintenance,
        rewards,
        rpg_management,
        rpg_rules,
        savings,
        sprite_assets,
        sprite_authoring,
        templates,
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
        against OAuth Bearer tokens,
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
