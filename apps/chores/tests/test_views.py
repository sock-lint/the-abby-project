"""Tests for ChoreViewSet and ChoreCompletionViewSet."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreService
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()


class ChoreViewSetTests(_Fixture):
    def test_parent_creates_chore(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/chores/", {
            "title": "Dishes", "reward_amount": "1.50", "coin_reward": 5,
            "recurrence": "daily",
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))

    def test_child_cannot_create_chore(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/chores/", {
            "title": "x", "reward_amount": "0.00",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_complete_action_child_submits(self):
        chore = Chore.objects.create(title="Trash", reward_amount=Decimal("1"), created_by=self.parent)
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chores/{chore.id}/complete/", {"notes": "done"}, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(ChoreCompletion.objects.filter(chore=chore, user=self.child).exists())


class ChoreCompletionViewSetTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.chore = Chore.objects.create(
            title="Trash", reward_amount=Decimal("1.00"), coin_reward=2,
            created_by=self.parent,
        )
        self.completion = ChoreService.submit_completion(self.child, self.chore)

    def test_child_sees_own_completions(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chore-completions/")
        self.assertEqual(resp.status_code, 200)

    def test_parent_approves(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/chore-completions/{self.completion.id}/approve/")
        self.assertIn(resp.status_code, (200, 204))
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, "approved")

    def test_parent_rejects(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/chore-completions/{self.completion.id}/reject/")
        self.assertIn(resp.status_code, (200, 204))
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, "rejected")

    def test_child_cannot_approve(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chore-completions/{self.completion.id}/approve/")
        self.assertEqual(resp.status_code, 403)
