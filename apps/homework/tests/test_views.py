"""Tests for HomeworkAssignmentViewSet, HomeworkSubmissionViewSet, HomeworkDashboardView."""
from datetime import timedelta
from decimal import Decimal
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
    def test_parent_creates_assignment(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/homework/", {
            "title": "Math ch5",
            "subject": "math",
            "due_date": (timezone.localdate() + timedelta(days=3)).isoformat(),
            "assigned_to": self.child.id,
            "effort_level": 3,
            "reward_amount": "5.00",
            "coin_reward": 10,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(HomeworkAssignment.objects.filter(title="Math ch5").exists())

    def test_child_creates_auto_assigns_self(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/homework/", {
            "title": "My reading",
            "description": "Read chapter 3",
            "subject": "reading",
            "due_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "effort_level": 2,
            "assigned_to": self.child.id,
            "reward_amount": "0.00",
            "coin_reward": 0,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        hw = HomeworkAssignment.objects.get(title="My reading")
        self.assertEqual(hw.assigned_to, self.child)

    def test_child_cannot_delete(self):
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
            reward_amount=Decimal("5.00"), coin_reward=10,
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
            reward_amount_snapshot=Decimal("0"), coin_reward_snapshot=0,
            timeliness="on_time", timeliness_multiplier=Decimal("1.0"),
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/homework-submissions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 1)


class HomeworkAdjustEndpointTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.hw = HomeworkAssignment.objects.create(
            title="Child HW", subject="math",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_to=self.child, created_by=self.child,
            reward_amount=Decimal("0"), coin_reward=0,
            rewards_pending_review=True,
        )
        self.sub = HomeworkSubmission.objects.create(
            assignment=self.hw, user=self.child, status="pending",
            reward_amount_snapshot=Decimal("0"), coin_reward_snapshot=0,
            timeliness="on_time", timeliness_multiplier=Decimal("1.0"),
        )

    def test_parent_can_adjust_pending_submission(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/homework-submissions/{self.sub.pk}/adjust/",
            {"effort_level": 3, "reward_amount": "2.00", "coin_reward": 10},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.sub.refresh_from_db()
        self.hw.refresh_from_db()
        # effort=3 → multiplier=1.0, timeliness=on_time → 1.0; $2×1×1 = $2.
        self.assertEqual(self.sub.reward_amount_snapshot, Decimal("2.00"))
        self.assertEqual(self.sub.coin_reward_snapshot, 10)
        self.assertFalse(self.hw.rewards_pending_review)

    def test_child_cannot_adjust(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/homework-submissions/{self.sub.pk}/adjust/",
            {"effort_level": 5, "reward_amount": "100", "coin_reward": 100},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_adjust_rejects_non_pending(self):
        self.sub.status = "approved"
        self.sub.save(update_fields=["status"])
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/homework-submissions/{self.sub.pk}/adjust/",
            {"effort_level": 3, "reward_amount": "1.00", "coin_reward": 5},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_adjust_validates_effort(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/homework-submissions/{self.sub.pk}/adjust/",
            {"effort_level": 9, "reward_amount": "1.00", "coin_reward": 5},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class HomeworkChildCreateEndpointTests(_Fixture):
    def test_child_post_ignores_reward_fields(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/homework/", {
            "title": "Self-assigned",
            "subject": "reading",
            "due_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "effort_level": 5,
            "reward_amount": "50.00",
            "coin_reward": 200,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        hw = HomeworkAssignment.objects.get(title="Self-assigned")
        self.assertTrue(hw.rewards_pending_review)
        self.assertEqual(hw.effort_level, 3)
        self.assertEqual(hw.reward_amount, Decimal("0.00"))
        self.assertEqual(hw.coin_reward, 0)


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
