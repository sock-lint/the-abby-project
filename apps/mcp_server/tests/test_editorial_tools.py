"""Textual publication is private, revisioned and inert until exact approval."""
from copy import deepcopy
from datetime import timedelta
import json
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import TestCase
from django.utils import timezone

from apps.lorebook.services import load_lorebook_catalog
from apps.mcp_server.context import override_user
from apps.mcp_server.editorial_schemas import (
    CreateEditorialDraftIn, EditorialDraftIn, EditorialDraftPage, EditorialDraftResult,
    EditorialRevisionIn, ListEditorialDraftsIn, PublishEditorialDraftIn, SaveEditorialDraftIn,
)
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import editorial as tools
from apps.rpg.content.editorial import editorial_catalog
from apps.rpg.models import RPGEditorialDraft, RPGEditorialOverride
from apps.wellbeing.services import _load_affirmations, _resolve_affirmation
from config.tests.factories import make_family


class EditorialPublicationTests(TestCase):
    def setUp(self):
        a = make_family("Editorial A", parents=[{"username": "editor-a", "is_staff": True}])
        b = make_family("Editorial B", parents=[{"username": "editor-b", "is_staff": True}])
        self.actor, self.other = a.parents[0], b.parents[0]

    def call(self, tool, schema, **values):
        with override_user(self.actor):
            return tool(schema(**values))

    def draft(self, section="lorebook", changes=None):
        draft = self.call(tools.create_editorial_draft, CreateEditorialDraftIn, section=section, name="Copy review")
        return self.call(tools.save_editorial_draft, SaveEditorialDraftIn, draft_id=draft["id"], revision=1,
            changes=changes or [{"slug": "duties", "values": {"title": "Shared chores"}}])

    def preview(self, draft):
        return self.call(tools.preview_editorial_draft, EditorialRevisionIn, draft_id=draft["id"], revision=draft["revision"])

    def publish(self, draft, **changes):
        values = dict(draft_id=draft["id"], revision=draft["revision"], preview_id=draft["preview"]["id"],
            content_digest=draft["preview"]["content_digest"])
        return self.call(tools.publish_editorial_draft, PublishEditorialDraftIn, **{**values, **changes})

    def test_exact_publication_refreshes_cached_copy_and_retries_once(self):
        original = next(row for row in load_lorebook_catalog() if row["slug"] == "duties")
        draft = self.preview(self.draft())
        self.assertEqual(next(row for row in load_lorebook_catalog() if row["slug"] == "duties"), original)
        published = self.publish(draft)
        row = next(row for row in load_lorebook_catalog() if row["slug"] == "duties")
        self.assertEqual(row["title"], "Shared chores")
        self.assertEqual(row["trial"], original["trial"])
        self.assertEqual(self.publish(draft), published)
        self.assertEqual(RPGEditorialOverride.objects.count(), 1)

    def test_large_editorial_drafts_have_compact_summary_pages_and_complete_details(self):
        # Each valid save stays below the tool's 200 KB input limit, while
        # its reviewed before/after copy makes the detail response larger.
        changes = [{"slug": row["slug"], "values": {
            "kid_voice": "Draft copy only. " + "x" * 9983,
            "mechanics": [f"Reviewed line {index}. " + "y" * 970 for index in range(30)],
        }} for row in load_lorebook_catalog()[:4]]
        self.assertGreater(len(json.dumps(changes).encode()), 150000)
        self.assertLess(len(json.dumps(changes).encode()), 200000)
        reviewed = [self.preview(self.draft(changes=changes)) for _ in range(4)]
        empty = self.call(tools.create_editorial_draft, CreateEditorialDraftIn,
                          section="affirmations", name="Unreviewed copy")
        own = {row["id"]: row for row in [*reviewed, empty]}
        with override_user(self.other):
            tools.create_editorial_draft(CreateEditorialDraftIn(section="lorebook", name="Private other family"))

        rows, after = [], None
        while True:
            page = self.call(tools.list_editorial_drafts, ListEditorialDraftsIn, after=after, limit=2)
            self.assertLess(len(json.dumps(page).encode()), 4096,
                            "Listing must not multiply large saved copy or previews by the page size.")
            EditorialDraftPage.model_validate(page)
            self.assertLessEqual(len(page["drafts"]), 2)
            for row in page["drafts"]:
                self.assertEqual(set(row), {"id", "section", "name", "revision", "is_archived", "published_at", "has_preview", "updated_at"})
                self.assertEqual(row["has_preview"], bool(own[row["id"]]["preview"]))
            rows.extend(page["drafts"])
            if page["next_after"] is None:
                break
            self.assertNotEqual(page["next_after"], after)
            after = page["next_after"]
        self.assertEqual(len(rows), len(own))
        self.assertEqual({row["id"] for row in rows}, set(own))
        self.assertEqual([row["id"] for row in rows], sorted(own))

        detail = self.call(tools.get_editorial_draft, EditorialDraftIn, draft_id=reviewed[0]["id"])
        EditorialDraftResult.model_validate(detail)
        self.assertGreater(len(json.dumps(detail).encode()), 300000)
        self.assertEqual(detail["changes"], changes)
        self.assertEqual(detail["preview"], reviewed[0]["preview"])

    def test_drafts_are_bound_to_actor_and_family(self):
        draft = self.preview(self.draft())
        with override_user(self.other), self.assertRaises(MCPNotFoundError):
            tools.get_editorial_draft(EditorialDraftIn(draft_id=draft["id"]))
        self.publish(draft)
        with override_user(self.other):
            other = tools.create_editorial_draft(CreateEditorialDraftIn(section="lorebook", name="Other"))
            with self.assertRaises(MCPPermissionDenied):
                tools.save_editorial_draft(SaveEditorialDraftIn(draft_id=other["id"], revision=1,
                    changes=[{"slug": "duties", "values": {"title": "Other edit"}}]))

    def test_wire_rejects_other_familys_published_entry_as_permission_denied_without_writes(self):
        self.publish(self.preview(self.draft()))
        with override_user(self.other):
            other = tools.create_editorial_draft(CreateEditorialDraftIn(section="lorebook", name="Other"))
        before = (list(RPGEditorialDraft.objects.order_by("pk").values()),
                  list(RPGEditorialOverride.objects.order_by("pk").values()))
        with override_user(self.other):
            response = async_to_sync(mcp.call_tool)("save_editorial_draft", {
                "params": {"draft_id": other["id"], "revision": 1,
                           "changes": [{"slug": "duties", "values": {"title": "Other edit"}}]},
                "confirmation": True,
            })
        payload = response.structuredContent if hasattr(response, "structuredContent") else response[1]
        self.assertEqual(payload, {"error": {
            "code": "permission_denied",
            "message": "This editorial entry is owned by another family or needs reconciliation.",
            "retryable": False, "field_errors": {},
        }})
        self.assertEqual((list(RPGEditorialDraft.objects.order_by("pk").values()),
                          list(RPGEditorialOverride.objects.order_by("pk").values())), before)

    def test_revisions_catalog_changes_expiry_and_wrong_preview_cannot_publish(self):
        draft = self.preview(self.draft())
        with self.assertRaises(MCPValidationError):
            self.publish(draft, preview_id=str(uuid4()))
        with self.assertRaises(MCPValidationError):
            self.publish(draft, revision=1)
        row = RPGEditorialDraft.objects.get(pk=draft["id"])
        expired = deepcopy(row.preview)
        expired["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
        RPGEditorialDraft.objects.filter(pk=row.pk).update(preview=expired)
        with self.assertRaises(MCPValidationError):
            self.publish(draft)
        draft = self.preview(draft)
        RPGEditorialOverride.objects.create(section="lorebook", slug="skills", family=self.actor.family, values={"title": "New title"})
        with self.assertRaises(MCPValidationError):
            self.publish(draft)
        self.assertFalse(RPGEditorialOverride.objects.filter(slug="duties").exists())

    def test_affirmation_retirement_preserves_historical_resolution(self):
        slug = _load_affirmations()[0]["slug"]
        original = _resolve_affirmation(slug)
        draft = self.preview(self.draft("affirmations", [{"slug": slug, "values": {"is_active": False}}]))
        self.publish(draft)
        self.assertNotIn(slug, {row["slug"] for row in _load_affirmations()})
        self.assertEqual(_resolve_affirmation(slug), original)
        self.assertTrue(any(row["slug"] == slug and not row["is_active"] for row in editorial_catalog("affirmations")))

    def test_new_affirmation_and_updated_copy_are_visible_without_cache_clear(self):
        _load_affirmations()
        draft = self.preview(self.draft("affirmations", [{"slug": "synthetic-affirmation", "values": {
            "text": "A small step counts.", "tone": "gentle"}}]))
        self.publish(draft)
        self.assertEqual(_resolve_affirmation("synthetic-affirmation")["text"], "A small step counts.")

    def test_stale_actor_permissions_are_rechecked_before_publication(self):
        draft = self.preview(self.draft())
        type(self.actor).objects.filter(pk=self.actor.pk).update(is_staff=False)
        with self.assertRaises(MCPPermissionDenied):
            self.publish(draft)
        self.assertEqual(RPGEditorialOverride.objects.count(), 0)

    def test_cannot_change_logic_create_unknown_lorebook_handler_or_empty_pool(self):
        for values in ({"trial": {"prompt": "Changed"}}, {"economy": {"coins": True}}, {"is_active": False}):
            with self.subTest(values=values), self.assertRaises(MCPValidationError):
                self.draft(changes=[{"slug": "duties", "values": values}])
        with self.assertRaises(MCPValidationError):
            self.draft(changes=[{"slug": "new-handler", "values": {"title": "New"}}])
        with self.assertRaises(MCPValidationError):
            self.draft("affirmations", [{"slug": row["slug"], "values": {"is_active": False}} for row in _load_affirmations()])
        self.assertEqual(RPGEditorialOverride.objects.count(), 0)
