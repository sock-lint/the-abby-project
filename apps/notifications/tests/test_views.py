"""Tests for NotificationViewSet — list, unread_count, mark_all_read, mark_read."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.notifications.models import Notification, NotificationType
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.child2 = User.objects.create_user(username="c2", password="pw", role="child")
        self.client = APIClient()


class NotificationListTests(_Fixture):
    def test_user_sees_only_own_notifications(self):
        Notification.objects.create(
            user=self.child, title="A", notification_type=NotificationType.BADGE_EARNED,
        )
        Notification.objects.create(
            user=self.child2, title="B", notification_type=NotificationType.BADGE_EARNED,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "A")

    def test_unauthenticated_denied(self):
        resp = self.client.get("/api/notifications/")
        self.assertEqual(resp.status_code, 401)


class UnreadCountTests(_Fixture):
    def test_returns_unread_count(self):
        Notification.objects.create(
            user=self.child, title="A", notification_type=NotificationType.BADGE_EARNED,
        )
        Notification.objects.create(
            user=self.child, title="B", notification_type=NotificationType.BADGE_EARNED,
            is_read=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/unread_count/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)


class MarkAllReadTests(_Fixture):
    def test_marks_all_unread_as_read(self):
        Notification.objects.create(
            user=self.child, title="A", notification_type=NotificationType.BADGE_EARNED,
        )
        Notification.objects.create(
            user=self.child, title="B", notification_type=NotificationType.BADGE_EARNED,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/notifications/mark_all_read/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(user=self.child, is_read=False).count(), 0
        )

    def test_does_not_affect_other_users(self):
        Notification.objects.create(
            user=self.child2, title="X", notification_type=NotificationType.BADGE_EARNED,
        )
        self.client.force_authenticate(self.child)
        self.client.post("/api/notifications/mark_all_read/")
        self.assertTrue(
            Notification.objects.filter(user=self.child2, is_read=False).exists()
        )


class MarkReadTests(_Fixture):
    def test_marks_single_notification_read(self):
        n = Notification.objects.create(
            user=self.child, title="A", notification_type=NotificationType.BADGE_EARNED,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/notifications/{n.pk}/mark_read/")
        self.assertEqual(resp.status_code, 200)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertEqual(resp.json()["title"], "A")

    def test_cannot_mark_other_users_notification(self):
        n = Notification.objects.create(
            user=self.child2, title="X", notification_type=NotificationType.BADGE_EARNED,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/notifications/{n.pk}/mark_read/")
        self.assertEqual(resp.status_code, 404)
