"""Regression tests for mounting the MCP app inside Django's ASGI app.

``config.asgi`` dispatches requests whose path begins with ``/mcp`` to a
FastMCP-backed Starlette sub-app and everything else to Django's ASGI
application. These tests guard:

* ``build_mounted_mcp_app()`` wires a lifespan and is independently callable
  (i.e. it doesn't rely on ``build_http_app()``).
* ``config.asgi.application`` is path-dispatching: ``/mcp`` lands on MCP
  (unauthenticated → 401), ``/health`` lands on Django (→ 200 JSON),
  ``/api/...`` lands on Django.
* The FastMCP session manager's task group gets initialized via the
  lifespan event forwarded by the dispatcher.
"""
from __future__ import annotations

import asyncio

from django.test import TransactionTestCase, override_settings
from rest_framework.authtoken.models import Token
from starlette.testclient import TestClient

from apps.mcp_server.server import build_mounted_mcp_app, mcp
from apps.accounts.models import User


def _reset_mcp_session_manager() -> None:
    """Force FastMCP to rebuild its session manager on next request.

    Each test needs a fresh anyio task group because
    ``StreamableHTTPSessionManager.run()`` can only be entered once per
    instance.
    """
    mcp._session_manager = None  # type: ignore[attr-defined]


_TEST_ALLOWED_HOSTS = ["testserver", "testserver:*", "127.0.0.1", "localhost"]
_TEST_ALLOWED_ORIGINS = [
    "http://testserver",
    "http://testserver:*",
    "http://127.0.0.1",
    "http://localhost",
]


@override_settings(
    MCP_ALLOWED_HOSTS=_TEST_ALLOWED_HOSTS,
    MCP_ALLOWED_ORIGINS=_TEST_ALLOWED_ORIGINS,
)
class BuildMountedMcpAppTests(TransactionTestCase):
    """``build_mounted_mcp_app()`` must be self-sufficient."""

    def setUp(self) -> None:
        _reset_mcp_session_manager()

    def test_mounted_app_has_lifespan_wired(self) -> None:
        app = build_mounted_mcp_app()
        self.assertIsNotNone(
            app.router.lifespan_context,
            "build_mounted_mcp_app() must wire a lifespan that starts the "
            "FastMCP session manager; otherwise the task group is never "
            "initialized.",
        )

    def test_mounted_app_has_no_health_route(self) -> None:
        """Mounted variant omits /health — Django already exposes one."""
        from starlette.routing import Route

        app = build_mounted_mcp_app()
        paths = [r.path for r in app.router.routes if isinstance(r, Route)]
        self.assertNotIn("/health", paths)

    def test_mounted_app_rejects_unauthenticated_mcp_request(self) -> None:
        app = build_mounted_mcp_app()
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


class ConfigAsgiDispatchTests(TransactionTestCase):
    """``config.asgi.application`` must path-dispatch by URL prefix.

    The tests replace the real Django and MCP sub-apps with recording
    stubs so we exercise only the dispatcher logic — driving the real
    Django ASGI app from hand-rolled scopes is flaky and not what's
    under test here.
    """

    def setUp(self) -> None:
        import config.asgi as asgi_module

        self.asgi_module = asgi_module
        self._orig_django = asgi_module._django_app
        self._orig_mcp = asgi_module._mcp_app
        self._orig_getter = asgi_module._get_mcp_app

        self.django_calls: list[dict] = []
        self.mcp_calls: list[dict] = []

        async def django_stub(scope, receive, send):
            self.django_calls.append(scope)
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"x-handler", b"django")],
                })
                await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def mcp_stub(scope, receive, send):
            self.mcp_calls.append(scope)
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"x-handler", b"mcp")],
                })
                await send({"type": "http.response.body", "body": b"", "more_body": False})
            elif scope["type"] == "lifespan":
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                msg = await receive()
                if msg["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})

        asgi_module._django_app = django_stub
        asgi_module._mcp_app = mcp_stub
        asgi_module._get_mcp_app = lambda: mcp_stub

    def tearDown(self) -> None:
        self.asgi_module._django_app = self._orig_django
        self.asgi_module._mcp_app = self._orig_mcp
        self.asgi_module._get_mcp_app = self._orig_getter

    def _drive_http(self, path: str) -> tuple[list[dict], list[dict]]:
        """Run a single HTTP request through the dispatcher."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                self.asgi_module.application(scope, receive, send),
            )
        finally:
            loop.close()
        return sent

    def _handler_name(self, messages: list[dict]) -> str:
        start = next(m for m in messages if m["type"] == "http.response.start")
        for key, value in start["headers"]:
            if key == b"x-handler":
                return value.decode()
        return ""

    def test_health_path_goes_to_django(self) -> None:
        messages = self._drive_http("/health")
        self.assertEqual(self._handler_name(messages), "django")
        self.assertEqual(len(self.mcp_calls), 0)

    def test_api_path_goes_to_django(self) -> None:
        messages = self._drive_http("/api/projects/")
        self.assertEqual(self._handler_name(messages), "django")
        self.assertEqual(len(self.mcp_calls), 0)

    def test_spa_root_goes_to_django(self) -> None:
        messages = self._drive_http("/")
        self.assertEqual(self._handler_name(messages), "django")
        self.assertEqual(len(self.mcp_calls), 0)

    def test_mcp_exact_path_goes_to_mcp_sub_app(self) -> None:
        messages = self._drive_http("/mcp")
        self.assertEqual(self._handler_name(messages), "mcp")
        self.assertEqual(len(self.django_calls), 0)

    def test_mcp_child_path_goes_to_mcp_sub_app(self) -> None:
        messages = self._drive_http("/mcp/messages")
        self.assertEqual(self._handler_name(messages), "mcp")
        self.assertEqual(len(self.django_calls), 0)

    def test_mcp_prefix_does_not_match_substring(self) -> None:
        """``/mcpanel`` must go to Django, not MCP — the prefix is a
        proper path segment match, not a substring.
        """
        messages = self._drive_http("/mcpanel")
        self.assertEqual(self._handler_name(messages), "django")
        self.assertEqual(len(self.mcp_calls), 0)

    def test_lifespan_events_forward_to_mcp(self) -> None:
        """Lifespan startup/shutdown must be forwarded to the MCP sub-app
        so its session-manager task group is initialized.
        """
        queue = asyncio.Queue()

        async def runner():
            sent: list[dict] = []

            async def receive():
                return await queue.get()

            async def send(message):
                sent.append(message)

            task = asyncio.create_task(
                self.asgi_module.application(
                    {"type": "lifespan"}, receive, send,
                ),
            )
            await queue.put({"type": "lifespan.startup"})
            # Yield until startup.complete is observed.
            for _ in range(100):
                if any(m["type"] == "lifespan.startup.complete" for m in sent):
                    break
                await asyncio.sleep(0)
            await queue.put({"type": "lifespan.shutdown"})
            await asyncio.wait_for(task, timeout=2)
            return sent

        loop = asyncio.new_event_loop()
        try:
            sent = loop.run_until_complete(runner())
        finally:
            loop.close()

        types = [m["type"] for m in sent]
        self.assertIn("lifespan.startup.complete", types)
        self.assertIn("lifespan.shutdown.complete", types)
        # The stub MCP app recorded at least one lifespan scope call.
        self.assertTrue(
            any(s.get("type") == "lifespan" for s in self.mcp_calls),
            "Lifespan events were not forwarded to the MCP sub-app.",
        )


@override_settings(
    MCP_ALLOWED_HOSTS=_TEST_ALLOWED_HOSTS,
    MCP_ALLOWED_ORIGINS=_TEST_ALLOWED_ORIGINS,
)
class MountedMcpAuthenticatedHandshakeTests(TransactionTestCase):
    """With a valid DRF token, an authenticated MCP initialize must not 500
    — i.e. the mounted variant's lifespan successfully starts the FastMCP
    session manager's task group.
    """

    def setUp(self) -> None:
        _reset_mcp_session_manager()
        self.user = User.objects.create_user(
            username="mounted-mcp-client", password="pw", role="parent",
        )
        self.token = Token.objects.create(user=self.user)

    def test_authenticated_initialize_does_not_500(self) -> None:
        app = build_mounted_mcp_app()
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
                    "Authorization": f"Token {self.token.key}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )
        self.assertNotEqual(
            response.status_code,
            500,
            f"Mounted MCP initialize returned 500 — task group likely not "
            f"initialized. Body: {response.text!r}",
        )
