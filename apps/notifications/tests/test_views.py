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


class PendingCelebrationTests(_Fixture):
    """``GET /api/notifications/pending-celebration/`` — sister to
    ``/api/chronicle/pending-celebration/``. Powers ``CelebrationModal``
    which fires a one-shot full-screen reveal on next app open for streak
    milestones (3/7/14/30/60/100) and Perfect Day awards."""

    def test_returns_204_when_nothing_pending(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/pending-celebration/")
        self.assertEqual(resp.status_code, 204)

    def test_returns_streak_milestone(self):
        Notification.objects.create(
            user=self.child,
            title="🔥 7-day streak!",
            notification_type=NotificationType.STREAK_MILESTONE,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/pending-celebration/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json()["notification_type"],
            NotificationType.STREAK_MILESTONE,
        )

    def test_returns_perfect_day(self):
        Notification.objects.create(
            user=self.child,
            title="Perfect day!",
            notification_type=NotificationType.PERFECT_DAY,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/pending-celebration/")
        self.assertEqual(resp.status_code, 200)

    def test_excludes_read_notifications(self):
        Notification.objects.create(
            user=self.child,
            title="🔥 7-day streak!",
            notification_type=NotificationType.STREAK_MILESTONE,
            is_read=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/pending-celebration/")
        self.assertEqual(resp.status_code, 204)

    def test_excludes_non_celebration_types(self):
        # A drop notification is unread but not eligible for the modal —
        # only streak/perfect-day are in CELEBRATION_TYPES.
        Notification.objects.create(
            user=self.child,
            title="A drop landed",
            notification_type=NotificationType.DROP_RECEIVED,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/pending-celebration/")
        self.assertEqual(resp.status_code, 204)

    def test_returns_most_recent_when_multiple(self):
        from datetime import timedelta
        from django.utils import timezone
        old = Notification.objects.create(
            user=self.child,
            title="🔥 3-day streak!",
            notification_type=NotificationType.STREAK_MILESTONE,
        )
        Notification.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=1),
        )
        recent = Notification.objects.create(
            user=self.child,
            title="🔥 7-day streak!",
            notification_type=NotificationType.STREAK_MILESTONE,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/pending-celebration/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], recent.pk)

    def test_self_scoped_does_not_leak_other_users(self):
        Notification.objects.create(
            user=self.child2,
            title="🔥 100-day streak!",
            notification_type=NotificationType.STREAK_MILESTONE,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/notifications/pending-celebration/")
        self.assertEqual(resp.status_code, 204)
