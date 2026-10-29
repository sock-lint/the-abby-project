"""Completed publication receipts survive disposal of their draft source files."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import User
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import content_packs
from apps.rpg.content import publication
from apps.rpg.models import ContentPackEntry, ContentPackPublication, ItemDefinition
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DeletedPackPublicationReplayTests(TestCase):
    pack = "saved-publication"
    scopes = frozenset({"mcp:catalog", "mcp:author", "mcp:publish"})

    def setUp(self):
        home = make_family("Saved publication", parents=[
            {"username": "publication-author", "is_staff": True},
            {"username": "publication-coparent", "is_staff": True},
        ])
        self.actor, self.coparent = home.parents
        self.foreign = make_family("Foreign publication", parents=[
            {"username": "publication-foreign", "is_staff": True},
        ]).parents[0]
        temporary = TemporaryDirectory(prefix="abby-saved-publication-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "packs"
        root_patch = patch.object(content_packs, "_packs_root", return_value=self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def wire(self, name, params, *, actor=None, confirmation=True, scopes=None):
        with override_user(actor or self.actor, scopes=self.scopes if scopes is None else scopes):
            result = async_to_sync(mcp.call_tool)(name, {
                "params": params, "confirmation": confirmation,
            })
        return result.structuredContent if hasattr(result, "structuredContent") else result[1]

    def ok(self, value):
        self.assertNotIn("error", value, value)
        return value

    def error(self, value, code=None):
        self.assertIn("error", value, value)
        if code is not None:
            self.assertEqual(value["error"]["code"], code, value)
        return value

    def prepare(self, *, publish=True, delete=True):
        self.ok(self.wire("write_pack_file", {
            "pack": self.pack, "filename": "items.yaml",
            "yaml_content": "items:\n  - slug: biscuit\n    name: Saved biscuit\n"
                            "    item_type: food\n    rarity: common\n    coin_value: 1\n",
        }))
        preview = self.ok(self.wire("preview_content_pack", {"pack": self.pack}))
        self.params = {key: preview[key] for key in ("pack", "preview_id", "content_digest")}
        self.published = self.ok(self.wire("publish_content_pack", self.params)) if publish else None
        if delete:
            self.ok(self.wire("delete_content_pack", {"pack": self.pack, "confirm": True}))
            self.assertFalse((self.root / self.pack).exists())

    def snapshot(self):
        return {
            "items": list(ItemDefinition.objects.order_by("pk").values()),
            "entries": list(ContentPackEntry.objects.order_by("pk").values()),
            "receipts": list(ContentPackPublication.objects.order_by("pk").values()),
        }

    def test_registered_replay_after_source_deletion_matches_native_without_writes(self):
        self.prepare()
        before = self.snapshot()
        native = publication.publish_content_pack(
            self.root / self.pack, self.pack, self.actor,
            self.params["preview_id"], self.params["content_digest"],
        )
        self.assertEqual(native, self.published)
        with CaptureQueriesContext(connection) as queries:
            replayed = self.ok(self.wire("publish_content_pack", self.params))
        self.assertEqual(replayed, self.published)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / self.pack).exists())
        mutations = [query["sql"] for query in queries
                     if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(mutations, [])

    def test_registered_load_alias_replays_same_completed_receipt(self):
        self.prepare()
        self.assertEqual(self.ok(self.wire("load_content_pack", self.params)), self.published)

    def test_completed_replay_does_not_need_a_packs_root_or_read_source(self):
        self.prepare()
        missing_root = self.root.parent / "missing-packs"
        with patch.object(content_packs, "_packs_root", return_value=missing_root), \
                patch.object(publication, "_read_source", side_effect=AssertionError("Replayed source read")):
            self.assertEqual(self.ok(self.wire("publish_content_pack", self.params)), self.published)
        self.assertFalse(missing_root.exists(), "Replay must not create even a lock directory")

    def test_wrong_digest_cannot_replay_or_recreate_deleted_source(self):
        self.prepare()
        before = self.snapshot()
        digest = "a" * 64 if self.params["content_digest"] != "a" * 64 else "b" * 64
        self.error(self.wire("publish_content_pack", {**self.params, "content_digest": digest}))
        self.error(self.wire("publish_content_pack", {**self.params, "content_digest": "invalid"}))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / self.pack).exists())

    def test_foreign_author_and_missing_receipt_are_indistinguishable(self):
        self.prepare()
        before = self.snapshot()
        for actor in (self.coparent, self.foreign):
            with self.subTest(actor=actor.pk):
                actual = self.error(self.wire("publish_content_pack", self.params, actor=actor), "not_found")
                unknown = self.error(self.wire("publish_content_pack", {
                    **self.params, "preview_id": str(uuid4()),
                }, actor=actor), "not_found")
                self.assertEqual(actual, unknown)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / self.pack).exists())

    def test_cached_actor_cannot_replay_after_authority_or_family_changes(self):
        self.prepare()
        before = self.snapshot()
        for change in ({"is_staff": False}, {"is_active": False}, {"role": "child"},
                       {"family_id": self.foreign.family_id}):
            with self.subTest(change=change):
                User.objects.filter(pk=self.actor.pk).update(**change)
                self.error(self.wire("publish_content_pack", self.params), "permission_denied")
                User.objects.filter(pk=self.actor.pk).update(
                    is_staff=True, is_active=True, role="parent", family_id=self.actor.family_id,
                )
        self.assertEqual(self.snapshot(), before)

    def test_current_author_in_another_family_cannot_replay_old_receipt(self):
        self.prepare()
        before = self.snapshot()
        User.objects.filter(pk=self.actor.pk).update(family=self.foreign.family)
        fresh_actor = User.objects.get(pk=self.actor.pk)
        self.error(self.wire("publish_content_pack", self.params, actor=fresh_actor), "not_found")
        self.assertEqual(self.snapshot(), before)

    def test_confirmation_and_publish_scope_still_apply_on_completed_replay(self):
        self.prepare()
        before = self.snapshot()
        self.error(self.wire("publish_content_pack", self.params, confirmation=False), "confirmation_required")
        self.error(self.wire("publish_content_pack", self.params, scopes=frozenset({"mcp:author"})),
                   "permission_denied")
        self.assertEqual(self.snapshot(), before)

    def test_deleted_unpublished_preview_cannot_publish(self):
        self.prepare(publish=False)
        before = self.snapshot()
        self.error(self.wire("publish_content_pack", self.params), "not_found")
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(ContentPackPublication.objects.get(pk=self.params["preview_id"]).published_at)

    def test_recreated_source_does_not_bypass_unpublished_preview_digest(self):
        self.prepare(publish=False)
        self.ok(self.wire("write_pack_file", {
            "pack": self.pack, "filename": "items.yaml", "yaml_content": "items: []\n",
        }))
        before = self.snapshot()
        result = self.error(self.wire("publish_content_pack", self.params), "invalid_request")
        self.assertIn("source changed", result["error"]["message"])
        self.assertEqual(self.snapshot(), before)

    def test_completed_receipt_is_independent_of_a_reused_foreign_draft_directory(self):
        self.prepare()
        self.ok(self.wire("write_pack_file", {
            "pack": self.pack, "filename": "items.yaml", "yaml_content": "items: []\n",
        }, actor=self.foreign))
        source_before = {path.name: path.read_bytes() for path in (self.root / self.pack).iterdir()}
        before = self.snapshot()
        self.assertEqual(self.ok(self.wire("publish_content_pack", self.params)), self.published)
        self.error(self.wire("publish_content_pack", self.params, actor=self.foreign))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({path.name: path.read_bytes() for path in (self.root / self.pack).iterdir()},
                         source_before)
