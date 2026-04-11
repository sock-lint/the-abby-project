"""DRF token authentication bridged into the MCP Starlette app.

Every inbound HTTP request must carry ``Authorization: Token <key>``. The
token is resolved against ``rest_framework.authtoken.models.Token`` (same
store the REST API and SPA use), and the resulting ``User`` is pinned to
the current asyncio task via ``context.set_current_user`` for the lifetime
of the request.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from asgiref.sync import sync_to_async
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from .context import reset_current_user, set_current_user


def _parse_token_header(header_value: Optional[str]) -> Optional[str]:
    """Return the raw token from an ``Authorization: Token <key>`` header."""
    if not header_value:
        return None
    parts = header_value.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, key = parts
    if scheme.lower() != "token":
        return None
    return key.strip() or None


def _resolve_user(token_key: str):
    """Look up a Django ``User`` from a DRF auth token (sync ORM call)."""
    from rest_framework.authtoken.models import Token

    try:
        token = Token.objects.select_related("user").get(key=token_key)
    except Token.DoesNotExist:
        return None
    user = token.user
    if not user.is_active:
        return None
    return user


resolve_user_async = sync_to_async(_resolve_user, thread_sensitive=True)


def _unauthorized(message: str) -> JSONResponse:
    """Return a JSON-RPC 2.0 shaped error for MCP clients."""
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "error": {"code": -32001, "message": message},
            "id": None,
        },
        status_code=401,
    )


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that resolves DRF tokens into the MCP context.

    Unauthenticated requests to the MCP endpoint are rejected with a 401 JSON
    error. Paths listed in ``exempt_paths`` skip auth (used for ``/health``).
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

        token_key = _parse_token_header(request.headers.get("authorization"))
        if not token_key:
            return _unauthorized("Missing or malformed Authorization header.")

        user = await resolve_user_async(token_key)
        if user is None:
            return _unauthorized("Invalid token.")

        ctx_token = set_current_user(user)
        try:
            response = await call_next(request)
        finally:
            reset_current_user(ctx_token)
        return response
