"""Tests for ProjectViewSet, MilestoneViewSet, TemplateViewSet."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectMilestone, ProjectTemplate, User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()


class ProjectCRUDTests(_Fixture):
    def test_parent_creates_project(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/projects/", {
            "title": "Birdhouse",
            "difficulty": 2,
            "assigned_to_id": self.child.id,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(Project.objects.filter(title="Birdhouse").exists())

    def test_child_sees_own_projects(self):
        child2 = User.objects.create_user(username="c2", password="pw", role="child")
        Project.objects.create(
            title="Mine", assigned_to=self.child, created_by=self.parent,
        )
        Project.objects.create(
            title="Theirs", assigned_to=child2, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/projects/")
        self.assertEqual(resp.status_code, 200)
        titles = [p["title"] for p in resp.json()["results"]]
        self.assertIn("Mine", titles)
        self.assertNotIn("Theirs", titles)

    def test_parent_sees_all_projects(self):
        Project.objects.create(title="A", assigned_to=self.child, created_by=self.parent)
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/projects/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["results"]), 1)

    def test_project_detail(self):
        project = Project.objects.create(
            title="Detail", assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get(f"/api/projects/{project.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Detail")


class ProjectStatusTransitionTests(_Fixture):
    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_approve_completes_project(self, mock_gl):
        project = Project.objects.create(
            title="P", assigned_to=self.child, created_by=self.parent,
            status="in_review", bonus_amount=Decimal("10.00"),
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/projects/{project.pk}/approve/")
        self.assertEqual(resp.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, "completed")

    def test_child_can_submit_for_review(self):
        project = Project.objects.create(
            title="P", assigned_to=self.child, created_by=self.parent,
            status="in_progress",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/projects/{project.pk}/submit/")
        self.assertEqual(resp.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, "in_review")

    def test_activate_project(self):
        project = Project.objects.create(
            title="P", assigned_to=self.child, created_by=self.parent,
            status="draft",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/projects/{project.pk}/activate/")
        self.assertEqual(resp.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, "in_progress")


class MilestoneTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="P", assigned_to=self.child, created_by=self.parent,
            status="in_progress",
        )

    def test_create_milestone(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/projects/{self.project.pk}/milestones/",
            {"title": "Ch1", "bonus_amount": "5.00", "project": self.project.pk},
            format="json",
        )
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(
            ProjectMilestone.objects.filter(project=self.project, title="Ch1").exists()
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_complete_milestone(self, mock_gl):
        ms = ProjectMilestone.objects.create(
            project=self.project, title="Ch1",
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.pk}/milestones/{ms.pk}/complete/"
        )
        self.assertEqual(resp.status_code, 200)
        ms.refresh_from_db()
        self.assertTrue(ms.is_completed)


class TemplateTests(_Fixture):
    def test_create_template_from_project(self):
        project = Project.objects.create(
            title="Finished", assigned_to=self.child, created_by=self.parent,
            status="completed", difficulty=3,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/templates/from-project/", {
            "project_id": project.pk,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(
            ProjectTemplate.objects.filter(title="Finished").exists()
        )

    def test_child_cannot_create_template(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/templates/", {
            "title": "Hack", "difficulty": 1,
        }, format="json")
        self.assertEqual(resp.status_code, 403)
