"""Tests for ActivityEventViewSet — parent-only access, filters, pagination."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.activity.models import ActivityEvent
from apps.activity.services import ActivityLogService
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.child2 = User.objects.create_user(
            username="c2", password="pw", role="child",
        )
        self.client = APIClient()


class AccessTests(_Fixture):
    def test_child_cannot_access_activity_log(self):
        ActivityLogService.record(
            category="system", event_type="test.event",
            summary="x", subject=self.child,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/activity/")
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_denied(self):
        resp = self.client.get("/api/activity/")
        self.assertEqual(resp.status_code, 401)

    def test_parent_sees_all_children_events(self):
        ActivityLogService.record(
            category="system", event_type="test.a",
            summary="alpha", subject=self.child,
        )
        ActivityLogService.record(
            category="system", event_type="test.b",
            summary="beta", subject=self.child2,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/activity/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["results"]), 2)


class FilterTests(_Fixture):
    def test_subject_filter(self):
        ActivityLogService.record(
            category="system", event_type="a", summary="a",
            subject=self.child,
        )
        ActivityLogService.record(
            category="system", event_type="a", summary="b",
            subject=self.child2,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/activity/?subject={self.child.pk}")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subject"]["id"], self.child.pk)

    def test_category_filter(self):
        ActivityLogService.record(
            category="rpg", event_type="rpg.x", summary="x",
            subject=self.child,
        )
        ActivityLogService.record(
            category="approval", event_type="approval.y", summary="y",
            subject=self.child,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/activity/?category=rpg")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "rpg")

    def test_event_type_filter(self):
        ActivityLogService.record(
            category="award", event_type="award.coins", summary="x",
            subject=self.child,
        )
        ActivityLogService.record(
            category="award", event_type="award.badge", summary="y",
            subject=self.child,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/activity/?event_type=award.badge")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["event_type"], "award.badge")


class SerializerShapeTests(_Fixture):
    def test_response_includes_breakdown_and_actor_subject(self):
        ActivityLogService.record(
            category="award", event_type="award.coins",
            summary="+5 coins",
            actor=self.parent, subject=self.child, coins_delta=5,
            breakdown=[{"label": "base", "value": 5, "op": "="}],
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/activity/")
        row = resp.json()["results"][0]
        self.assertEqual(row["coins_delta"], 5)
        self.assertEqual(row["actor"]["id"], self.parent.pk)
        self.assertEqual(row["subject"]["id"], self.child.pk)
        self.assertEqual(row["context"]["breakdown"][0]["label"], "base")
