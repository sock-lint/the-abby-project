"""Regression tests for the sync → async tool adapter.

Background: FastMCP's ``FuncMetadata.call_fn_with_arg_validation`` dispatches
sync tool handlers *inline* on the event-loop thread::

    if fn_is_async:
        return await fn(**arguments_parsed_dict)
    else:
        return fn(**arguments_parsed_dict)  # runs on the event-loop thread

Every MCP tool in this project touches the Django ORM. If the registered
handler is sync, Django's async-safety guard rejects the first ORM call with
``SynchronousOnlyOperation`` ("You cannot call this from an async context -
use a thread or sync_to_async."). Matt hit this in production: routing and
the handshake worked, but every ``tools/call`` returned a ToolError.

The fix is ``apps.mcp_server.server.tool`` — a decorator used in place of
``@mcp.tool()`` that wraps sync handlers with
``asgiref.sync.sync_to_async(..., thread_sensitive=True)`` before registering
them with FastMCP. The registered callable is then a true ``async def``
adapter that FastMCP awaits, and the sync body executes on the shared sync
thread where Django is happy.

These tests guard both halves of that contract.
"""
from __future__ import annotations

import inspect

from asgiref.sync import async_to_sync
from django.test import TransactionTestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.accounts.models import User


class AllToolsRegisteredAsAsync(TransactionTestCase):
    """Catch any future tool module that uses ``@mcp.tool()`` directly."""

    def test_every_registered_tool_is_a_coroutine(self) -> None:
        tools = mcp._tool_manager.list_tools()
        self.assertGreater(
            len(tools), 0, "No tools registered — tool modules failed to import.",
        )
        sync_tools: list[str] = []
        for mcp_tool in tools:
            if not (mcp_tool.is_async and inspect.iscoroutinefunction(mcp_tool.fn)):
                sync_tools.append(mcp_tool.name)
        self.assertFalse(
            sync_tools,
            msg=(
                "These tools are registered as sync callables and will raise "
                "SynchronousOnlyOperation on their first Django ORM call when "
                "dispatched through the MCP HTTP transport: "
                f"{sorted(sync_tools)}. Use `from ..server import tool` and "
                "`@tool()` instead of `@mcp.tool()` in the tool module."
            ),
        )


class ToolRunDispatchesSyncBodyToThreadpool(TransactionTestCase):
    """Exercise the exact production code path that was broken.

    ``TransactionTestCase`` (not ``TestCase``) is required: sync_to_async
    dispatches the tool body to a separate thread with its own DB connection,
    so the test data must be committed rather than locked inside the test's
    transaction.
    """

    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.child_alice = User.objects.create_user(
            username="child_alice",
            password="pw",
            role="child",
            display_name="Alice",
        )
        self.child_bob = User.objects.create_user(
            username="child_bob",
            password="pw",
            role="child",
            display_name="Bob",
        )

    def test_list_children_runs_through_registry_in_event_loop(self) -> None:
        list_children_tool = mcp._tool_manager.get_tool("list_children")
        self.assertIsNotNone(
            list_children_tool,
            "list_children tool not registered — did users.py import fail?",
        )

        async def _invoke() -> dict:
            with override_user(self.parent):
                # Tool.run() is the same entry point the Streamable HTTP
                # transport uses via ToolManager.call_tool(). If the adapter
                # regresses, this raises ToolError wrapping
                # SynchronousOnlyOperation.
                return await list_children_tool.run({"params": {}})

        result = async_to_sync(_invoke)()
        self.assertIn("children", result)
        names = {c["display_name"] for c in result["children"]}
        self.assertEqual(names, {"Alice", "Bob"})

    def test_contextvar_propagates_into_threadpool(self) -> None:
        """The ``mcp_current_user`` contextvar set by the auth middleware must
        still be readable from inside the sync_to_async-dispatched body —
        otherwise ``get_current_user()`` raises ``MCPPermissionDenied``.
        """
        get_user_tool = mcp._tool_manager.get_tool("get_user")
        self.assertIsNotNone(get_user_tool)

        async def _invoke_as_child() -> dict:
            with override_user(self.child_alice):
                return await get_user_tool.run({"params": {}})

        result = async_to_sync(_invoke_as_child)()
        self.assertEqual(result["username"], "child_alice")
