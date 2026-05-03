"""Audit H5/H6 — nested project ViewSets + ClockView + ProjectQRCodeView
must not leak across families.

Pre-fix, ``ProjectStep`` / ``ProjectMilestone`` / ``MaterialItem`` /
``ProjectResource`` / ``ProjectCollaborator`` ViewSets only filtered on the
URL's ``project_pk`` — any auth'd user could enumerate IDs across families
and read foreign-family step data via ``GET /api/projects/<foreign>/steps/``.
``ClockView`` accepted any project_id (a child could clock in against a
foreign-family project), and ``ProjectQRCodeView`` leaked project titles
in the QR payload to anyone with an ID.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import (
    MaterialItem, Project, ProjectCollaborator, ProjectMilestone,
    ProjectResource, ProjectStep,
)
from config.tests.factories import make_family


class _TwoFamilyFixture(TestCase):
    def setUp(self):
        self.fam_a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.fam_b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        # Project owned by family B; everything below is scoped under it.
        self.project_b = Project.objects.create(
            title="Bravo's Birdhouse",
            created_by=self.fam_b.parents[0],
            assigned_to=self.fam_b.children[0],
            status="in_progress",
        )
        self.client = APIClient()


class NestedStepFamilyScopingTests(_TwoFamilyFixture):
    """Audit H5: ProjectStepViewSet must not surface foreign-family steps."""

    def test_alpha_kid_cannot_list_bravo_project_steps(self):
        ProjectStep.objects.create(project=self.project_b, title="Sand", order=0)
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/steps/")
        # Empty result — the queryset filter hides foreign rows entirely.
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        self.assertEqual(rows, [])

    def test_alpha_parent_cannot_list_bravo_project_steps(self):
        ProjectStep.objects.create(project=self.project_b, title="Sand", order=0)
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/steps/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        self.assertEqual(rows, [])

    def test_alpha_kid_cannot_complete_bravo_step(self):
        step = ProjectStep.objects.create(project=self.project_b, title="Sand", order=0)
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.post(
            f"/api/projects/{self.project_b.id}/steps/{step.id}/complete/",
        )
        self.assertEqual(resp.status_code, 404)
        step.refresh_from_db()
        self.assertFalse(step.is_completed)

    def test_bravo_kid_can_still_see_own_project_steps(self):
        step = ProjectStep.objects.create(project=self.project_b, title="Sand", order=0)
        self.client.force_authenticate(self.fam_b.children[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/steps/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], step.id)


class NestedMilestoneFamilyScopingTests(_TwoFamilyFixture):
    def test_alpha_parent_cannot_see_bravo_milestones(self):
        ProjectMilestone.objects.create(
            project=self.project_b, title="Phase 1", order=0,
        )
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/milestones/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        self.assertEqual(rows, [])


class NestedMaterialFamilyScopingTests(_TwoFamilyFixture):
    def test_alpha_parent_cannot_see_bravo_materials(self):
        MaterialItem.objects.create(
            project=self.project_b, name="Lumber",
            estimated_cost=Decimal("12.50"),
        )
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/materials/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        self.assertEqual(rows, [])


class NestedResourceFamilyScopingTests(_TwoFamilyFixture):
    def test_alpha_parent_cannot_see_bravo_resources(self):
        # ProjectResourceViewSet is parent-only via permission_classes — but
        # the audit point is that "parent" wasn't enough; family-scoping
        # has to also gate. An alpha parent (parent role, but wrong family)
        # should still see nothing.
        ProjectResource.objects.create(
            project=self.project_b, title="Tutorial", url="https://example.com/",
            resource_type="link",
        )
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/resources/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        self.assertEqual(rows, [])


class NestedCollaboratorFamilyScopingTests(_TwoFamilyFixture):
    def test_alpha_parent_cannot_see_bravo_collaborators(self):
        ProjectCollaborator.objects.create(
            project=self.project_b, user=self.fam_b.children[0],
            pay_split_percent=Decimal("50.00"),
        )
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/collaborators/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body if isinstance(body, list) else body.get("results", [])
        self.assertEqual(rows, [])


class ClockViewFamilyScopingTests(_TwoFamilyFixture):
    """Audit H6: ClockView must not let a child clock in to a foreign project."""

    def test_alpha_kid_cannot_clock_in_to_bravo_project(self):
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.post(
            "/api/clock/",
            {"action": "in", "project_id": self.project_b.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Project not found", resp.json()["error"])

    def test_alpha_parent_cannot_clock_in_to_bravo_project(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.post(
            "/api/clock/",
            {"action": "in", "project_id": self.project_b.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_bravo_kid_can_still_clock_in_to_own_project(self):
        self.client.force_authenticate(self.fam_b.children[0])
        resp = self.client.post(
            "/api/clock/",
            {"action": "in", "project_id": self.project_b.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)


class QRCodeFamilyScopingTests(_TwoFamilyFixture):
    """Audit H6: ProjectQRCodeView leaked the project title (in the QR
    payload) to anyone who could guess the id.
    """

    def test_alpha_kid_cannot_fetch_bravo_project_qr(self):
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/qr/")
        self.assertEqual(resp.status_code, 404)

    def test_alpha_parent_cannot_fetch_bravo_project_qr(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/qr/")
        self.assertEqual(resp.status_code, 404)

    def test_bravo_kid_can_fetch_own_project_qr(self):
        self.client.force_authenticate(self.fam_b.children[0])
        resp = self.client.get(f"/api/projects/{self.project_b.id}/qr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")
