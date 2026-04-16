"""Tests for config.permissions — IsParent."""
from django.test import RequestFactory, TestCase

from apps.projects.models import User
from config.permissions import IsParent


class IsParentTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.permission = IsParent()

    def _request(self, user=None):
        request = self.factory.get("/fake/")
        request.user = user
        return request

    def test_parent_allowed(self):
        parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.assertTrue(self.permission.has_permission(self._request(parent), None))

    def test_child_denied(self):
        child = User.objects.create_user(username="c", password="pw", role="child")
        self.assertFalse(self.permission.has_permission(self._request(child), None))

    def test_unauthenticated_denied(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self.permission.has_permission(self._request(AnonymousUser()), None))

    def test_message(self):
        self.assertEqual(self.permission.message, "Parents only.")
