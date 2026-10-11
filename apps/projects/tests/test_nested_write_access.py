"""Nested writes must authorize the URL project and preserve its relationships."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import (
    MaterialItem, Project, ProjectCollaborator, ProjectMilestone, ProjectResource, ProjectStep,
)
from config.tests.factories import make_family


class NestedProjectWriteAccessTests(TestCase):
    def setUp(self):
        self.alpha = make_family(
            "Alpha", parents=[{"username": "alpha-parent"}],
            children=[{"username": "alpha-child"}, {"username": "alpha-sibling"}],
        )
        self.bravo = make_family(
            "Bravo", parents=[{"username": "bravo-parent"}], children=[{"username": "bravo-child"}],
        )
        self.own = Project.objects.create(
            title="Own", created_by=self.alpha.parents[0], assigned_to=self.alpha.children[0],
        )
        self.foreign = Project.objects.create(
            title="Private", created_by=self.bravo.parents[0], assigned_to=self.bravo.children[0],
        )
        self.client = APIClient()

    def test_foreign_reorder_neither_discloses_nor_changes_steps(self):
        step = ProjectStep.objects.create(project=self.foreign, title="Private instructions", order=3)
        for user in (self.alpha.parents[0], self.alpha.children[0]):
            for items in ([], [{"id": step.pk, "order": 0}]):
                with self.subTest(user=user.role, items=items):
                    self.client.force_authenticate(user)
                    response = self.client.post(
                        f"/api/projects/{self.foreign.pk}/steps/reorder/", {"items": items}, format="json",
                    )
                    self.assertEqual(response.status_code, 404, response.content)
                    self.assertNotIn("Private instructions", response.content.decode())
                    step.refresh_from_db()
                    self.assertEqual(step.order, 3)

    def test_assignee_and_collaborator_can_reorder_but_other_child_cannot(self):
        step = ProjectStep.objects.create(project=self.own, title="Build", order=0)
        self.client.force_authenticate(self.alpha.children[1])
        url = f"/api/projects/{self.own.pk}/steps/reorder/"
        response = self.client.post(url, {"items": []}, format="json")
        self.assertEqual(response.status_code, 404)
        ProjectCollaborator.objects.create(project=self.own, user=self.alpha.children[1])
        for idx, user in enumerate(self.alpha.children):
            self.client.force_authenticate(user)
            response = self.client.post(url, {"items": [{"id": step.pk, "order": idx + 1}]}, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            step.refresh_from_db()
            self.assertEqual(step.order, idx + 1)

    def test_foreign_parent_project_rejected_for_every_nested_create(self):
        self.client.force_authenticate(self.alpha.parents[0])
        cases = [
            ("steps", ProjectStep, {"title": "Intrusion"}),
            ("milestones", ProjectMilestone, {"title": "Intrusion"}),
            ("materials", MaterialItem, {"name": "Intrusion"}),
            ("resources", ProjectResource, {"url": "https://example.com/intrusion"}),
            ("collaborators", ProjectCollaborator, {"user_id": self.alpha.children[0].pk}),
        ]
        for route, model, payload in cases:
            with self.subTest(route=route):
                response = self.client.post(
                    f"/api/projects/{self.foreign.pk}/{route}/", payload, format="json",
                )
                self.assertEqual(response.status_code, 404, response.content)
                self.assertFalse(model.objects.filter(project=self.foreign).exists())

    def test_create_uses_authorized_url_project_without_body_project(self):
        self.client.force_authenticate(self.alpha.parents[0])
        response = self.client.post(
            f"/api/projects/{self.own.pk}/steps/", {"title": "Build"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(ProjectStep.objects.get().project_id, self.own.pk)

    def test_nested_rows_cannot_be_reassigned_to_foreign_project(self):
        self.client.force_authenticate(self.alpha.parents[0])
        cases = [
            ("steps", ProjectStep.objects.create(project=self.own, title="Build")),
            ("milestones", ProjectMilestone.objects.create(project=self.own, title="Phase")),
            ("materials", MaterialItem.objects.create(project=self.own, name="Wood")),
            ("resources", ProjectResource.objects.create(project=self.own, url="https://example.com/")),
        ]
        for route, instance in cases:
            with self.subTest(route=route):
                response = self.client.patch(
                    f"/api/projects/{self.own.pk}/{route}/{instance.pk}/",
                    {"project": self.foreign.pk}, format="json",
                )
                self.assertEqual(response.status_code, 400, response.content)
                instance.refresh_from_db()
                self.assertEqual(instance.project_id, self.own.pk)

    def test_step_milestone_and_resource_step_must_belong_to_url_project(self):
        self.client.force_authenticate(self.alpha.parents[0])
        milestone = ProjectMilestone.objects.create(project=self.foreign, title="Private phase")
        step = ProjectStep.objects.create(project=self.foreign, title="Private step")
        cases = [
            ("steps", {"title": "Build", "milestone": milestone.pk}),
            ("resources", {"url": "https://example.com/", "step": step.pk}),
        ]
        for route, payload in cases:
            with self.subTest(route=route):
                response = self.client.post(f"/api/projects/{self.own.pk}/{route}/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(ProjectStep.objects.filter(project=self.own).exists())
        self.assertFalse(ProjectResource.objects.filter(project=self.own).exists())

    def test_related_rows_can_be_assigned_within_the_same_project(self):
        self.client.force_authenticate(self.alpha.parents[0])
        milestone = ProjectMilestone.objects.create(project=self.own, title="Phase")
        response = self.client.post(
            f"/api/projects/{self.own.pk}/steps/", {"title": "Build", "milestone": milestone.pk}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        response = self.client.post(
            f"/api/projects/{self.own.pk}/resources/",
            {"url": "https://example.com/", "step": response.json()["id"]}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
