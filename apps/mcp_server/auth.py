"""OAuth 2.1 Bearer-token authentication for the MCP Starlette app.

Every inbound request to ``/mcp/*`` must carry
``Authorization: Bearer <access_token>`` where the token resolves against
``oauth2_provider.AccessToken``. Tokens are issued via the auth-code +
PKCE flow handled by django-oauth-toolkit (see ``config/oauth_views.py``);
the MCP-spec discovery endpoints live at ``/.well-known/oauth-*``.

RFC 8707 resource binding: the auth-code flow stamps a ``resource`` claim
on each AccessToken's ``claims`` JSON. We refuse tokens whose claim
doesn't match ``settings.MCP_RESOURCE_URL`` — that's what prevents a
token issued for a different resource server (or a different MCP server
on the same auth-server) from being replayed against /mcp/.

The pre-OAuth flow accepted ``Authorization: Token <key>`` (DRF
TokenAuthentication) for the same surface. That path is gone now — the
SPA's ``/api/*`` calls keep using Token auth, but ``/mcp/*`` is OAuth-only.
A request that still sends ``Token <key>`` here gets a 401 + a body hint
pointing at the discovery URL so the client knows to migrate.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from .context import reset_current_user, set_current_user


def _parse_bearer_header(header_value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Split an ``Authorization`` header into ``(scheme, key)``.

    Returns ``(None, None)`` when the header is missing or malformed.
    Callers check scheme to surface a "you sent Token, send Bearer"
    discovery hint to legacy clients.
    """
    if not header_value:
        return None, None
    parts = header_value.split(None, 1)
    if len(parts) != 2:
        return None, None
    scheme, key = parts
    return scheme.lower(), key.strip() or None


def _resolve_user(token_key: str):
    """Look up an OAuth AccessToken row and return its User if valid.

    All-or-nothing — any failed precondition (missing row, expired,
    revoked, wrong resource binding, inactive user) returns None and the
    middleware turns that into a 401.
    """
    from oauth2_provider.models import AccessToken

    try:
        access_token = AccessToken.objects.select_related("user", "application").get(
            token=token_key,
        )
    except AccessToken.DoesNotExist:
        return None
    # DOT exposes is_valid()/is_expired() — be explicit so the failure mode
    # is obvious in tests (expired rows still exist; revoked-via-expires
    # also short-circuits here).
    if access_token.expires is not None and access_token.expires <= timezone.now():
        return None
    user = access_token.user
    if not user or not user.is_active:
        return None
    # RFC 8707 resource binding. Missing row = legacy (test fixtures /
    # admin-created tokens); reject only on explicit mismatch.
    expected_resource = getattr(settings, "MCP_RESOURCE_URL", "") or ""
    bound_resource: str = ""
    binding = getattr(access_token, "mcp_resource", None)
    if binding is not None:
        bound_resource = binding.resource or ""
    if bound_resource and expected_resource and bound_resource != expected_resource:
        return None
    return user


resolve_user_async = sync_to_async(_resolve_user, thread_sensitive=True)


def _unauthorized(message: str, *, discovery_url: Optional[str] = None) -> JSONResponse:
    """Return a JSON-RPC 2.0 shaped error for MCP clients.

    When ``discovery_url`` is provided it's included in the error payload's
    ``data`` field so an MCP client that hit /mcp/ with stale Token-style
    auth can self-correct.
    """
    error: dict[str, Any] = {"code": -32001, "message": message}
    if discovery_url:
        error["data"] = {"discovery_url": discovery_url}
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "error": error,
            "id": None,
        },
        status_code=401,
    )


def _discovery_url(request: Request) -> str:
    """Compute the absolute URL of the OAuth protected-resource metadata."""
    site = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if site:
        return f"{site}/.well-known/oauth-protected-resource"
    # Fall back to the request's own scheme+host (works in dev/tests).
    return str(request.url_for("oauth-protected-resource")) if hasattr(request, "url_for") else (
        f"{request.url.scheme}://{request.url.netloc}/.well-known/oauth-protected-resource"
    )


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that resolves OAuth Bearer tokens into the MCP context.

    Class name kept (`TokenAuthMiddleware`) for back-compat with anything
    importing it; the implementation is now OAuth Bearer-only.
    """

    def __init__(self, app: ASGIApp, exempt_paths: tuple[str, ...] = ("/health",)) -> None:
        super().__init__(app)
        self.exempt_paths = exempt_paths

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        scheme, key = _parse_bearer_header(request.headers.get("authorization"))
        if scheme is None or key is None:
            return _unauthorized(
                "Missing or malformed Authorization header. Use 'Authorization: Bearer <token>'.",
                discovery_url=_discovery_url(request),
            )
        if scheme == "token":
            # Legacy DRF-token clients used to work against this endpoint.
            # Tell them where the discovery doc lives so they can migrate.
            return _unauthorized(
                "MCP requires OAuth 2.1 Bearer tokens. Token-style auth is no longer accepted.",
                discovery_url=_discovery_url(request),
            )
        if scheme != "bearer":
            return _unauthorized(
                f"Unsupported Authorization scheme: {scheme}. Use Bearer.",
                discovery_url=_discovery_url(request),
            )

        user = await resolve_user_async(key)
        if user is None:
            return _unauthorized(
                "Invalid, expired, or revoked access token.",
                discovery_url=_discovery_url(request),
            )

        ctx_token = set_current_user(user)
        try:
            response = await call_next(request)
        finally:
            reset_current_user(ctx_token)
        return response
