"""Cross-family scoping for project assignment + collaborator endpoints.

Pinned because PrimaryKeyRelatedField on assigned_to_id / user_id was
unscoped (queryset=User.objects.all()) — a parent could POST a project
assigned to another family's child, or attach a foreign-family child
as a collaborator. The serializer-level validators close the leak.
"""
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.projects.models import Project, ProjectCollaborator, ProjectTemplate
from config.tests.factories import make_family


class _Fixture(APITestCase):
    def setUp(self):
        self.a = make_family(
            "Family A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "Family B",
            parents=[{"username": "bp"}],
            children=[{"username": "bc"}],
        )
        self.a_token = Token.objects.create(user=self.a.parents[0])
        self.b_token = Token.objects.create(user=self.b.parents[0])

    def _auth_a(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.a_token.key}")


class ProjectAssignmentFamilyScopingTests(_Fixture):
    def test_create_assigned_to_own_child_succeeds(self):
        self._auth_a()
        resp = self.client.post(
            "/api/projects/",
            {
                "title": "Birdhouse",
                "difficulty": 2,
                "assigned_to_id": self.a.children[0].id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(Project.objects.filter(title="Birdhouse").exists())

    def test_create_assigned_to_foreign_child_rejected(self):
        self._auth_a()
        resp = self.client.post(
            "/api/projects/",
            {
                "title": "Sneaky",
                "difficulty": 2,
                "assigned_to_id": self.b.children[0].id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Project.objects.filter(title="Sneaky").exists())

    def test_patch_reassign_to_foreign_child_rejected(self):
        # Parent A creates a project assigned to their own child first…
        project = Project.objects.create(
            title="Mine", assigned_to=self.a.children[0],
            created_by=self.a.parents[0],
        )
        self._auth_a()
        # …then tries to reassign to Family B's child.
        resp = self.client.patch(
            f"/api/projects/{project.pk}/",
            {"assigned_to_id": self.b.children[0].id},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        project.refresh_from_db()
        self.assertEqual(project.assigned_to_id, self.a.children[0].id)


class ProjectCollaboratorFamilyScopingTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="Co-op", assigned_to=self.a.children[0],
            created_by=self.a.parents[0],
        )

    def test_add_collaborator_from_own_family_succeeds(self):
        # Add a second child to Family A so we have someone to add.
        from apps.accounts.models import User
        sibling = User.objects.create_user(
            username="ac2", password="pw", role="child",
            family=self.a.family,
        )
        self._auth_a()
        resp = self.client.post(
            f"/api/projects/{self.project.pk}/collaborators/",
            {"user_id": sibling.id, "pay_split_percent": "50.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(
            ProjectCollaborator.objects.filter(
                project=self.project, user=sibling,
            ).exists(),
        )

    def test_add_collaborator_from_foreign_family_rejected(self):
        self._auth_a()
        resp = self.client.post(
            f"/api/projects/{self.project.pk}/collaborators/",
            {"user_id": self.b.children[0].id, "pay_split_percent": "50.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(
            ProjectCollaborator.objects.filter(
                project=self.project, user=self.b.children[0],
            ).exists(),
        )


class TemplateCreateProjectFamilyScopingTests(_Fixture):
    def test_create_project_from_template_for_foreign_child_rejected(self):
        # Template lives in Family A.
        template = ProjectTemplate.objects.create(
            title="Birdhouse Template", description="x", difficulty=2,
            created_by=self.a.parents[0], family=self.a.family,
        )
        self._auth_a()
        resp = self.client.post(
            f"/api/templates/{template.pk}/create-project/",
            {"assigned_to_id": self.b.children[0].id},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Project.objects.filter(title="Birdhouse Template").exists())

    def test_create_project_from_template_for_own_child_succeeds(self):
        template = ProjectTemplate.objects.create(
            title="Tpl-OK", description="x", difficulty=2,
            created_by=self.a.parents[0], family=self.a.family,
        )
        self._auth_a()
        resp = self.client.post(
            f"/api/templates/{template.pk}/create-project/",
            {"assigned_to_id": self.a.children[0].id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(Project.objects.filter(title="Tpl-OK").exists())
