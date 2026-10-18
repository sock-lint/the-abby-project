"""The public MCP registry enforces grants, annotations and confirmations."""
from asgiref.sync import async_to_sync
from django.test import TransactionTestCase, override_settings
from mcp.server.fastmcp.exceptions import ToolError

from apps.mcp_server.context import (
    override_user, reset_current_user, set_current_user,
)
from apps.mcp_server.server import mcp, tool
from apps.mcp_server.tool_policy import (
    AUTHOR_SCOPE, AUTHOR_TOOLS, CATALOG_SCOPE, CATALOG_TOOLS, DESTRUCTIVE_TOOLS, MCP_SCOPES,
    PUBLISH_SCOPE, PUBLISH_TOOLS,
    READ_SCOPE, READ_TOOLS, WRITE_SCOPE, WRITE_TOOLS, policy_for,
)
from config.tests.factories import make_family


class ToolPermissionTests(TransactionTestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "scope-parent", "is_staff": True}],
            children=[{"username": "scope-child"}],
        )
        self.parent = family.parents[0]
        self.child = family.children[0]

    def invoke(self, name, params=None, *, scopes=MCP_SCOPES, **arguments):
        from asgiref.sync import sync_to_async
        from django.db import connections

        async def run():
            with override_user(self.parent, scopes=frozenset(scopes)):
                try:
                    return await mcp._tool_manager.get_tool(name).run({"params": params or {}, **arguments})
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def test_only_exact_granted_scope_tools_are_discoverable(self):
        async def names(scopes):
            with override_user(self.parent, scopes=frozenset(scopes)):
                return {tool.name for tool in await mcp.list_tools()}
        for scope, expected in ((READ_SCOPE, READ_TOOLS), (WRITE_SCOPE, WRITE_TOOLS), (CATALOG_SCOPE, CATALOG_TOOLS), (AUTHOR_SCOPE, AUTHOR_TOOLS), (PUBLISH_SCOPE, PUBLISH_TOOLS)):
            with self.subTest(scope=scope):
                self.assertEqual(async_to_sync(names)({scope}), expected)
        self.assertEqual(async_to_sync(names)(set()), set())

    def test_every_registered_tool_has_exact_reviewed_annotations(self):
        registered = mcp._tool_manager.list_tools()
        self.assertEqual({t.name for t in registered}, READ_TOOLS | WRITE_TOOLS | AUTHOR_TOOLS | CATALOG_TOOLS | PUBLISH_TOOLS)
        groups = [READ_TOOLS, WRITE_TOOLS, AUTHOR_TOOLS, CATALOG_TOOLS, PUBLISH_TOOLS]
        self.assertEqual(sum(len(group) for group in groups), len(set().union(*groups)))
        for entry in registered:
            with self.subTest(tool=entry.name):
                policy = policy_for(entry.name)
                self.assertEqual(entry.annotations.readOnlyHint, policy.read_only)
                self.assertEqual(entry.annotations.destructiveHint, policy.destructive)
                self.assertEqual(entry.annotations.idempotentHint, policy.idempotent)
                self.assertEqual(entry.annotations.openWorldHint, policy.open_world)
                self.assertEqual("confirmation" in entry.parameters["properties"], entry.name in DESTRUCTIVE_TOOLS)
        # These getters create state and therefore require write permission.
        self.assertEqual(policy_for("get_daily_challenge").scope, WRITE_SCOPE)
        self.assertEqual(policy_for("list_cosmetics").scope, WRITE_SCOPE)

    def test_unknown_tool_registration_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no reviewed permission policy"):
            @tool()
            def unreviewed_operation():
                pass

    def test_retired_pet_breeding_is_not_registered_or_permitted(self):
        self.assertNotIn("breed_mounts", {entry.name for entry in mcp._tool_manager.list_tools()})
        self.assertIsNone(mcp._tool_manager.get_tool("breed_mounts"))
        with self.assertRaisesRegex(ValueError, "no reviewed permission policy"):
            policy_for("breed_mounts")

    def test_catalog_grant_does_not_disclose_family_records_or_allow_drafts_or_publication(self):
        self.assertIn("categories", self.invoke("list_skill_categories", scopes={CATALOG_SCOPE}))
        for name, params in [
            ("get_skill_tree", {"category_id": 1, "user_id": self.child.pk}),
            ("list_children", {}), ("list_coin_ledger", {}), ("list_challenges", {}),
            ("get_today_journal", {}), ("list_asset_proposals", {}),
            ("create_category", {"name": "No"}),
        ]:
            with self.subTest(name=name), self.assertRaisesRegex(ToolError, "permission"):
                self.invoke(name, params, scopes={CATALOG_SCOPE})
        self.assertEqual(policy_for("get_skill_tree").scope, READ_SCOPE)
        self.assertEqual(policy_for("write_pack_file").scope, AUTHOR_SCOPE)
        self.assertEqual(policy_for("publish_content_pack").scope, PUBLISH_SCOPE)

    def test_draft_and_publish_grants_are_independent(self):
        for name, params, granted in [
            ("create_category", {"name": "No"}, AUTHOR_SCOPE),
            ("list_asset_proposals", {}, PUBLISH_SCOPE),
            ("list_children", {}, AUTHOR_SCOPE),
            ("list_children", {}, PUBLISH_SCOPE),
        ]:
            with self.subTest(name=name, granted=granted), self.assertRaisesRegex(ToolError, "permission"):
                self.invoke(name, params, scopes={granted})

    def test_grant_is_enforced_on_invocation_even_for_known_hidden_tools(self):
        self.assertIn("children", self.invoke("list_children", scopes={READ_SCOPE}))
        for scope, name, params in [
            (READ_SCOPE, "mark_all_notifications_read", {}),
            (READ_SCOPE, "create_category", {"name": "Unauthorized"}),
            (WRITE_SCOPE, "create_category", {"name": "Unauthorized"}),
            (AUTHOR_SCOPE, "mark_all_notifications_read", {}),
        ]:
            with self.subTest(scope=scope, tool=name), self.assertRaisesRegex(ToolError, "permission"):
                self.invoke(name, params, scopes={scope})
        self.assertEqual(self.invoke("mark_all_notifications_read", scopes={WRITE_SCOPE})["marked_read"], 0)
        created = self.invoke("create_category", {"name": "Authorized"}, scopes={PUBLISH_SCOPE})
        self.assertEqual(created["name"], "Authorized")

    def test_user_context_alone_never_grants_permissions(self):
        async def run():
            token = set_current_user(self.parent)
            try:
                return await mcp._tool_manager.get_tool("mark_all_notifications_read").run({"params": {}})
            finally:
                reset_current_user(token)
        with self.assertRaisesRegex(ToolError, "permission"):
            async_to_sync(run)()

    def test_publish_scope_still_requires_staff(self):
        self.parent.is_staff = False
        with self.assertRaisesRegex(ToolError, "staff parents"):
            self.invoke("create_category", {"name": "Unauthorized"}, scopes={PUBLISH_SCOPE})

    def test_destructive_action_requires_explicit_strict_boolean_confirmation(self):
        from apps.projects.models import Project
        project = Project.objects.create(title="Fixture project", assigned_to=self.child, created_by=self.parent)
        params = {"project_id": project.pk}
        for argument in ({}, {"confirmation": False}, {"confirmation": "true"}):
            with self.subTest(argument=argument), self.assertRaises(ToolError):
                self.invoke("delete_project", params, scopes={WRITE_SCOPE}, **argument)
            self.assertTrue(Project.objects.filter(pk=project.pk).exists())
        result = self.invoke("delete_project", params, scopes={WRITE_SCOPE}, confirmation=True)
        self.assertTrue(result["deleted"])
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())


@override_settings(MCP_ALLOWED_HOSTS=["testserver"], MCP_ALLOWED_ORIGINS=["http://testserver"])
class HttpScopeBoundaryTests(TransactionTestCase):
    def test_http_scope_and_confirmation_are_enforced_through_the_real_transport(self):
        import json
        from asgiref.sync import sync_to_async
        from django.db import connections
        from starlette.testclient import TestClient
        from apps.mcp_server.server import build_mounted_mcp_app
        from apps.projects.models import Project
        from config.tests.factories import make_oauth_token

        family = make_family(
            parents=[{"username": "http-scope-parent", "is_staff": True}],
            children=[{"username": "http-scope-child"}],
        )
        parent, child = family.parents[0], family.children[0]
        project = Project.objects.create(title="Disposable HTTP fixture", assigned_to=child, created_by=parent)
        _, read_header = make_oauth_token(parent, scope="mcp:read")
        _, write_header = make_oauth_token(parent, scope="mcp:write")
        mcp._session_manager = None

        def request(client, header, method, params=None):
            response = client.post("/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
            }, headers={
                "Authorization": header, "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            })
            self.assertEqual(response.status_code, 200, response.text)
            if response.headers.get("content-type", "").startswith("text/event-stream"):
                return json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: ")))
            return response.json()

        async def close_worker_connections():
            await sync_to_async(connections.close_all, thread_sensitive=True)()

        with TestClient(build_mounted_mcp_app()) as client:
            try:
                listed = request(client, read_header, "tools/list")["result"]["tools"]
                self.assertEqual({entry["name"] for entry in listed}, READ_TOOLS)
                denied = request(client, read_header, "tools/call", {
                    "name": "delete_project", "arguments": {"params": {"project_id": project.pk}, "confirmation": True},
                })
                self.assertTrue(denied["result"]["isError"])
                self.assertTrue(Project.objects.filter(pk=project.pk).exists())
                denied = request(client, write_header, "tools/call", {
                    "name": "delete_project", "arguments": {"params": {"project_id": project.pk}, "confirmation": False},
                })
                self.assertTrue(denied["result"]["isError"])
                self.assertTrue(Project.objects.filter(pk=project.pk).exists())
                allowed = request(client, write_header, "tools/call", {
                    "name": "delete_project", "arguments": {"params": {"project_id": project.pk}, "confirmation": True},
                })
                self.assertFalse(allowed["result"].get("isError"))
                self.assertFalse(Project.objects.filter(pk=project.pk).exists())
            finally:
                # Close the actual transport's worker before its portal exits;
                # a new async_to_sync call would close a different connection.
                client.portal.call(close_worker_connections)
