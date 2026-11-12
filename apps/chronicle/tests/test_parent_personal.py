from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from uuid import uuid4

from apps.chronicle.models import ChronicleEntry
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParentPersonalChronicleTests(TestCase):
    def setUp(self):
        family = make_family("Personal memories", parents=[{"username": "journal-parent"}, {"username": "journal-coparent"}], children=[{"username": "journal-child"}])
        self.parent, self.coparent = family.parents
        self.child = family.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.client.credentials(HTTP_X_ABBY_SPACE="personal")

    def entry(self, user, **kwargs):
        return ChronicleEntry.objects.create(user=user, kind="journal", occurred_on=timezone.localdate(), chapter_year=2026,
                                            title="Memory", **kwargs)

    def test_personal_history_contains_own_private_writing_only(self):
        own = self.entry(self.parent, is_private=True)
        self.entry(self.child, is_private=False)
        self.entry(self.coparent, is_private=False)
        response = self.client.get("/api/chronicle/")
        self.assertEqual([row["id"] for row in response.data["results"]], [own.pk])
        self.assertEqual(self.client.get("/api/chronicle/journal/today/").data["id"], own.pk)

    def test_personal_summary_cannot_select_child_shared_memories(self):
        entry = self.entry(self.child, is_private=False)
        result = self.client.get("/api/chronicle/summary/", {"user_id": self.child.pk})
        self.assertIn(result.status_code, (400, 404))
        self.assertEqual(self.client.get(f"/api/chronicle/entries/{entry.pk}/comments/").status_code, 404)

    def test_parent_writes_own_private_journal_and_coparent_sees_only_explicit_sharing(self):
        result = self.client.post("/api/chronicle/journal/", {"title": "My journal", "summary": "My own private memory", "client_entry_id": str(uuid4()), "user_id": self.child.pk}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        entry = ChronicleEntry.objects.get(pk=result.data["id"])
        self.assertEqual(entry.user, self.parent)
        self.assertTrue(entry.is_private)
        self.client.force_authenticate(self.coparent)
        self.client.credentials()
        self.assertEqual(self.client.get(f"/api/chronicle/{entry.pk}/").status_code, 404)
        entry.is_private = False
        entry.save(update_fields=["is_private"])
        self.assertEqual(self.client.get(f"/api/chronicle/{entry.pk}/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/chronicle/{entry.pk}/journal/", {"is_private": True}, format="json").status_code, 404)

    def test_personal_manual_memory_cannot_target_a_child(self):
        result = self.client.post("/api/chronicle/manual/", {"user_id": self.child.pk, "title": "Manual memory", "occurred_on": timezone.localdate().isoformat()}, format="json")
        self.assertIn(result.status_code, (400, 404))
        self.assertFalse(ChronicleEntry.objects.exists())

    def test_parent_can_add_own_manual_memory_without_selecting_a_child(self):
        result = self.client.post("/api/chronicle/manual/", {"title": "My milestone", "occurred_on": timezone.localdate().isoformat()}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(ChronicleEntry.objects.get(pk=result.data["id"]).user, self.parent)
