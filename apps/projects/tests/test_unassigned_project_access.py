"""Parents can author family drafts before assigning them to a child."""
from apps.ingestion.models import ProjectIngestionJob
from apps.projects.models import Project, ProjectStep
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


class UnassignedProjectAccessTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "draft-author"}, {"username": "draft-coparent"}]
    family_children = [{"username": "draft-child"}]

    def setUp(self):
        self.other = make_family(
            "Other draft family", parents=[{"username": "foreign-author"}],
            children=[{"username": "foreign-child"}],
        )
        self.client.force_authenticate(self.parents[0])

    def listed_project_ids(self):
        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        rows = data.get("results", []) if isinstance(data, dict) else data
        return {row["id"] for row in rows}

    def test_import_without_assignee_opens_and_remains_editable_by_family_parents(self):
        job = ProjectIngestionJob.objects.create(
            created_by=self.parents[0], source_type="url", status="ready",
            result_json={"title": "Unassigned import", "steps": [{"title": "Imported step"}]},
        )
        response = self.client.post(f"/api/projects/ingest/{job.pk}/commit/", {}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(pk=response.json()["id"])
        self.assertIsNone(project.assigned_to_id)
        self.assertEqual(project.created_by, self.parents[0])
        self.assertEqual(project.status, Project.Status.DRAFT)
        step = project.steps.get()

        for parent in self.parents:
            with self.subTest(parent=parent.username):
                self.client.force_authenticate(parent)
                self.assertEqual(self.client.get(f"/api/projects/{project.pk}/").status_code, 200)
                self.assertIn(project.pk, self.listed_project_ids())
                response = self.client.patch(
                    f"/api/projects/{project.pk}/", {"description": parent.username}, format="json",
                )
                self.assertEqual(response.status_code, 200, response.content)
                response = self.client.patch(
                    f"/api/projects/{project.pk}/steps/{step.pk}/",
                    {"description": parent.username}, format="json",
                )
                self.assertEqual(response.status_code, 200, response.content)
                response = self.client.post(
                    f"/api/projects/{project.pk}/steps/reorder/",
                    {"items": [{"id": step.pk, "order": 2}]}, format="json",
                )
                self.assertEqual(response.status_code, 200, response.content)

        project.refresh_from_db()
        step.refresh_from_db()
        self.assertEqual(project.description, self.parents[1].username)
        self.assertEqual(step.description, self.parents[1].username)
        self.assertEqual(step.order, 2)

    def test_family_draft_allows_every_nested_resource_create_and_edit(self):
        project = Project.objects.create(title="Draft", created_by=self.parents[0])
        self.client.force_authenticate(self.parents[1])
        for route, payload, edit in (
            ("milestones", {"title": "Phase"}, {"title": "Edited phase"}),
            ("steps", {"title": "Task"}, {"title": "Edited task"}),
            ("materials", {"name": "Wood"}, {"name": "Edited wood"}),
            ("resources", {"url": "https://example.com/draft"}, {"title": "Edited reference"}),
        ):
            with self.subTest(route=route):
                url = f"/api/projects/{project.pk}/{route}/"
                created = self.client.post(url, payload, format="json")
                self.assertEqual(created.status_code, 201, created.content)
                detail = f"{url}{created.json()['id']}/"
                self.assertEqual(self.client.get(detail).status_code, 200)
                edited = self.client.patch(detail, edit, format="json")
                self.assertEqual(edited.status_code, 200, edited.content)

    def test_parent_can_assign_a_previously_unassigned_draft(self):
        created = self.client.post("/api/projects/", {"title": "New draft"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        project_id = created.json()["id"]
        self.assertIn(project_id, self.listed_project_ids())
        assigned = self.client.patch(
            f"/api/projects/{project_id}/", {"assigned_to_id": self.children[0].pk}, format="json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertEqual(Project.objects.get(pk=project_id).assigned_to, self.children[0])
        self.client.force_authenticate(self.children[0])
        self.assertEqual(self.client.get(f"/api/projects/{project_id}/").status_code, 200)

    def test_children_do_not_gain_access_to_unassigned_family_drafts(self):
        project = Project.objects.create(title="Parent draft", created_by=self.parents[0])
        step = ProjectStep.objects.create(project=project, title="Private instructions")
        self.client.force_authenticate(self.children[0])
        self.assertNotIn(project.pk, self.listed_project_ids())
        self.assertEqual(self.client.get(f"/api/projects/{project.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/projects/{project.pk}/steps/{step.pk}/").status_code, 404)

    def test_unassigned_foreign_creator_and_foreign_assignment_remain_inaccessible(self):
        projects = (
            Project.objects.create(title="Foreign draft", created_by=self.other.parents[0]),
            Project.objects.create(
                title="Foreign assignment", created_by=self.parents[0], assigned_to=self.other.children[0],
            ),
        )
        for project in projects:
            with self.subTest(project=project.title):
                step = ProjectStep.objects.create(project=project, title="Foreign instructions")
                self.assertNotIn(project.pk, self.listed_project_ids())
                self.assertEqual(self.client.get(f"/api/projects/{project.pk}/").status_code, 404)
                edited = self.client.patch(f"/api/projects/{project.pk}/", {"title": "Changed"}, format="json")
                self.assertEqual(edited.status_code, 404, edited.content)
                self.assertEqual(self.client.get(f"/api/projects/{project.pk}/steps/{step.pk}/").status_code, 404)
                created = self.client.post(
                    f"/api/projects/{project.pk}/steps/", {"title": "Intrusion"}, format="json",
                )
                self.assertEqual(created.status_code, 404, created.content)
                project.refresh_from_db()
                self.assertNotEqual(project.title, "Changed")
                self.assertEqual(project.steps.count(), 1)

    def test_assigned_family_project_remains_accessible_with_foreign_creator(self):
        project = Project.objects.create(
            title="Family assignment", created_by=self.other.parents[0], assigned_to=self.children[0],
        )
        self.assertIn(project.pk, self.listed_project_ids())
        self.assertEqual(self.client.get(f"/api/projects/{project.pk}/").status_code, 200)
        response = self.client.post(f"/api/projects/{project.pk}/steps/", {"title": "Task"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_unassigned_draft_creator_can_be_any_family_member(self):
        project = Project.objects.create(title="Child-authored draft", created_by=self.children[0])
        self.assertIn(project.pk, self.listed_project_ids())
        self.assertEqual(self.client.get(f"/api/projects/{project.pk}/").status_code, 200)

