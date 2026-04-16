"""Tests for config.viewsets — helpers and mixins."""
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.projects.models import User
from config.viewsets import filter_queryset_by_role, get_child_or_404, resolve_target_user


class FilterQuerysetByRoleTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.child2 = User.objects.create_user(username="c2", password="pw", role="child")

    def test_parent_sees_all(self):
        qs = User.objects.all()
        result = filter_queryset_by_role(self.parent, qs, role_filter_field="id")
        self.assertEqual(result.count(), 3)

    def test_child_sees_own(self):
        from apps.notifications.models import Notification

        Notification.objects.create(
            user=self.child, title="A", notification_type="badge_earned",
        )
        Notification.objects.create(
            user=self.child2, title="B", notification_type="badge_earned",
        )
        qs = Notification.objects.all()
        result = filter_queryset_by_role(self.child, qs)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().user, self.child)


class GetChildOr404Tests(TestCase):
    def test_returns_child(self):
        child = User.objects.create_user(username="c", password="pw", role="child")
        self.assertEqual(get_child_or_404(child.id), child)

    def test_returns_none_for_parent(self):
        parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.assertIsNone(get_child_or_404(parent.id))

    def test_returns_none_for_missing_id(self):
        self.assertIsNone(get_child_or_404(99999))


class ResolveTargetUserTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")

    def _drf_request(self, url, user):
        """Build a DRF Request (has query_params) from a raw Django request."""
        django_request = self.factory.get(url)
        django_request.user = user
        drf_request = Request(django_request)
        drf_request.user = user
        return drf_request

    def test_child_resolves_to_self(self):
        request = self._drf_request("/fake/", self.child)
        user, err = resolve_target_user(request)
        self.assertEqual(user, self.child)
        self.assertIsNone(err)

    def test_parent_with_child_id(self):
        request = self._drf_request(f"/fake/?user_id={self.child.id}", self.parent)
        user, err = resolve_target_user(request)
        self.assertEqual(user, self.child)
        self.assertIsNone(err)

    def test_parent_with_bad_id_returns_error(self):
        request = self._drf_request("/fake/?user_id=99999", self.parent)
        user, err = resolve_target_user(request)
        self.assertIsNone(user)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 404)

    def test_parent_without_child_id_resolves_to_self(self):
        request = self._drf_request("/fake/", self.parent)
        user, err = resolve_target_user(request)
        self.assertEqual(user, self.parent)
        self.assertIsNone(err)
