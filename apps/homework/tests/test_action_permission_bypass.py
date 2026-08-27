"""A child must not be able to save one of her assignments as a template.

Regression for the same privilege escalation fixed in
``apps/projects/tests/test_action_permission_bypass.py``:
``HomeworkAssignmentViewSet.get_permissions`` returned ``[IsAuthenticated]``
for every action except ``update``/``partial_update``/``destroy``, silently
discarding the ``permission_classes=[IsParent]`` on the ``save_template``
``@action``. Templates are parent-authored content reused across a family, so
a child minting them is an authoring-surface leak rather than a money one —
but it is the same defect.

``config/tests/test_action_permissions.py`` is the structural gate.
"""
from __future__ import annotations

import datetime

from django.utils import timezone
from rest_framework.test import APITestCase

from config.tests.factories import make_family

from apps.homework.models import HomeworkAssignment, HomeworkTemplate


class ChildCannotSaveHomeworkTemplateTests(APITestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.assignment = HomeworkAssignment.objects.create(
            title="Fractions worksheet",
            subject=HomeworkAssignment.Subject.MATH,
            due_date=timezone.localdate() + datetime.timedelta(days=2),
            assigned_to=self.child,
            created_by=self.parent,
        )

    def test_a_child_cannot_save_her_assignment_as_a_template(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/homework/{self.assignment.id}/save_template/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(HomeworkTemplate.objects.exists())

    def test_a_parent_can_still_save_a_template(self):
        # The fix must not have broken the legitimate path.
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/homework/{self.assignment.id}/save_template/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(HomeworkTemplate.objects.exists())
