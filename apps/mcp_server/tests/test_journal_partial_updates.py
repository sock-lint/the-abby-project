"""MCP journal patches preserve omitted fields and native explicit-blank behavior."""
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import SkillProgress
from apps.chronicle.models import ChronicleEntry
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class JournalPartialUpdateTests(TestCase):
    def setUp(self):
        self.parent = make_family(parents=[{"username": "patch-parent", "is_staff": True}]).parents[0]
        self.entry = ChronicleEntry.objects.create(
            user=self.parent, kind="journal", is_private=True, occurred_on=timezone.localdate(),
            chapter_year=timezone.localdate().year, title="Deliberate title", summary="Saved journal prose",
        )

    def wire(self, fields):
        with override_user(self.parent, scopes=frozenset({"mcp:write"})):
            result = async_to_sync(mcp.call_tool)("update_journal", {
                "params": {"entry_id": self.entry.pk, **fields}, "confirmation": True,
            })
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def assert_patch(self, fields, title, summary):
        result = self.wire(fields)
        self.assertNotIn("error", result, result)
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.title, self.entry.summary), (title, summary))
        self.assertEqual((result["title"], result["summary"]), (title, summary))
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())

    def test_title_only_preserves_saved_summary(self):
        self.assert_patch({"title": "New title"}, "New title", "Saved journal prose")

    def test_summary_only_preserves_deliberate_title(self):
        self.assert_patch({"summary": "New prose"}, "Deliberate title", "New prose")

    def test_empty_patch_preserves_both_fields(self):
        self.assert_patch({}, "Deliberate title", "Saved journal prose")

    def test_explicit_blank_summary_clears_only_summary(self):
        self.assert_patch({"summary": ""}, "Deliberate title", "")

    def test_explicit_blank_title_uses_existing_summary_for_native_autofill(self):
        self.assert_patch({"title": ""}, "Saved journal prose", "Saved journal prose")

    def test_both_blank_is_rejected_without_erasing_saved_text(self):
        result = self.wire({"title": "", "summary": ""})
        self.assertEqual(result["error"]["code"], "invalid_request")
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.title, self.entry.summary), ("Deliberate title", "Saved journal prose"))

    def test_yesterday_remains_immutable(self):
        self.entry.occurred_on -= timedelta(days=1)
        self.entry.save(update_fields=["occurred_on"])
        self.assertEqual(self.wire({"title": "New title"})["error"]["code"], "permission_denied")
