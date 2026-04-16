"""Tests for notifications.services — notify, notify_parents, get_display_name."""
from django.test import TestCase

from apps.notifications.models import Notification, NotificationType
from apps.notifications.services import get_display_name, notify, notify_parents
from apps.projects.models import User


class GetDisplayNameTests(TestCase):
    def test_returns_display_name_when_set(self):
        user = User.objects.create_user(username="kid", password="pw", display_name="Abby")
        self.assertEqual(get_display_name(user), "Abby")

    def test_returns_username_when_no_display_name(self):
        user = User.objects.create_user(username="kid", password="pw")
        self.assertEqual(get_display_name(user), "kid")


class NotifyTests(TestCase):
    def test_creates_notification(self):
        user = User.objects.create_user(username="c", password="pw", role="child")
        n = notify(user, "Test Title", "Test message", NotificationType.BADGE_EARNED, link="/test")
        self.assertIsInstance(n, Notification)
        self.assertEqual(n.user, user)
        self.assertEqual(n.title, "Test Title")
        self.assertEqual(n.message, "Test message")
        self.assertEqual(n.notification_type, NotificationType.BADGE_EARNED)
        self.assertEqual(n.link, "/test")
        self.assertFalse(n.is_read)

    def test_defaults(self):
        user = User.objects.create_user(username="c", password="pw", role="child")
        n = notify(user, "Title")
        self.assertEqual(n.message, "")
        self.assertEqual(n.notification_type, "timecard_ready")
        self.assertEqual(n.link, "")


class NotifyParentsTests(TestCase):
    def test_notifies_all_parents(self):
        User.objects.create_user(username="p1", password="pw", role="parent")
        User.objects.create_user(username="p2", password="pw", role="parent")
        User.objects.create_user(username="c", password="pw", role="child")

        notify_parents("Alert", "msg", NotificationType.CHORE_SUBMITTED)
        # Only parents get notified (2 parents, 0 children).
        self.assertEqual(Notification.objects.count(), 2)
        self.assertFalse(
            Notification.objects.filter(user__role="child").exists()
        )

    def test_no_parents_creates_no_notifications(self):
        User.objects.create_user(username="c", password="pw", role="child")
        notify_parents("Alert", "msg", NotificationType.CHORE_SUBMITTED)
        self.assertEqual(Notification.objects.count(), 0)
