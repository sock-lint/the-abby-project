"""Tests for HomeworkAssignmentViewSet, HomeworkSubmissionViewSet, HomeworkDashboardView."""
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.projects.models import User


def _fake_image():
    buf = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    buf.seek(0)
    buf.name = "proof.png"
    return buf


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()


class HomeworkAssignmentCreateTests(_Fixture):
    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_parent_creates_assignment(self, _gl):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/homework/", {
            "title": "Math ch5",
            "subject": "math",
            "due_date": (timezone.localdate() + timedelta(days=3)).isoformat(),
            "assigned_to": self.child.id,
            "effort_level": 3,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("application/json", resp["Content-Type"])
        self.assertEqual(resp.data["title"], "Math ch5")
        self.assertIn("id", resp.data)
        self.assertTrue(HomeworkAssignment.objects.filter(title="Math ch5").exists())
        # Response must NOT include the dead currency fields.
        self.assertNotIn("reward_amount", resp.data)
        self.assertNotIn("coin_reward", resp.data)
        self.assertNotIn("rewards_pending_review", resp.data)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_creates_auto_assigns_self(self, _gl):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/homework/", {
            "title": "My reading",
            "description": "Read chapter 3",
            "subject": "reading",
            "due_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "effort_level": 2,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("application/json", resp["Content-Type"])
        self.assertEqual(resp.data["title"], "My reading")
        hw = HomeworkAssignment.objects.get(title="My reading")
        self.assertEqual(hw.assigned_to, self.child)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_cannot_delete(self, _gl):
        hw = HomeworkAssignment.objects.create(
            title="HW", subject="math",
            due_date=timezone.localdate() + timedelta(days=3),
            assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.delete(f"/api/homework/{hw.pk}/")
        self.assertEqual(resp.status_code, 403)


class HomeworkAssignmentListTests(_Fixture):
    def test_child_sees_own_assignments(self):
        child2 = User.objects.create_user(username="c2", password="pw", role="child")
        HomeworkAssignment.objects.create(
            title="Mine", subject="math",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        HomeworkAssignment.objects.create(
            title="Theirs", subject="math",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_to=child2, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/homework/")
        self.assertEqual(resp.status_code, 200)
        titles = [r["title"] for r in resp.json()["results"]]
        self.assertIn("Mine", titles)
        self.assertNotIn("Theirs", titles)


class HomeworkSubmitTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.hw = HomeworkAssignment.objects.create(
            title="HW1", subject="math",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_submits_with_proof(self, mock_gl):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/homework/{self.hw.pk}/submit/",
            {"images": _fake_image(), "notes": "Done"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            HomeworkSubmission.objects.filter(assignment=self.hw, user=self.child).exists()
        )

    def test_submit_without_images_fails(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/homework/{self.hw.pk}/submit/",
            {"notes": "No proof"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)


class HomeworkSubmissionViewSetTests(_Fixture):
    def test_child_sees_own_submissions(self):
        hw = HomeworkAssignment.objects.create(
            title="HW", subject="math",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        HomeworkSubmission.objects.create(
            assignment=hw, user=self.child, status="pending",
            timeliness="on_time",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/homework-submissions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 1)



class HomeworkDashboardTests(_Fixture):
    def test_child_dashboard_returns_sections(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/homework/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("today", data)
        self.assertIn("upcoming", data)
        self.assertIn("overdue", data)
        self.assertIn("stats", data)

    def test_parent_dashboard_returns_pending(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/homework/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("pending_submissions", resp.json())
