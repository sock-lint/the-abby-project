"""Parent-owned manual memories retain ownership across both workspaces."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chronicle.models import ChronicleEntry
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError
from apps.mcp_server.schemas import (
    DeleteChronicleEntryIn, GetChronicleSummaryIn, ListChronicleEntriesIn,
    MarkChronicleViewedIn, UpdateManualEntryIn,
)
from apps.mcp_server.tools.chronicle import (
    delete_chronicle_entry, get_chronicle_summary, list_chronicle_entries,
    mark_chronicle_viewed, update_manual_entry,
)
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParentManualMemoryPrivacyTests(TestCase):
    def setUp(self):
        family = make_family("Manual memory owners", parents=[
            {"username": "manual-owner", "is_staff": True},
            {"username": "manual-coparent", "is_staff": True},
        ], children=[{"username": "manual-child"}])
        self.owner, self.coparent = family.parents
        self.child = family.children[0]
        self.foreign = make_family("Other manual household", parents=[{"username": "manual-foreign", "is_staff": True}]).parents[0]
        self.client = APIClient()
        self.entry = self.create_memory()

    def authenticate(self, user, *, personal=False):
        self.client.force_authenticate(user)
        self.client.credentials(**({"HTTP_X_ABBY_SPACE": "personal"} if personal else {}))

    def create_memory(self):
        self.authenticate(self.owner, personal=True)
        response = self.client.post("/api/chronicle/manual/", {
            "title": "My personal manual memory", "summary": "The owner's own details",
            "occurred_on": timezone.localdate().isoformat(),
            "metadata": {"personal": "Owner's saved context"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        entry = ChronicleEntry.objects.get(pk=response.data["id"])
        self.assertEqual(entry.user, self.owner)
        return entry

    def test_coparent_family_lists_hide_parent_manual_memory_even_without_private_flag(self):
        self.entry.is_private = False
        self.entry.save(update_fields=["is_private"])
        self.authenticate(self.coparent)
        for query in ({}, {"user_id": self.owner.pk}):
            with self.subTest(query=query):
                response = self.client.get("/api/chronicle/", query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["results"], [])

    def test_coparent_family_detail_and_mark_viewed_cannot_return_personal_memory(self):
        self.authenticate(self.coparent)
        self.assertEqual(self.client.get(f"/api/chronicle/{self.entry.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/chronicle/{self.entry.pk}/mark-viewed/").status_code, 404)
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.viewed_at)

    def test_coparent_family_cannot_edit_parent_manual_memory(self):
        self.authenticate(self.coparent)
        for method in (self.client.patch, self.client.put):
            with self.subTest(method=method.__name__):
                response = method(f"/api/chronicle/{self.entry.pk}/", {
                    "title": "Changed by co-parent", "summary": "Changed details",
                    "occurred_on": timezone.localdate().isoformat(),
                }, format="json")
                self.assertEqual(response.status_code, 404)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.title, "My personal manual memory")
        self.assertEqual(self.entry.summary, "The owner's own details")

    def test_coparent_family_cannot_delete_parent_manual_memory(self):
        self.authenticate(self.coparent)
        self.assertEqual(self.client.delete(f"/api/chronicle/{self.entry.pk}/").status_code, 404)
        self.assertTrue(ChronicleEntry.objects.filter(pk=self.entry.pk).exists())

    def test_other_accounts_in_either_space_cannot_access_parent_manual_memory(self):
        for actor in (self.coparent, self.foreign, self.child):
            for personal in (False, True):
                with self.subTest(actor=actor.pk, personal=personal):
                    self.authenticate(actor, personal=personal)
                    self.assertEqual(self.client.get(f"/api/chronicle/{self.entry.pk}/").status_code, 404)
                    self.assertEqual(self.client.get("/api/chronicle/").data["results"], [])
        self.assertTrue(ChronicleEntry.objects.filter(pk=self.entry.pk).exists())

    def test_owner_can_read_edit_and_remove_manual_memories_in_both_spaces(self):
        for personal in (False, True):
            with self.subTest(personal=personal):
                entry = self.create_memory()
                self.authenticate(self.owner, personal=personal)
                self.assertEqual(self.client.get(f"/api/chronicle/{entry.pk}/").status_code, 200)
                listed = self.client.get("/api/chronicle/").data["results"]
                self.assertIn(entry.pk, [row["id"] for row in listed])
                summary = self.client.get("/api/chronicle/summary/")
                self.assertIn(entry.pk, [row["id"] for chapter in summary.data["chapters"] for row in chapter["entries"]])
                self.assertEqual(self.client.patch(f"/api/chronicle/{entry.pk}/", {"title": "My correction"}, format="json").status_code, 200)
                entry.refresh_from_db()
                self.assertEqual(entry.title, "My correction")
                self.assertEqual(self.client.delete(f"/api/chronicle/{entry.pk}/").status_code, 204)
                self.assertFalse(ChronicleEntry.objects.filter(pk=entry.pk).exists())

    def test_family_parents_retain_child_manual_memory_management(self):
        self.authenticate(self.owner)
        response = self.client.post("/api/chronicle/manual/", {
            "user_id": self.child.pk, "title": "Our child's milestone",
            "occurred_on": timezone.localdate().isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        entry_id = response.data["id"]
        self.authenticate(self.coparent)
        self.assertEqual(self.client.get(f"/api/chronicle/{entry_id}/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/chronicle/{entry_id}/", {"title": "A family correction"}, format="json").status_code, 200)
        self.authenticate(self.child)
        self.assertEqual(self.client.get(f"/api/chronicle/{entry_id}/").status_code, 200)
        self.authenticate(self.coparent)
        self.assertEqual(self.client.delete(f"/api/chronicle/{entry_id}/").status_code, 204)

    def test_parent_journal_sharing_stays_independent_of_manual_memory_policy(self):
        private = ChronicleEntry.objects.create(user=self.owner, kind="journal", is_private=True,
                                                occurred_on=timezone.localdate(), chapter_year=self.entry.chapter_year, title="Private journal")
        shared = ChronicleEntry.objects.create(user=self.owner, kind="journal", is_private=False,
                                               occurred_on=timezone.localdate() - timedelta(days=1), chapter_year=self.entry.chapter_year, title="Shared journal")
        self.authenticate(self.coparent)
        listed = self.client.get("/api/chronicle/").data["results"]
        self.assertEqual([row["id"] for row in listed], [shared.pk])
        self.assertEqual(self.client.get(f"/api/chronicle/{shared.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/chronicle/{private.pk}/").status_code, 404)

    def test_shared_mcp_reads_hide_coparent_manual_memories(self):
        with override_user(self.coparent):
            listing = list_chronicle_entries(ListChronicleEntriesIn(user_id=self.owner.pk))
            summary = get_chronicle_summary(GetChronicleSummaryIn(user_id=self.owner.pk))
        self.assertEqual(listing["entries"], [])
        self.assertEqual(summary["chapters"], [])
        with override_user(self.owner):
            own = list_chronicle_entries(ListChronicleEntriesIn())
        self.assertEqual([row["id"] for row in own["entries"]], [self.entry.pk])

    def test_shared_mcp_entry_actions_cannot_touch_coparent_manual_memories(self):
        for action, payload in (
            (mark_chronicle_viewed, lambda pk: MarkChronicleViewedIn(entry_id=pk)),
            (update_manual_entry, lambda pk: UpdateManualEntryIn(entry_id=pk, title="Wrong editor")),
            (delete_chronicle_entry, lambda pk: DeleteChronicleEntryIn(entry_id=pk)),
        ):
            with self.subTest(action=action.__name__):
                entry = self.create_memory()
                with override_user(self.coparent), self.assertRaises(MCPNotFoundError):
                    action(payload(entry.pk))
                entry.refresh_from_db()
                self.assertEqual(entry.title, "My personal manual memory")
                self.assertIsNone(entry.viewed_at)
