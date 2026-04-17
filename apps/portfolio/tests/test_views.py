"""Tests for ProjectPhoto CRUD, portfolio aggregation, and ZIP export."""
from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.homework.models import (
    HomeworkAssignment,
    HomeworkProof,
    HomeworkSubmission,
)
from apps.portfolio.models import ProjectPhoto
from apps.projects.models import Project, User


def _image(name="photo.jpg"):
    # Minimal valid JPEG header + padding so Django's ImageField validator accepts it in
    # field-level use. For Portfolio we use the field as-is without Pillow validation in tests.
    return SimpleUploadedFile(name, b"\xff\xd8\xff\xe0" + b"\x00" * 100, content_type="image/jpeg")


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.other = User.objects.create_user(username="o", password="pw", role="child")
        self.project = Project.objects.create(
            title="Birdhouse", created_by=self.parent, assigned_to=self.child,
        )
        self.other_project = Project.objects.create(
            title="Quilt", created_by=self.parent, assigned_to=self.other,
        )
        self.client = APIClient()


class ProjectPhotoModelTests(_Fixture):
    def test_create_photo(self):
        photo = ProjectPhoto.objects.create(
            project=self.project, user=self.child, caption="first saw cut",
        )
        self.assertEqual(photo.project, self.project)
        self.assertFalse(photo.is_timelapse)

    def test_ordering_most_recent_first(self):
        p1 = ProjectPhoto.objects.create(project=self.project, user=self.child, caption="a")
        p2 = ProjectPhoto.objects.create(project=self.project, user=self.child, caption="b")
        photos = list(ProjectPhoto.objects.all())
        self.assertEqual(photos[0], p2)
        self.assertEqual(photos[1], p1)

    def test_str_rendering(self):
        photo = ProjectPhoto.objects.create(
            project=self.project, user=self.child, caption="cap",
        )
        self.assertIn("Birdhouse", str(photo))


class ProjectPhotoViewSetTests(_Fixture):
    def test_child_sees_only_own_project_photos(self):
        ProjectPhoto.objects.create(project=self.project, user=self.child, caption="mine")
        ProjectPhoto.objects.create(project=self.other_project, user=self.other, caption="theirs")
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/photos/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 1)

    def test_parent_sees_all(self):
        ProjectPhoto.objects.create(project=self.project, user=self.child, caption="a")
        ProjectPhoto.objects.create(project=self.other_project, user=self.other, caption="b")
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/photos/")
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 2)

    def test_create_photo_uses_request_user(self):
        # Use video_url path — avoids Pillow JPEG validation of the stub image.
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/photos/", {
            "project": self.project.id, "caption": "via-link",
            "video_url": "https://youtu.be/example",
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        photo = ProjectPhoto.objects.get(caption="via-link")
        self.assertEqual(photo.user, self.child)

    def test_unauthenticated_rejected(self):
        resp = self.client.get("/api/photos/")
        self.assertEqual(resp.status_code, 401)


class PortfolioViewTests(_Fixture):
    def test_returns_grouped_projects_and_homework(self):
        ProjectPhoto.objects.create(project=self.project, user=self.child, caption="pic")

        # Approved homework proof should appear.
        assignment = HomeworkAssignment.objects.create(
            title="Essay", subject="writing", effort_level=3,
            due_date=date.today() + timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        submission = HomeworkSubmission.objects.create(
            assignment=assignment, user=self.child, status="approved",
            reward_amount_snapshot=Decimal("5"), coin_reward_snapshot=5,
            timeliness="on_time", timeliness_multiplier=Decimal("1.0"),
        )
        HomeworkProof.objects.create(submission=submission, caption="proof")

        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/portfolio/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["projects"]), 1)
        self.assertEqual(body["projects"][0]["project_title"], "Birdhouse")
        self.assertEqual(len(body["homework"]), 1)
        self.assertEqual(body["homework"][0]["subject"], "writing")

    def test_rejected_homework_excluded(self):
        assignment = HomeworkAssignment.objects.create(
            title="x", subject="math", effort_level=3,
            due_date=date.today() + timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        submission = HomeworkSubmission.objects.create(
            assignment=assignment, user=self.child, status="rejected",
            reward_amount_snapshot=Decimal("0"), coin_reward_snapshot=0,
            timeliness="on_time", timeliness_multiplier=Decimal("1.0"),
        )
        HomeworkProof.objects.create(submission=submission, caption="rejected proof")

        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/portfolio/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["homework"], [])


class ProjectPhotoDeleteTests(_Fixture):
    def test_owner_can_delete_own_photo(self):
        photo = ProjectPhoto.objects.create(
            project=self.project, user=self.child, image=_image(), caption="mine",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.delete(f"/api/photos/{photo.pk}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ProjectPhoto.objects.filter(pk=photo.pk).exists())

    def test_parent_can_delete_any_photo(self):
        photo = ProjectPhoto.objects.create(
            project=self.project, user=self.child, image=_image(), caption="mine",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/photos/{photo.pk}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ProjectPhoto.objects.filter(pk=photo.pk).exists())

    def test_other_child_cannot_delete(self):
        # RoleFilteredQuerySet scopes to project__assigned_to, so a sibling
        # child gets 404 (the row isn't visible to them), which is the same
        # security outcome as 403 — the photo stays.
        photo = ProjectPhoto.objects.create(
            project=self.project, user=self.child, image=_image(), caption="mine",
        )
        self.client.force_authenticate(self.other)
        resp = self.client.delete(f"/api/photos/{photo.pk}/")
        self.assertIn(resp.status_code, (403, 404))
        self.assertTrue(ProjectPhoto.objects.filter(pk=photo.pk).exists())

    def test_unauthenticated_rejected(self):
        photo = ProjectPhoto.objects.create(
            project=self.project, user=self.child, caption="mine",
        )
        resp = self.client.delete(f"/api/photos/{photo.pk}/")
        self.assertEqual(resp.status_code, 401)


class ExportPortfolioViewTests(_Fixture):
    def test_empty_export_404(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/export/portfolio/")
        self.assertEqual(resp.status_code, 404)

    def test_export_returns_zip(self):
        ProjectPhoto.objects.create(
            project=self.project, user=self.child,
            image=_image(), caption="saw",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/export/portfolio/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")
        self.assertIn("portfolio.zip", resp["Content-Disposition"])
        # ZIP contains the project folder.
        buf = io.BytesIO(b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            self.assertTrue(any("Birdhouse" in n for n in names))
