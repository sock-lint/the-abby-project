"""Real OAuth HTTP transport preserves structured failures and typed successes."""
import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import sync_to_async
from django.db import connections
from django.test import TransactionTestCase, override_settings
from starlette.testclient import TestClient

from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import CreateProjectIn, LogMovementSessionIn, RequestRedemptionIn
from apps.mcp_server.server import build_http_app, mcp
from apps.mcp_server.shapes import project_list_to_dict
from apps.mcp_server.tools import movement, projects, rewards
from apps.movement.models import MovementType
from apps.projects.models import Project
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService
from config.tests.factories import make_family, make_oauth_token


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    MCP_ALLOWED_HOSTS=["testserver", "testserver:*"],
    MCP_ALLOWED_ORIGINS=["http://testserver", "http://testserver:*"],
)
class StructuredErrorHTTPTests(TransactionTestCase):
    def setUp(self):
        household = make_family(
            "HTTP result contracts", parents=[{"username": "http-result-parent", "is_staff": True}],
            children=[{"username": "http-result-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.headers_by_scope = {
            scope: make_oauth_token(self.parent, scope=scope)[1]
            for scope in ("mcp:read", "mcp:write", "mcp:catalog")
        }
        self.request_id = 0
        self.protocol = "2025-11-25"
        mcp._session_manager = None
        self.http = self.enterContext(TestClient(build_http_app()))
        # TestClient's portal and the thread-sensitive ORM executor have
        # different lifetimes. Close that executor's connection before its
        # portal exits so PostgreSQL can drop the disposable test database.
        async def close_worker_connections():
            await sync_to_async(connections.close_all, thread_sensitive=True)()
        self.addCleanup(self.http.portal.call, close_worker_connections)
        initialized = self.rpc("initialize", {
            "protocolVersion": self.protocol, "capabilities": {},
            "clientInfo": {"name": "abby-result-contract-tests", "version": "1"},
        })
        self.protocol = initialized["protocolVersion"]
        acknowledged = self.http.post("/mcp", headers=self.headers(), json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        self.assertIn(acknowledged.status_code, (200, 202, 204))

    def headers(self, scope="mcp:read"):
        return {
            "Authorization": self.headers_by_scope[scope],
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol,
        }

    def rpc(self, method, params, *, scope="mcp:read"):
        self.request_id += 1
        response = self.http.post("/mcp", headers=self.headers(scope), json={
            "jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params,
        })
        self.assertEqual(response.status_code, 200, response.text)
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            messages = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:")]
            envelope = next(message for message in reversed(messages) if message.get("id") == self.request_id)
        else:
            envelope = response.json()
        self.assertEqual(envelope["jsonrpc"], "2.0")
        self.assertEqual(envelope["id"], self.request_id)
        self.assertNotIn("error", envelope, envelope)
        return envelope["result"]

    def call(self, name, params=None, *, scope="mcp:read", **arguments):
        return self.rpc("tools/call", {
            "name": name, "arguments": {"params": params or {}, **arguments},
        }, scope=scope)

    def assert_matching_payloads(self, result, *, failed=False):
        self.assertEqual(result.get("isError", False), failed, result)
        text_blocks = [block["text"] for block in result["content"] if block["type"] == "text"]
        self.assertEqual(len(text_blocks), 1, result)
        self.assertEqual(json.loads(text_blocks[0]), result["structuredContent"])
        return result["structuredContent"]

    def test_invalid_arguments_have_safe_field_errors_over_http(self):
        private_value = "synthetic-private-user-input"
        result = self.call("list_projects", {"limit": private_value})
        error = self.assert_matching_payloads(result, failed=True)["error"]
        self.assertEqual(error["code"], "invalid_input")
        self.assertIn("params.limit", error["field_errors"])
        self.assertFalse(error["retryable"])
        self.assertNotIn(private_value, json.dumps(result))

    def test_json_encoded_params_keep_fastmcp_client_compatibility(self):
        result = self.rpc("tools/call", {
            "name": "list_projects", "arguments": {"params": "{}"},
        })
        payload = self.assert_matching_payloads(result)
        self.assertEqual(payload["projects"], [])
        self.assertEqual(payload["total"], 0)
        invalid = self.rpc("tools/call", {
            "name": "list_projects", "arguments": {"params": json.dumps({"limit":"synthetic-private-value"})},
        })
        error = self.assert_matching_payloads(invalid, failed=True)["error"]
        self.assertEqual(error["code"], "invalid_input")
        self.assertIn("params.limit", error["field_errors"])
        self.assertNotIn("synthetic-private-value", json.dumps(invalid))

    def test_json_encoded_params_do_not_coerce_confirmation(self):
        project = Project.objects.create(title="Retained project", created_by=self.parent, assigned_to=self.child)
        result = self.rpc("tools/call", {
            "name": "delete_project", "arguments": {
                "params": json.dumps({"project_id":project.pk}), "confirmation":"true",
            },
        }, scope="mcp:write")
        error = self.assert_matching_payloads(result, failed=True)["error"]
        self.assertEqual(error["code"], "invalid_input")
        self.assertIn("confirmation", error["field_errors"])
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

    def test_missing_confirmation_is_distinct_and_never_deletes(self):
        project = Project.objects.create(title="Retained project", created_by=self.parent, assigned_to=self.child)
        for arguments in ({}, {"confirmation": False}):
            with self.subTest(arguments=arguments):
                result = self.call("delete_project", {"project_id": project.pk}, scope="mcp:write", **arguments)
                error = self.assert_matching_payloads(result, failed=True)["error"]
                self.assertEqual(error["code"], "confirmation_required")
                self.assertFalse(error["retryable"])
                self.assertTrue(Project.objects.filter(pk=project.pk).exists())
        invalid = self.call("delete_project", {"project_id": project.pk}, scope="mcp:write", confirmation="true")
        error = self.assert_matching_payloads(invalid, failed=True)["error"]
        self.assertEqual(error["code"], "invalid_input")
        self.assertIn("confirmation", error["field_errors"])
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

    def test_exact_grants_filter_discovery_and_produce_permission_errors(self):
        read_names = {entry["name"] for entry in self.rpc("tools/list", {}, scope="mcp:read")["tools"]}
        self.assertIn("list_projects", read_names)
        self.assertNotIn("create_project", read_names)
        for name, scope, params in (
            ("create_project", "mcp:read", {}),
            ("list_projects", "mcp:write", {}),
            ("get_homework", "mcp:catalog", {"assignment_id": 123456}),
        ):
            with self.subTest(name=name, scope=scope):
                result = self.call(name, params, scope=scope)
                error = self.assert_matching_payloads(result, failed=True)["error"]
                self.assertEqual(error["code"], "permission_denied")
                self.assertFalse(error["retryable"])
        self.assertFalse(Project.objects.exists())

    def test_unknown_tool_and_unexpected_failure_are_safe_tool_results(self):
        unknown = self.call("synthetic_missing_tool", scope="mcp:catalog")
        self.assertEqual(self.assert_matching_payloads(unknown, failed=True)["error"]["code"], "unknown_tool")
        private_value = "synthetic-private-exception-details"
        with patch.object(mcp._tool_manager, "call_tool", side_effect=RuntimeError(private_value)):
            result = self.call("list_projects", {})
        error = self.assert_matching_payloads(result, failed=True)["error"]
        self.assertEqual(error["code"], "internal_error")
        self.assertFalse(error["retryable"])
        self.assertEqual(error["field_errors"], {})
        self.assertNotIn(private_value, json.dumps(result))
        self.assertNotIn("Traceback", json.dumps(result))

    def test_typed_project_page_preserves_complete_serializer_fields(self):
        first = Project.objects.create(
            title="First project", description="Original project description", created_by=self.parent,
            assigned_to=self.child, bonus_amount=Decimal("3.25"),
        )
        second = Project.objects.create(title="Second project", created_by=self.parent, assigned_to=self.child)
        result = self.call("list_projects", {"limit": 1})
        payload = self.assert_matching_payloads(result)
        self.assertEqual(payload["projects"], [project_list_to_dict(second)])
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["has_more"])
        self.assertIsInstance(payload["next_cursor"], str)
        later = self.assert_matching_payloads(self.call("list_projects", {"limit": 1, "cursor": payload["next_cursor"]}))
        self.assertEqual(later["projects"], [project_list_to_dict(first)])
        self.assertEqual(later["projects"][0]["bonus_amount"], "3.25")
        self.assertFalse(later["has_more"])

    def test_typed_create_preserves_nested_steps_resources_and_retry_response(self):
        params = {
            "request_id": str(uuid4()), "title": "HTTP build", "assigned_to_id": self.child.pk,
            "description": "Saved through the HTTP tool", "bonus_amount": "4.50",
            "milestones": [{"title": "Build the chassis"}],
            "steps": [{"title": "Measure the parts", "milestone_index": 0}],
            "resources": [{"title": "Reference", "url": "https://example.com/reference", "step_index": 0}],
        }
        payload = self.assert_matching_payloads(self.call("create_project", params, scope="mcp:write"))
        with override_user(self.parent):
            direct_retry = projects.create_project(CreateProjectIn(**params))
        self.assertEqual(payload, direct_retry)
        self.assertEqual(payload["bonus_amount"], "4.50")
        self.assertEqual(payload["milestones"][0]["title"], "Build the chassis")
        self.assertEqual(payload["steps"][0]["title"], "Measure the parts")
        self.assertEqual(payload["steps"][0]["resources"][0]["url"], "https://example.com/reference")
        self.assertEqual(Project.objects.count(), 1)

    def test_typed_movement_preserves_distance_receipts_and_additional_fields(self):
        movement_type = MovementType.objects.create(name="HTTP walk", slug="http-walk")
        params = {
            "client_request_id": str(uuid4()), "movement_type_id": movement_type.pk,
            "user_id": self.child.pk, "duration_minutes": 20, "distance": "1.25", "distance_unit": "mi",
            "notes": "Synthetic walk notes",
        }
        payload = self.assert_matching_payloads(self.call("log_movement_session", params, scope="mcp:write"))
        with override_user(self.parent):
            direct_retry = movement.log_movement_session(LogMovementSessionIn(**params))
        self.assertEqual(payload, direct_retry)
        self.assertEqual(payload["distance"], "1.25")
        self.assertEqual(payload["distance_meters"], "2011.680")
        self.assertEqual(payload["notes"], "Synthetic walk notes")
        self.assertEqual(payload["movement_type_name"], "HTTP walk")
        self.assertIn("challenge_receipts", payload)

    def test_typed_redemption_preserves_saved_promise_and_spends_once(self):
        reward = Reward.objects.create(
            family=self.parent.family, name="HTTP reward", cost_coins=10, stock=2, requires_parent_approval=True,
        )
        CoinService.award_coins(self.parent, 50, CoinLedger.Reason.ADJUSTMENT)
        params = {"request_id": str(uuid4()), "reward_id": reward.pk}
        result = self.call("request_redemption", params, scope="mcp:write", confirmation=True)
        payload = self.assert_matching_payloads(result)
        with override_user(self.parent):
            direct_retry = rewards.request_redemption(RequestRedemptionIn(**params))
        self.assertEqual(payload, direct_retry)
        self.assertEqual(payload["reward"]["name"], "HTTP reward")
        self.assertEqual(payload["coin_cost_snapshot"], 10)
        self.assertEqual(payload["reward"]["fulfillment_kind"], "real_world")
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(RewardRedemption.objects.count(), 1)
        self.assertEqual(CoinService.get_balance(self.parent), 40)
