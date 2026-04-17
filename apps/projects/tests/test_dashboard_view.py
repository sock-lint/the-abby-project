"""Endpoint tests for GET /api/dashboard/.

Currently covers only the `next_actions` field added for the priority feed.
Other dashboard fields are covered implicitly by the pages that consume them."""
import datetime
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore
from apps.homework.models import HomeworkAssignment
from apps.projects.models import User


class DashboardNextActionsTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent")
        self.child = User.objects.create_user(
            username="c", password="pw", role="child")
        self.client = APIClient()

    def test_parent_receives_empty_next_actions(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["next_actions"], [])

    def test_child_receives_scored_next_actions(self):
        HomeworkAssignment.objects.create(
            title="Math workbook", subject="math", effort_level=3,
            due_date=datetime.date.today() + datetime.timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        Chore.objects.create(
            title="Clean Room", recurrence="weekly",
            reward_amount=Decimal("1.00"), coin_reward=2,
            assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("next_actions", data)
        self.assertGreaterEqual(len(data["next_actions"]), 2)
        first = data["next_actions"][0]
        required_keys = {
            "kind", "id", "title", "subtitle", "score",
            "due_at", "reward", "icon", "tone", "action_url",
        }
        self.assertTrue(required_keys <= set(first.keys()))
        # Homework due tomorrow (60) outranks weekly chore on any weekday (≤58)
        self.assertEqual(first["kind"], "homework")

    def test_child_item_shape_for_chore(self):
        Chore.objects.create(
            title="Dishes", icon="🍽", recurrence="daily",
            reward_amount=Decimal("0.50"), coin_reward=1,
            assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        data = self.client.get("/api/dashboard/").json()
        chore_item = next(
            (a for a in data["next_actions"] if a["kind"] == "chore"), None,
        )
        self.assertIsNotNone(chore_item)
        self.assertEqual(chore_item["reward"], {"money": "0.50", "coins": 1})
        self.assertEqual(chore_item["tone"], "moss")
        self.assertEqual(chore_item["action_url"], "/chores")
        self.assertIsNone(chore_item["due_at"])
