"""The household MCP reader exposes the native aggregate without new authority."""
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError
from rest_framework.test import APIClient

from apps.families.models import LiveTestFamily
from apps.mcp_server.challenge_schemas import GetVoyagerFeedbackIn
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.mcp_server.server import mcp
from apps.mcp_server.tool_policy import CATALOG_SCOPE, MCP_SCOPES, READ_SCOPE, policy_for
from apps.mcp_server.tools import challenges
from apps.quests.goals import _snapshot
from apps.quests.models import ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.rewards.models import CoinLedger
from apps.rpg.models import UserInventory
from config.tests.factories import make_family


class VoyagerFeedbackRegistrationTests(SimpleTestCase):
    def test_voyager_feedback_is_registered_as_a_household_reader(self):
        entry = mcp._tool_manager.get_tool("get_voyager_feedback")
        self.assertIsNotNone(entry, "The production MCP surface needs the same readonly feedback report.")
        self.assertEqual(policy_for(entry.name).scope, READ_SCOPE)
        self.assertTrue(entry.annotations.readOnlyHint)
        self.assertTrue(entry.annotations.idempotentHint)
        self.assertFalse(entry.annotations.destructiveHint)
        self.assertFalse(entry.annotations.openWorldHint)
        self.assertNotIn("confirmation", entry.parameters["properties"])

    def test_input_is_empty_and_rejects_all_selectors_or_transport_parameters(self):
        self.assertEqual(GetVoyagerFeedbackIn().model_dump(), {})
        for key, value in [("user_id", 1), ("family_id", 1), ("since", "2026-01-01"),
                           ("until", "2026-10-20"), ("as_of", "2026-10-20"),
                           ("policy", "saved_45_day"), ("limit", 100), ("_abby_session", "transport")]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                GetVoyagerFeedbackIn.model_validate({key: value})
        schema = GetVoyagerFeedbackIn.model_json_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"], {})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class VoyagerFeedbackToolTests(TransactionTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "MCP Voyager household", parents=[{"username": "mcp-voyager-parent", "is_staff": True}],
            children=[{"username": "mcp-voyager-child"}, {"username": "mcp-voyager-new-child"}],
        )
        self.parent, self.child, self.new_child = household.parents[0], *household.children
        other = make_family("Other MCP Voyager", parents=[{"username": "mcp-voyager-other-parent", "is_staff": True}],
                            children=[{"username": "mcp-voyager-other-child"}])
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        get_user_model().objects.filter(pk__in=[self.child.pk, self.new_child.pk, self.other_child.pk]).update(
            date_joined=self.now - timedelta(days=120))
        self.definition = QuestDefinition.objects.create(
            name="Reading Voyager", is_system=True, quest_type="collection", target_value=20,
            duration_days=45, trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        self.saved_window(self.child)
        self.saved_window(self.other_child)

    def saved_window(self, child):
        start = self.now - timedelta(days=80)
        goal = ChallengeGoal.objects.create(
            user=child, family=child.family, is_catalog=True, catalog_definition=self.definition,
            name="Reading Voyager", description="Private saved presentation", metric="count", target=20,
            trigger_filter={"allowed_triggers": ["reading_logged"]}, unit="actions",
            timezone_name="America/Phoenix", starts_at=start, ends_at=start + timedelta(days=45),
        )
        row = ChallengeOccurrence.objects.create(
            goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at, snapshot=_snapshot(goal),
            progress=20, status="completed", completed_at=self.now - timedelta(days=40),
        )
        ChallengeOccurrence.objects.filter(pk=row.pk).update(created_at=start)

    def invoke(self, *, scopes=frozenset({READ_SCOPE}), params=None, actor=None):
        async def run():
            with override_user(actor or self.parent, scopes=scopes):
                try:
                    return await mcp._tool_manager.get_tool("get_voyager_feedback").run({"params": params or {}})
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def test_native_service_rest_and_mcp_return_the_same_readonly_household_aggregate(self):
        from apps.quests.voyager_feedback import voyager_feedback
        client = APIClient()
        client.force_authenticate(self.parent)
        rest = client.get("/api/challenges/voyager-feedback/")
        self.assertEqual(rest.status_code, 200)
        before = {model._meta.label: list(model.objects.order_by("pk").values()) for model in (
            ChallengeGoal, ChallengeOccurrence, ChallengeEnrollment, CoinLedger, UserInventory,
        )}
        with CaptureQueriesContext(connection) as queries, override_user(self.parent):
            result = challenges.get_voyager_feedback(GetVoyagerFeedbackIn())
        self.assertEqual(result, voyager_feedback(self.parent))
        self.assertEqual(result, rest.json())
        self.assertEqual(json.loads(json.dumps(result)), result)
        self.assertEqual(result["cohort"]["eligible_children"], 2)
        self.assertEqual(result["current_states"]["completed"], 1)
        self.assertEqual(result["current_states"]["ready"], 1)
        groups = {row["policy"]: row for row in result["policy_groups"]}
        self.assertEqual(groups["saved_45_day"]["accepted_windows"], 1)
        self.assertEqual(groups["saved_45_day"]["mature_denominator"], 1)
        self.assertEqual(groups["saved_45_day"]["completion_rate"], 1)
        self.assertFalse(any(row["sql"].lstrip().upper().startswith((
            "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP")) for row in queries))
        self.assertEqual(before, {model._meta.label: list(model.objects.order_by("pk").values()) for model in (
            ChallengeGoal, ChallengeOccurrence, ChallengeEnrollment, CoinLedger, UserInventory,
        )})
        for private in [self.child.username, self.other_child.username, "Private saved presentation", "user_id", "goal_id"]:
            self.assertNotIn(private, json.dumps(result))

    def test_read_grant_invokes_real_report_and_catalog_only_is_hidden_and_denied(self):
        async def names(scopes):
            with override_user(self.parent, scopes=scopes):
                return {entry.name for entry in await mcp.list_tools()}
        self.assertIn("get_voyager_feedback", async_to_sync(names)(frozenset({READ_SCOPE})))
        self.assertNotIn("get_voyager_feedback", async_to_sync(names)(frozenset({CATALOG_SCOPE})))
        result = self.invoke()
        self.assertEqual(result["cohort"]["eligible_children"], 2)
        with self.assertRaisesRegex(ToolError, "mcp:read permission"):
            self.invoke(scopes=frozenset({CATALOG_SCOPE}))
        for scope in MCP_SCOPES - {READ_SCOPE, CATALOG_SCOPE}:
            with self.subTest(scope=scope), self.assertRaisesRegex(ToolError, "mcp:read permission"):
                self.invoke(scopes=frozenset({scope}))

    def test_registered_adapter_rejects_selectors(self):
        for params in [{"user_id": self.child.pk}, {"family_id": self.other_parent.family_id}, {"as_of": self.now.isoformat()}]:
            with self.subTest(params=params), self.assertRaises(ToolError):
                self.invoke(params=params)

    def test_children_nonstaff_and_missing_identity_are_denied(self):
        for actor in [self.child, None]:
            with self.subTest(actor=actor), override_user(actor), self.assertRaises(MCPPermissionDenied):
                challenges.get_voyager_feedback(GetVoyagerFeedbackIn())
        self.parent.is_staff = False
        with override_user(self.parent), self.assertRaises(MCPPermissionDenied):
            challenges.get_voyager_feedback(GetVoyagerFeedbackIn())

    def test_fresh_service_revalidation_denies_stale_staff_role_activity_and_family(self):
        changes = [{"is_staff": False}, {"is_active": False}, {"role": "child"},
                   {"family_id": self.other_parent.family_id}]
        for changed in changes:
            with self.subTest(changed=changed):
                get_user_model().objects.filter(pk=self.parent.pk).update(**changed)
                # The context still contains the previous staff-parent object;
                # the native service must recheck the saved account itself.
                with override_user(self.parent), self.assertRaises(MCPPermissionDenied):
                    challenges.get_voyager_feedback(GetVoyagerFeedbackIn())
                get_user_model().objects.filter(pk=self.parent.pk).update(
                    is_staff=True, is_active=True, role="parent", family_id=self.parent.family_id)

    def test_trusted_observer_exclusion_is_preserved_in_the_mcp_result(self):
        LiveTestFamily.objects.create(namespace="mcp-voyager-fixture", family=self.parent.family,
                                      parent=self.parent, child=self.child)
        result = self.invoke()
        self.assertTrue(result["cohort"]["observer_family_excluded"])
        self.assertEqual(result["cohort"]["eligible_children"], 0)
        self.assertEqual(result["status"], "insufficient_evidence")
