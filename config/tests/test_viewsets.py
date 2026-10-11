"""Tests for config.viewsets — helpers and mixins."""
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.notifications.models import Notification
from apps.projects.models import Project, ProjectCollaborator, ProjectResource, ProjectStep, User
from config.tests.factories import make_family
from config.viewsets import (
    filter_projects_accessible_to, filter_queryset_by_role, filter_resources_under_accessible_projects,
    get_child_or_404, resolve_target_user,
)


class ProjectAccessFilterTests(TestCase):
    def setUp(self):
        self.fam = make_family(
            "Project access", parents=[{"username": "access-parent"}],
            children=[{"username": "access-child"}, {"username": "access-sibling"}],
        )
        self.other = make_family(
            "Foreign project access", parents=[{"username": "foreign-access-parent"}],
            children=[{"username": "foreign-access-child"}],
        )
        self.draft = Project.objects.create(title="Family draft", created_by=self.fam.parents[0])
        self.assigned = Project.objects.create(
            title="Family assignment", created_by=self.other.parents[0], assigned_to=self.fam.children[0],
        )
        self.foreign_draft = Project.objects.create(title="Foreign draft", created_by=self.other.parents[0])
        self.foreign_assignment = Project.objects.create(
            title="Foreign assignment", created_by=self.fam.parents[0], assigned_to=self.other.children[0],
        )
        for project in (self.draft, self.assigned, self.foreign_draft, self.foreign_assignment):
            step = ProjectStep.objects.create(project=project, title="Task")
            ProjectResource.objects.create(project=project, step=step, url="https://example.com/task")

    def test_parent_project_and_nested_filters_apply_the_same_family_rule(self):
        expected = {self.draft.pk, self.assigned.pk}
        projects = filter_projects_accessible_to(self.fam.parents[0], Project.objects.all())
        self.assertEqual(set(projects.values_list("pk", flat=True)), expected)
        steps = filter_resources_under_accessible_projects(self.fam.parents[0], ProjectStep.objects.all())
        self.assertEqual(set(steps.values_list("project_id", flat=True)), expected)

    def test_nested_filter_supports_an_indirect_project_field(self):
        resources = filter_resources_under_accessible_projects(
            self.fam.parents[0], ProjectResource.objects.all(), project_field="step__project",
        )
        self.assertEqual(set(resources.values_list("project_id", flat=True)), {self.draft.pk, self.assigned.pk})

    def test_child_assignee_and_collaborator_access_is_preserved_without_draft_access(self):
        ProjectCollaborator.objects.create(project=self.assigned, user=self.fam.children[1])
        for child in self.fam.children:
            with self.subTest(child=child.username):
                projects = filter_projects_accessible_to(child, Project.objects.all())
                self.assertEqual(set(projects.values_list("pk", flat=True)), {self.assigned.pk})
                steps = filter_resources_under_accessible_projects(child, ProjectStep.objects.all())
                self.assertEqual(set(steps.values_list("project_id", flat=True)), {self.assigned.pk})


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
