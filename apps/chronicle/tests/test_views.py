"""Tests for ChronicleViewSet — list and summary endpoints."""
from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.chronicle.models import ChronicleEntry

User = get_user_model()


class ChronicleListTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create(username="mom", role=User.Role.PARENT)
        self.child = User.objects.create(
            username="kid", role=User.Role.CHILD,
            date_of_birth=date(2011, 9, 22), grade_entry_year=2025,
        )
        ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2025, 10, 1),
            chapter_year=2025, title="A manual memory",
        )

    def test_child_sees_own_entries(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/")
        self.assertEqual(resp.status_code, 200)
        # DRF may paginate — `resp.data` may be a dict with "results" or a list.
        results = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertEqual(len(results), 1)

    def test_parent_can_filter_by_user_id(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/chronicle/?user_id={self.child.id}")
        self.assertEqual(resp.status_code, 200)
        results = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertEqual(len(results), 1)

    def test_filter_by_chapter_year(self):
        ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2026, 9, 1),
            chapter_year=2026, title="Later chapter",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/?chapter_year=2026")
        self.assertEqual(resp.status_code, 200)
        results = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Later chapter")


class ChronicleSummaryTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create(
            username="kid", role=User.Role.CHILD,
            date_of_birth=date(2011, 9, 22), grade_entry_year=2025,
        )
        ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2025, 10, 1),
            chapter_year=2025, title="Freshman memory",
        )
        ChronicleEntry.objects.create(
            user=self.child, kind="recap", occurred_on=date(2026, 6, 1),
            chapter_year=2025, title="Freshman recap", metadata={"projects_completed": 3},
        )

    def test_summary_groups_by_chapter(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/summary/")
        self.assertEqual(resp.status_code, 200)
        chapters = resp.data["chapters"]
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["chapter_year"], 2025)
        self.assertEqual(chapters[0]["grade"], 9)
        self.assertEqual(chapters[0]["label"], "Freshman Year")
        # Past chapter reads stats from frozen RECAP.
        self.assertEqual(chapters[0]["stats"]["projects_completed"], 3)


class PendingCelebrationTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create(username="kid", role=User.Role.CHILD, date_of_birth=date(2011, 4, 21))

    def test_returns_204_when_nothing_pending(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 204)

    def test_returns_birthday_entry_today(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date.today(),
            chapter_year=date.today().year if date.today().month >= 8 else date.today().year - 1,
            title="Turned 15", metadata={"gift_coins": 1500},
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], entry.id)
        self.assertEqual(resp.data["metadata"]["gift_coins"], 1500)

    def test_does_not_return_already_viewed_entry(self):
        from django.utils import timezone
        ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date.today(),
            chapter_year=2025, title="Turned 15", viewed_at=timezone.now(),
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 204)

    def test_does_not_leak_across_users(self):
        other_child = User.objects.create(username="sibling", role=User.Role.CHILD)
        ChronicleEntry.objects.create(
            user=other_child, kind="birthday", occurred_on=date.today(),
            chapter_year=2025, title="Turned 10",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chronicle/pending-celebration/")
        self.assertEqual(resp.status_code, 204)


class MarkViewedTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create(username="kid", role=User.Role.CHILD)
        self.entry = ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date.today(),
            chapter_year=2025, title="Turned 15",
        )

    def test_sets_viewed_at(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chronicle/{self.entry.id}/mark-viewed/")
        self.assertEqual(resp.status_code, 200)
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.viewed_at)

    def test_idempotent_does_not_rewrite_viewed_at(self):
        from django.utils import timezone
        fixed = timezone.now()
        self.entry.viewed_at = fixed
        self.entry.save()
        self.client.force_authenticate(self.child)
        self.client.post(f"/api/chronicle/{self.entry.id}/mark-viewed/")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.viewed_at, fixed)

    def test_other_user_cannot_mark_viewed(self):
        stranger = User.objects.create(username="stranger", role=User.Role.CHILD)
        self.client.force_authenticate(stranger)
        resp = self.client.post(f"/api/chronicle/{self.entry.id}/mark-viewed/")
        self.assertIn(resp.status_code, (403, 404))


class ManualEntryTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create(username="mom", role=User.Role.PARENT)
        self.child = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_parent_creates_manual_entry(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/chronicle/manual/", {
            "user_id": self.child.id,
            "title": "Rode a bike for the first time",
            "summary": "Big Wednesday.",
            "occurred_on": "2026-04-21",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(ChronicleEntry.objects.filter(user=self.child, kind="manual").exists())

    def test_child_cannot_create_manual_entry(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/chronicle/manual/", {
            "user_id": self.child.id,
            "title": "Unauthorized",
            "occurred_on": "2026-04-21",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_parent_edits_manual_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2026, 4, 21),
            chapter_year=2025, title="Old title",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/chronicle/{entry.id}/", {"title": "New title"}, format="json")
        self.assertEqual(resp.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "New title")

    def test_parent_cannot_edit_auto_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=date(2026, 4, 21),
            chapter_year=2025, title="Turned 15",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/chronicle/{entry.id}/", {"title": "No"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_parent_deletes_manual_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="manual", occurred_on=date(2026, 4, 21),
            chapter_year=2025, title="Delete me",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/chronicle/{entry.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ChronicleEntry.objects.filter(pk=entry.id).exists())

    def test_parent_cannot_delete_auto_entry(self):
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="recap", occurred_on=date(2026, 6, 1),
            chapter_year=2025, title="Freshman recap",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/chronicle/{entry.id}/")
        self.assertEqual(resp.status_code, 403)
