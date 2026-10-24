"""Private challenge names do not reserve identities in the public workbench."""
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.models import Quest, QuestDefinition, QuestRewardItem
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import ItemDefinition, RPGContentOverride
from config.tests.factories import make_family


class ContentWorkbenchNameScopeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = make_family("Public content author", parents=[
            {"username": "public-name-author", "is_staff": True},
        ]).parents[0]
        self.other = make_family("Private content household", parents=[
            {"username": "private-name-parent", "is_staff": True},
        ]).parents[0]
        self.public = self.public_definition("Public practice")
        self.item = ItemDefinition.objects.create(slug="public-practice-snack", name="Saved snack",
            icon="x", item_type="food", coin_value=2)
        QuestRewardItem.objects.create(quest_definition=self.public, item=self.item, quantity=2)

    def public_definition(self, name, **values):
        return QuestDefinition.objects.create(name=name, description="Public instructions", icon="x",
            is_system=True, quest_type="collection", target_value=3, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]}, **values)

    def private_definition(self, actor, name):
        client = APIClient()
        client.force_authenticate(actor)
        response = client.post("/api/quests/", {
            "name": name, "description": "Private household instructions", "quest_type": "collection",
            "target_value": 3, "duration_days": 7,
            "trigger_filter": {"allowed_triggers": ["chore_complete"]},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        definition = QuestDefinition.objects.get(pk=response.data["id"])
        self.assertFalse(definition.is_system)
        self.assertEqual(definition.created_by_id, actor.pk)
        return definition

    def response(self, name, params):
        with override_user(self.actor, scopes=frozenset({"mcp:author", "mcp:publish", "mcp:catalog"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        if isinstance(result, tuple):
            return True, result[1]
        return not result.isError, result.structuredContent

    def wire(self, name, params):
        success, result = self.response(name, params)
        self.assertTrue(success, result)
        return result

    def draft(self, values=None, *, definition=None):
        draft = self.wire("create_content_draft", {"name": "Public metadata correction"})
        return self.wire("save_content_draft", {"draft_id": draft["id"], "revision": draft["revision"],
            "changes": [{"section": "quests", "object_id": (definition or self.public).pk,
                "key": "public-edit", "values": values or {"description": "Clarified public instructions"}}]})

    def preview(self, draft):
        return self.wire("preview_content_draft", {"draft_id": draft["id"], "revision": draft["revision"]})

    def publish(self, draft):
        reviewed = self.preview(draft)
        plan = reviewed["preview"]
        params = {"draft_id": draft["id"], "revision": draft["revision"],
            "preview_id": plan["preview_id"], "content_digest": plan["content_digest"]}
        self.wire("simulate_content_draft", {key: value for key, value in {
            **params, "config": {"horizon_days": 30, "trials": 1},
        }.items() if key != "content_digest"})
        published = self.wire("publish_content_draft", params)
        self.assertEqual(self.wire("publish_content_draft", params), published)
        return published

    def assert_preview_rejected(self, draft, message):
        success, result = self.response("preview_content_draft", {
            "draft_id": draft["id"], "revision": draft["revision"],
        })
        self.assertFalse(success, result)
        self.assertIn(message, result["error"]["message"])
        self.public.refresh_from_db()
        self.assertEqual(self.public.name, "Public practice")
        self.assertEqual(self.public.description, "Public instructions")

    def test_other_family_private_name_allows_exact_public_edit_publish_replay_and_reload(self):
        private = self.private_definition(self.other, self.public.name)
        accepted = Quest.objects.create(definition=self.public, end_date=timezone.now() + timedelta(days=7))
        published = self.publish(self.draft())
        self.assertIsNotNone(published["published_at"])
        self.assertNotIn("Private household instructions", json.dumps(published))
        self.public.refresh_from_db()
        private.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual(self.public.description, "Clarified public instructions")
        self.assertEqual(self.public.name, private.name)
        self.assertEqual(private.description, "Private household instructions")
        self.assertFalse(private.is_system)
        self.assertEqual(list(self.public.reward_items.values_list("item_id", "quantity")), [(self.item.pk, 2)])
        self.assertEqual(accepted.reward_items_snapshot[0]["item_id"], self.item.pk)
        self.assertEqual(accepted.reward_items_snapshot[0]["quantity"], 2)
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "quests.yaml").write_text("quests:\n- name: Public practice\n  description: Bundled instructions\n"
                "  quest_type: collection\n  target_value: 3\n", encoding="utf-8")
            ContentPack(path).load()
        self.public.refresh_from_db()
        self.assertEqual(self.public.description, "Clarified public instructions")
        self.assertEqual(QuestDefinition.objects.filter(is_system=True, name=self.public.name).count(), 1)

    def test_same_author_private_name_allows_public_preview(self):
        self.private_definition(self.actor, self.public.name)
        reviewed = self.preview(self.draft())
        self.assertTrue(reviewed["preview"]["changes"])
        self.assertNotIn("Private household instructions", json.dumps(reviewed))
        self.public.refresh_from_db()
        self.assertEqual(self.public.description, "Public instructions")

    def test_distinct_private_name_does_not_affect_public_preview(self):
        self.private_definition(self.other, "Private practice")
        self.assertTrue(self.preview(self.draft())["preview"]["changes"])

    def test_real_public_duplicate_still_blocks_unchanged_name_edit(self):
        self.public_definition(self.public.name)
        self.assert_preview_rejected(self.draft(), "Challenge name collides")

    def test_public_definition_with_creator_still_reserves_its_public_name(self):
        self.public_definition(self.public.name, created_by=self.other)
        self.assert_preview_rejected(self.draft(), "Challenge name collides")

    def test_rename_to_another_public_name_remains_blocked(self):
        other = self.public_definition("Another public practice")
        self.assert_preview_rejected(self.draft({"name": other.name}), "Challenge name collides")

    def test_authored_badge_named_dependency_still_blocks_rename(self):
        Badge.objects.create(name="Named practice badge", description="Preserved named rule", icon="x",
            criteria_type="quest_completed", criteria_value={"quest_name": self.public.name})
        self.assert_preview_rejected(self.draft({"name": "Renamed public practice"}), "A badge refers")

    def test_public_source_identity_remains_reserved_after_authored_rename(self):
        original = self.public.name
        self.publish(self.draft({"name": "Renamed public practice"}))
        override = RPGContentOverride.objects.get(model_label="quests.questdefinition", object_id=self.public.pk)
        self.assertEqual(override.source_lookup, {"name": original})
        other = self.public_definition("Different public practice")
        draft = self.wire("create_content_draft", {"name": "Source identity collision"})
        success, result = self.response("save_content_draft", {
            "draft_id": draft["id"], "revision": draft["revision"],
            "changes": [{"section": "quests", "object_id": other.pk, "key": "other-public",
                "values": {"name": original}}],
        })
        self.assertFalse(success, result)
        self.assertIn("source identity is retained", result["error"]["message"])
        other.refresh_from_db()
        self.assertEqual(other.name, "Different public practice")

    def test_private_row_cannot_be_selected_as_public_content(self):
        private = self.private_definition(self.other, self.public.name)
        draft = self.wire("create_content_draft", {"name": "Private row is not public"})
        success, result = self.response("save_content_draft", {
            "draft_id": draft["id"], "revision": draft["revision"],
            "changes": [{"section": "quests", "object_id": private.pk, "key": "private-edit",
                "values": {"description": "Must not be applied"}}],
        })
        self.assertFalse(success, result)
        self.assertEqual(result["error"]["code"], "not_found")
        self.assertNotIn("Private household instructions", json.dumps(result))
        private.refresh_from_db()
        self.assertEqual(private.description, "Private household instructions")
