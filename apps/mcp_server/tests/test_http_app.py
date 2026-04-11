"""Regression tests for the Starlette HTTP transport wiring.

Guards against a past bug where ``build_http_app()`` passed
``getattr(mcp_app, "lifespan", None)`` as the outer app's lifespan. Starlette
has no ``.lifespan`` attribute, so the outer app ended up with ``lifespan=None``
and FastMCP's ``StreamableHTTPSessionManager.run()`` was never entered,
causing every real MCP request to raise
``RuntimeError: Task group is not initialized. Make sure to use run().``
"""
from __future__ import annotations

from django.test import TestCase, TransactionTestCase
from rest_framework.authtoken.models import Token
from starlette.testclient import TestClient

from apps.mcp_server.server import build_http_app, mcp
from apps.projects.models import User


def _reset_mcp_session_manager() -> None:
    """Reset the module-level FastMCP singleton's cached session manager.

    ``StreamableHTTPSessionManager.run()`` can only be called once per
    instance. Our module-level ``mcp`` caches its session manager lazily in
    ``streamable_http_app()``; resetting it lets each test build a fresh
    app + fresh session manager + fresh anyio task group.
    """
    mcp._session_manager = None  # type: ignore[attr-defined]


class BuildHttpAppLifespanTests(TestCase):
    def setUp(self) -> None:
        _reset_mcp_session_manager()

    def test_outer_app_has_lifespan_wired(self) -> None:
        """The outer Starlette app must have a lifespan_context — not None.

        This is the direct regression guard for the bug: the previous code
        did ``getattr(mcp_app, "lifespan", None)``, which always returned
        None because Starlette has no ``.lifespan`` attribute.
        """
        app = build_http_app()
        self.assertIsNotNone(
            app.router.lifespan_context,
            "build_http_app() must wire a lifespan that starts the FastMCP "
            "session manager; otherwise the task group is never initialized.",
        )

    def test_health_endpoint_is_unauthenticated(self) -> None:
        """Entering the TestClient context runs the lifespan. /health should 200."""
        app = build_http_app()
        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_mcp_endpoint_rejects_missing_token(self) -> None:
        """Unauthenticated requests to the MCP endpoint must 401, not 500."""
        app = build_http_app()
        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )
        self.assertEqual(response.status_code, 401)

class MCPInitializeHandshakeTests(TransactionTestCase):
    """End-to-end test that a real MCP ``initialize`` call is dispatched.

    Uses ``TransactionTestCase`` so DB writes are visible to the sync ORM
    call inside ``TokenAuthMiddleware`` (which runs in asgiref's thread pool
    and would otherwise deadlock against a ``TestCase`` transaction on
    SQLite).
    """

    def setUp(self) -> None:
        _reset_mcp_session_manager()

    def test_mcp_initialize_does_not_raise_task_group_error(self) -> None:
        """An authenticated initialize request must reach FastMCP's handler.

        If the session manager's task group isn't initialized (the bug this
        test guards against), ``StreamableHTTPSessionManager.handle_request``
        raises ``RuntimeError: Task group is not initialized.`` and Starlette
        surfaces it as a 500. A healthy wiring returns a JSON-RPC response —
        anything but 500.
        """
        user = User.objects.create_user(
            username="mcp-client", password="pw", role="parent",
        )
        token = Token.objects.create(user=user)

        app = build_http_app()
        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "abby-test", "version": "0"},
                    },
                },
                headers={
                    "Authorization": f"Token {token.key}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )

        self.assertNotEqual(
            response.status_code,
            500,
            f"MCP initialize returned 500 — task group likely not initialized. "
            f"Body: {response.text!r}",
        )
