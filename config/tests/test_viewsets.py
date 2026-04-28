"""Tests for config.viewsets — helpers and mixins."""
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.notifications.models import Notification
from apps.projects.models import User
from config.tests.factories import make_family
from config.viewsets import filter_queryset_by_role, get_child_or_404, resolve_target_user


class FilterQuerysetByRoleTests(TestCase):
    """The filter scopes by role: parents see family, children see own."""

    def setUp(self):
        self.fam = make_family(
            "A",
            parents=[{"username": "p"}],
            children=[{"username": "c"}, {"username": "c2"}],
        )
        self.other = make_family(
            "B",
            parents=[{"username": "op"}],
            children=[{"username": "oc"}],
        )

    def test_parent_sees_only_own_family_notifications(self):
        Notification.objects.create(
            user=self.fam.children[0], title="A", notification_type="badge_earned",
        )
        Notification.objects.create(
            user=self.fam.children[1], title="B", notification_type="badge_earned",
        )
        Notification.objects.create(
            user=self.other.children[0], title="C", notification_type="badge_earned",
        )
        result = filter_queryset_by_role(
            self.fam.parents[0], Notification.objects.all(),
        )
        self.assertEqual(result.count(), 2)
        # The other family's notification is invisible.
        for note in result:
            self.assertEqual(note.user.family_id, self.fam.family.id)

    def test_child_sees_own(self):
        Notification.objects.create(
            user=self.fam.children[0], title="A", notification_type="badge_earned",
        )
        Notification.objects.create(
            user=self.fam.children[1], title="B", notification_type="badge_earned",
        )
        result = filter_queryset_by_role(
            self.fam.children[0], Notification.objects.all(),
        )
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().user, self.fam.children[0])


class GetChildOr404Tests(TestCase):
    def test_returns_child(self):
        child = User.objects.create_user(username="c", password="pw", role="child")
        self.assertEqual(get_child_or_404(child.id), child)

    def test_returns_none_for_parent(self):
        parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.assertIsNone(get_child_or_404(parent.id))

    def test_returns_none_for_missing_id(self):
        self.assertIsNone(get_child_or_404(99999))

    def test_scopes_to_requesting_users_family(self):
        a = make_family("A", parents=[{"username": "ap"}], children=[{"username": "ac"}])
        b = make_family("B", parents=[{"username": "bp"}], children=[{"username": "bc"}])
        # Parent A asking for child A → returned.
        self.assertEqual(
            get_child_or_404(a.children[0].id, requesting_user=a.parents[0]),
            a.children[0],
        )
        # Parent A asking for child B → 404.
        self.assertIsNone(
            get_child_or_404(b.children[0].id, requesting_user=a.parents[0]),
        )


class ResolveTargetUserTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        # Same family — parent sees their child.
        self.fam = make_family(
            "A",
            parents=[{"username": "p"}],
            children=[{"username": "c"}],
        )
        self.parent = self.fam.parents[0]
        self.child = self.fam.children[0]

    def _drf_request(self, url, user):
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

    def test_parent_with_other_family_child_id_returns_404(self):
        other = make_family("B", children=[{"username": "oc"}])
        request = self._drf_request(
            f"/fake/?user_id={other.children[0].id}", self.parent,
        )
        user, err = resolve_target_user(request)
        self.assertIsNone(user)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 404)
