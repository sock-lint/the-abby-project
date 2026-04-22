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
