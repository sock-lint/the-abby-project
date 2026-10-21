"""Authoring failures keep safe, actionable transport error categories."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.achievements.models import SkillCategory
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rpg.models import RPGEditorialOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthoringReviewErrorsTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "error-author", "is_staff": True}]).parents[0]

    def call(self, name, values):
        with override_user(self.actor):
            result = async_to_sync(mcp.call_tool)(name, values)
        return result.structuredContent if hasattr(result, "structuredContent") else result[1]

    def test_id_only_saved_pack_row_is_validation_error_and_file_is_unchanged(self):
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=Path(directory)):
            self.call("write_pack_file", {"params": {"pack": "review-errors", "filename": "badges.yaml",
                "yaml_content": "badges: [{id: b1, description: Saved malformed draft}]\n"}, "confirmation": True})
            path = Path(directory) / "content/rpg/packs/review-errors/badges.yaml"
            original = path.read_bytes()
            result = self.call("draft_pack_entries", {"params": {"pack": "review-errors", "filename": "badges.yaml",
                "entries": [{"name": "New badge", "description": "Valid row"}]}, "confirmation": True})
            self.assertEqual(result["error"]["code"], "invalid_request")
            self.assertIn("name", result["error"]["message"])
            self.assertEqual(path.read_bytes(), original)

    def test_missing_editorial_draft_is_not_found(self):
        result = self.call("get_editorial_draft", {"params": {"draft_id": str(uuid4())}})
        self.assertEqual(result["error"]["code"], "not_found")

    def test_other_authors_editorial_draft_is_indistinguishable_from_missing(self):
        own = self.call("create_editorial_draft", {"params": {"section": "lorebook", "name": "Private copy"}})
        self.actor = make_family(parents=[{"username": "other-error-author", "is_staff": True}]).parents[0]
        result = self.call("get_editorial_draft", {"params": {"draft_id": own["id"]}})
        missing = self.call("get_editorial_draft", {"params": {"draft_id": str(uuid4())}})
        self.assertEqual(result, missing)
        self.assertEqual(result["error"]["code"], "not_found")

    def test_revoked_editorial_publication_is_permission_denied_without_writes(self):
        draft = self.call("create_editorial_draft", {"params": {"section": "lorebook", "name": "Copy"}})
        saved = self.call("save_editorial_draft", {"params": {"draft_id": draft["id"], "revision": draft["revision"],
            "changes": [{"slug": "duties", "values": {"title": "Reviewed chores"}}]}, "confirmation": True})
        reviewed = self.call("preview_editorial_draft", {"params": {"draft_id": draft["id"], "revision": saved["revision"]}})
        User.objects.filter(pk=self.actor.pk).update(is_staff=False)
        result = self.call("publish_editorial_draft", {"params": {"draft_id": draft["id"], "revision": saved["revision"],
            "preview_id": reviewed["preview"]["id"], "content_digest": reviewed["preview"]["content_digest"]},
            "confirmation": True})
        self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertFalse(RPGEditorialOverride.objects.exists())

    def test_revoked_direct_catalog_author_is_permission_denied_without_writes(self):
        User.objects.filter(pk=self.actor.pk).update(is_staff=False)
        result = self.call("create_category", {"params": {"name": "Must not be created"}, "confirmation": True})
        self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertFalse(SkillCategory.objects.filter(name="Must not be created").exists())
