"""Real MCP dispatch reaches the existing reviewed database authoring services."""
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase
from mcp.server.fastmcp.exceptions import ToolError

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rewards.models import Reward
from apps.rpg.content.workbench import create_draft
from apps.rpg.models import ContentPackEntry, ContentPackPublication, ItemDefinition, RPGContentDraft, UserInventory
from apps.rpg.progression_views import ProgressionSimulationThrottle
from apps.rpg.workbench_views import WorkbenchSimulationThrottle
from config.tests.factories import make_family


TOOLS = {
    "get_content_workbench", "list_content_drafts", "get_content_draft", "create_content_draft",
    "save_content_draft", "preview_content_draft", "simulate_content_draft", "publish_content_draft",
    "get_progression_lab", "simulate_progression_scenario",
}


class ContentWorkbenchToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.a = make_family("Workbench A", parents=[{"username": "wb-ap", "is_staff": True}, {"username": "wb-coparent", "is_staff": True}])
        self.b = make_family("Workbench B", parents=[{"username": "wb-bp", "is_staff": True}])
        self.actor = self.a.parents[0]
        self.item = ItemDefinition.objects.create(slug="workbench-apple", name="Apple", description="Synthetic", icon="x", item_type="food", coin_value=2)

    def invoke(self, name, params=None, *, scopes=("mcp:author",), actor=None, **arguments):
        entry = mcp._tool_manager.get_tool(name)
        self.assertIsNotNone(entry, f"Missing MCP workflow: {name}")

        async def run():
            with override_user(actor or self.actor, scopes=frozenset(scopes)):
                try:
                    result = await entry.run({"params": params or {}, **arguments}, convert_result=True)
                    return result[1] if isinstance(result, tuple) else result
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def draft(self, *, values=None):
        draft = self.invoke("create_content_draft", {"name": "Reviewed design"})
        return self.invoke("save_content_draft", {
            "draft_id": draft["id"], "revision": draft["revision"], "changes": [{
                "section": "items", "object_id": self.item.pk, "key": "apple",
                "values": values or {"name": "Bright Apple"},
            }],
        }, confirmation=True)

    def test_bridge_tools_are_registered_with_concrete_output_contracts(self):
        registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
        self.assertFalse(TOOLS - set(registered), f"Missing MCP workflows: {TOOLS - set(registered)}")
        for name in TOOLS:
            with self.subTest(tool=name):
                self.assertIsNotNone(registered[name].output_schema)
        for name in ("get_content_workbench", "get_content_draft", "list_content_drafts", "get_progression_lab", "simulate_progression_scenario"):
            self.assertTrue(registered[name].annotations.readOnlyHint)
        self.assertTrue(registered["publish_content_draft"].annotations.destructiveHint)
        self.assertTrue(registered["publish_content_draft"].annotations.idempotentHint)

    def test_review_simulate_publish_preserves_identity_and_replays(self):
        draft = self.draft()
        reviewed = self.invoke("preview_content_draft", {"draft_id": draft["id"], "revision": draft["revision"]})
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Apple")
        plan = reviewed["preview"]
        publish = {"draft_id": draft["id"], "revision": draft["revision"], "preview_id": plan["preview_id"], "content_digest": plan["content_digest"]}
        with self.assertRaisesRegex(ToolError, "Simulate"):
            self.invoke("publish_content_draft", publish, scopes=("mcp:publish",), confirmation=True)
        comparison = self.invoke("simulate_content_draft", {
            "draft_id": draft["id"], "revision": draft["revision"], "preview_id": plan["preview_id"],
            "config": {"horizon_days": 30, "trials": 1},
        })
        self.assertEqual(comparison["baseline"]["config"], comparison["proposed"]["config"])
        first = self.invoke("publish_content_draft", publish, scopes=("mcp:publish",), confirmation=True)
        replay = self.invoke("publish_content_draft", publish, scopes=("mcp:publish",), confirmation=True)
        self.assertEqual(first, replay)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Bright Apple")
        self.assertEqual(ItemDefinition.objects.filter(pk=self.item.pk).count(), 1)

    def test_draft_list_and_details_are_bound_to_actor_and_family(self):
        own = self.invoke("create_content_draft", {"name": "Own design"})
        create_draft(self.a.parents[1], "Other author private design")
        foreign = create_draft(self.b.parents[0], "Other family private design")
        page = self.invoke("list_content_drafts", {"limit": 1})
        self.assertEqual([row["id"] for row in page["drafts"]], [own["id"]])
        self.assertIsNone(page["next_after"])
        with self.assertRaisesRegex(ToolError, "not found"):
            self.invoke("get_content_draft", {"draft_id": foreign["id"]})
        with self.assertRaisesRegex(ToolError, "not found"):
            self.invoke("get_content_draft", {"draft_id": own["id"]}, actor=self.a.parents[1])

    def test_draft_summaries_traverse_all_pages_without_returning_private_changes(self):
        own = {self.invoke("create_content_draft", {"name": f"Design {index}"})["id"] for index in range(4)}
        first = self.invoke("list_content_drafts", {"limit": 2})
        second = self.invoke("list_content_drafts", {"limit": 2, "after": first["next_after"]})
        rows = first["drafts"] + second["drafts"]
        self.assertEqual({row["id"] for row in rows}, own)
        self.assertEqual(len(rows), 4)
        self.assertEqual((first["total"], second["total"]), (4, 4))
        self.assertIsNone(second["next_after"])
        self.assertTrue(all("changes" not in row for row in rows))

    def test_wire_conflicts_and_private_misses_keep_structured_domain_codes(self):
        draft = self.invoke("create_content_draft", {"name": "Own design"})
        foreign = create_draft(self.b.parents[0], "Private design")

        async def call(name, params, **arguments):
            with override_user(self.actor, scopes=frozenset({"mcp:author"})):
                try:
                    return await mcp.call_tool(name, {"params": params, **arguments})
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        missing = async_to_sync(call)("get_content_draft", {"draft_id": foreign["id"]})
        self.assertTrue(missing.isError)
        self.assertEqual(missing.structuredContent["error"]["code"], "not_found")
        self.assertNotIn("Private design", str(missing))
        conflict = async_to_sync(call)("save_content_draft", {
            "draft_id": draft["id"], "revision": draft["revision"] + 1, "changes": [],
        }, confirmation=True)
        self.assertTrue(conflict.isError)
        self.assertEqual(conflict.structuredContent["error"]["code"], "content_workbench_conflict")

    def test_catalog_references_never_query_or_expose_family_shop_usage(self):
        Reward.objects.create(family=self.a.family, name="Private household shop offer", item_definition=self.item, cost_coins=7)
        with patch("apps.rewards.models.Reward.objects.filter", side_effect=AssertionError("Catalog must not query household offers")):
            result = self.invoke("get_content_workbench", {"section": "items"}, scopes=("mcp:catalog",))
        self.assertEqual(result["results"][0]["id"], self.item.pk)
        self.assertNotIn("shop", json.dumps(result).lower())
        self.assertNotIn("Private household", json.dumps(result))
        self.assertEqual(RPGContentDraft.objects.count(), 0)

    def test_scopes_confirmation_ownership_and_revision_guards_still_apply(self):
        draft = self.draft()
        with self.assertRaisesRegex(ToolError, "permission"):
            self.invoke("get_content_draft", {"draft_id": draft["id"]}, scopes=("mcp:catalog",))
        with self.assertRaisesRegex(ToolError, "confirmation"):
            self.invoke("save_content_draft", {"draft_id": draft["id"], "revision": draft["revision"], "changes": []})
        with self.assertRaisesRegex(ToolError, "revision"):
            self.invoke("save_content_draft", {"draft_id": draft["id"], "revision": draft["revision"] - 1, "changes": []}, confirmation=True)
        ContentPackEntry.objects.create(pack="other-owner", family=self.b.family, kind="itemdefinition", key="apple", model_label="rpg.itemdefinition", object_id=self.item.pk)
        with self.assertRaisesRegex(ToolError, "another family"):
            self.draft(values={"name": "Forbidden"})

    def test_long_horizon_progression_is_anonymous_and_bounded(self):
        before = (RPGContentDraft.objects.count(), ContentPackPublication.objects.count(), UserInventory.objects.count())
        metadata = self.invoke("get_progression_lab", scopes=("mcp:catalog",))
        self.assertIn(365, metadata["limits"]["horizon_days"]["choices"])
        report = self.invoke("simulate_progression_scenario", {"config": {"horizon_days": 365, "trials": 1}}, scopes=("mcp:catalog",))
        self.assertEqual(report["config"]["horizon_days"], 365)
        self.assertEqual(len(report["trace"]), 365)
        self.assertEqual(before, (RPGContentDraft.objects.count(), ContentPackPublication.objects.count(), UserInventory.objects.count()))
        for config in ({"user_id": self.actor.pk}, {"horizon_days": 365, "trials": 40}, {"horizon_days": True}):
            with self.subTest(config=config), self.assertRaises(ToolError):
                self.invoke("simulate_progression_scenario", {"config": config}, scopes=("mcp:catalog",))

    def test_simulation_quotas_share_the_native_workbench_and_lab_buckets(self):
        request = SimpleNamespace(user=self.actor)
        with patch.object(ProgressionSimulationThrottle, "rate", "1/min"):
            self.assertTrue(ProgressionSimulationThrottle().allow_request(request, None))
            with self.assertRaisesRegex(ToolError, "rate limit"):
                self.invoke("simulate_progression_scenario", {"config": {"trials": 1, "horizon_days": 30}}, scopes=("mcp:catalog",))
        draft = self.draft()
        reviewed = self.invoke("preview_content_draft", {"draft_id": draft["id"], "revision": draft["revision"]})
        with patch.object(WorkbenchSimulationThrottle, "rate", "1/min"):
            self.assertTrue(WorkbenchSimulationThrottle().allow_request(request, None))
            with self.assertRaisesRegex(ToolError, "rate limit"):
                self.invoke("simulate_content_draft", {"draft_id": draft["id"], "revision": draft["revision"], "preview_id": reviewed["preview"]["preview_id"], "config": {"trials": 1, "horizon_days": 30}})

    def test_private_operations_recheck_database_permissions_before_native_calls(self):
        draft = self.draft()
        identity = {"draft_id": draft["id"], "revision": draft["revision"]}
        operations = [
            ("list_content_drafts", {}, None, {}),
            ("get_content_draft", {"draft_id": draft["id"]}, "get_draft", {}),
            ("create_content_draft", {"name": "Revoked author"}, "create_draft", {}),
            ("save_content_draft", {**identity, "changes": []}, "save_draft", {"confirmation": True}),
            ("preview_content_draft", identity, "preview_draft", {}),
            ("simulate_content_draft", {**identity, "preview_id": str(uuid4()), "config": {"trials": 1, "horizon_days": 30}}, "simulate_draft", {}),
            ("publish_content_draft", {**identity, "preview_id": str(uuid4()), "content_digest": "0" * 64}, "publish_draft", {"confirmation": True, "scopes": ("mcp:publish",)}),
        ]
        users = get_user_model().objects.filter(pk=self.actor.pk)
        original = {"role": self.actor.role, "is_staff": self.actor.is_staff, "is_active": self.actor.is_active, "family_id": self.actor.family_id}
        for revoked in ({"role": "child"}, {"is_staff": False}, {"is_active": False}, {"family_id": self.b.family.pk}):
            users.update(**revoked)
            try:
                for name, params, native, arguments in operations:
                    with self.subTest(revoked=revoked, tool=name):
                        if native is None:
                            with self.assertRaisesRegex(ToolError, "permissions have changed"):
                                self.invoke(name, params, **arguments)
                        else:
                            with patch(f"apps.rpg.content.workbench.{native}", side_effect=AssertionError("Stale author reached native service")) as service:
                                with self.assertRaisesRegex(ToolError, "permissions have changed"):
                                    self.invoke(name, params, **arguments)
                                service.assert_not_called()
            finally:
                users.update(**original)

    def test_revoked_author_cannot_publish_reviewed_draft_or_replay_publication(self):
        draft = self.draft()
        reviewed = self.invoke("preview_content_draft", {"draft_id": draft["id"], "revision": draft["revision"]})
        plan = reviewed["preview"]
        self.invoke("simulate_content_draft", {
            "draft_id": draft["id"], "revision": draft["revision"], "preview_id": plan["preview_id"],
            "config": {"horizon_days": 30, "trials": 1},
        })
        publish = {"draft_id": draft["id"], "revision": draft["revision"], "preview_id": plan["preview_id"], "content_digest": plan["content_digest"]}
        users = get_user_model().objects.filter(pk=self.actor.pk)
        users.update(is_staff=False)
        with self.assertRaises(ToolError):
            self.invoke("publish_content_draft", publish, scopes=("mcp:publish",), confirmation=True)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Apple")
        self.assertIsNone(RPGContentDraft.objects.get(pk=draft["id"]).published_at)
        users.update(is_staff=True)
        self.invoke("publish_content_draft", publish, scopes=("mcp:publish",), confirmation=True)
        users.update(is_active=False)
        with self.assertRaisesRegex(ToolError, "permissions have changed"):
            self.invoke("publish_content_draft", publish, scopes=("mcp:publish",), confirmation=True)
