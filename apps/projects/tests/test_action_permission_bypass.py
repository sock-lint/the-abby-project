"""A child must not be able to drive a project's parent-only transitions.

Regression for a real privilege escalation: ``ProjectViewSet.get_permissions``
returned ``[IsAuthenticated]`` for every action except ``create``/``destroy``,
which silently discarded the ``permission_classes=[IsParent]`` declared on the
``activate``, ``approve`` and ``request_changes`` ``@action`` decorators.

``POST /api/projects/<id>/approve/`` returned **200** for the child the project
was assigned to. That flips the project to ``completed``, and
``apps/projects/signals.py`` posts ``project_bonus`` (or ``bounty_payout``) to
``PaymentLedger`` on that transition — so the child was paying themselves.

These assert the endpoints, not the mechanism; ``config/tests/
test_action_permissions.py`` is the structural gate that stops a new instance
from landing.
"""
from __future__ import annotations

from rest_framework.test import APITestCase

from config.tests.factories import make_family

from apps.payments.models import PaymentLedger
from apps.projects.models import Project


class ChildCannotDriveProjectTransitionsTests(APITestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.project = Project.objects.create(
            title="Birdhouse",
            assigned_to=self.child,
            created_by=self.parent,
            status="in_review",
        )

    def test_a_child_cannot_approve_her_own_project(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/approve/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)

        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "in_review")
        # The money half of the bug: no ledger row may exist.
        self.assertFalse(
            PaymentLedger.objects.filter(user=self.child).exists(),
            "a rejected approval must not have paid the child",
        )

    def test_a_child_cannot_activate_her_own_project(self):
        self.project.status = "draft"
        self.project.save(update_fields=["status"])
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/activate/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "draft")

    def test_a_child_cannot_request_changes_on_her_own_project(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/request-changes/",
            {"notes": "nope"}, format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_a_parent_can_still_approve(self):
        # The fix must not have broken the legitimate path.
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/approve/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "completed")

    def test_a_parent_can_still_activate(self):
        self.project.status = "draft"
        self.project.save(update_fields=["status"])
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/activate/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_a_parent_can_still_request_changes(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/request-changes/",
            {"notes": "add a photo"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
