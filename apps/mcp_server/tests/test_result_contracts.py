"""Wire contracts for typed results and safe, actionable tool failures."""
from types import SimpleNamespace
import json
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp, mcp_capabilities


class ResultContractTests(SimpleTestCase):
    def setUp(self):
        self.actor = SimpleNamespace(id=1, family_id=1, role="parent", is_staff=True)

    def call(self, name, params, *, scopes=frozenset({"mcp:catalog"})):
        with override_user(self.actor, scopes=scopes):
            return async_to_sync(mcp.call_tool)(name, {"params": params})

    def test_project_page_advertises_fields_instead_of_an_opaque_dictionary(self):
        schema = mcp._tool_manager.get_tool("list_projects").fn_metadata.output_schema
        self.assertIn("projects", schema.get("properties", {}))
        self.assertIn("next_cursor", schema["properties"])

    def test_capabilities_explain_scope_requirements_without_household_identity(self):
        with override_user(self.actor, scopes=frozenset({"mcp:catalog"})):
            result = json.loads(mcp_capabilities())
        self.assertEqual(result["granted_scopes"], ["mcp:catalog"])
        self.assertTrue(result["workflows"]["catalog"]["available"])
        self.assertFalse(result["workflows"]["reading_history"]["available"])
        self.assertEqual(result["workflows"]["reading_log"]["required_scopes"], ["mcp:write"])
        self.assertFalse({"user_id", "family_id", "token", "records"} & result.keys())

    def test_permission_error_has_stable_code_without_household_data(self):
        result = self.call("get_homework", {"assignment_id": 999})
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")
        self.assertFalse(result.structuredContent["error"]["retryable"])

    def test_input_errors_expose_fields_without_echoing_input(self):
        result = self.call("list_skills", {"limit": "synthetic-private-value"})
        self.assertTrue(result.isError)
        error = result.structuredContent["error"]
        self.assertEqual(error["code"], "invalid_input")
        self.assertIn("params.limit", error["field_errors"])
        self.assertNotIn("synthetic-private-value", str(result))

    def test_unexpected_exception_is_sanitized_and_never_promises_a_safe_retry(self):
        with patch.object(mcp._tool_manager, "call_tool", side_effect=RuntimeError("synthetic-private-value")):
            result = self.call("list_skills", {})
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["error"]["code"], "internal_error")
        self.assertFalse(result.structuredContent["error"]["retryable"])
        self.assertNotIn("synthetic-private-value", str(result))

    def test_expected_domain_failure_retains_the_supported_next_action(self):
        result = self.call("submit_homework", {"assignment_id": 123}, scopes=frozenset({"mcp:write"}))
        self.assertTrue(result.isError)
        error = result.structuredContent["error"]
        self.assertEqual(error["code"], "invalid_request")
        self.assertIn("/api/homework/", error["message"])
