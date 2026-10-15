"""Project planning responses from real family-scoped endpoints and provider parsing."""
from copy import deepcopy
import json
from unittest.mock import Mock, patch

from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.projects.models import MaterialItem, Project, ProjectMilestone, ProjectStep
from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


PLAN = {
    "milestones": [{"title": "Prepare the feeder", "description": "Gather supplies before building."}],
    "steps": [
        {"title": "Measure the pieces", "description": "Mark equal lengths with a ruler.", "milestone_index": 0},
        {"title": "Share what worked", "description": "Describe one thing you learned.", "milestone_index": None},
    ],
    "materials": [{"name": "Untreated wood", "description": "Use a clean offcut.", "estimated_cost": "0.00"}],
}


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class ProjectAIPlanApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared_fixtures.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Project AI Fixture Family", family_id=71,
            parents=[{"id": 701, "username": "project-ai-fixture-parent"}],
            children=[{"id": 702, "username": "project-ai-fixture-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.other_parent = make_family(
            "Other Project AI Fixture Family", family_id=72,
            parents=[{"id": 799, "username": "project-ai-fixture-other-parent"}],
        ).parents[0]
        token = Token.objects.create(user=self.parent, key="e" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        saved = self.client.put("/api/homework/ai-settings/", {
            "provider": "openai", "model": "gpt-5.4-mini", "api_key": "synthetic-project-provider-key",
        }, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        self.project = Project.objects.create(
            id=401, title="Build a bird feeder", description="Make a simple feeder together.",
            difficulty=2, created_by=self.parent, assigned_to=self.child,
            parent_notes="Private fixture note excluded from the AI prompt.",
        )
        self.milestone = ProjectMilestone.objects.create(
            id=501, project=self.project, title="Choose a design", order=0,
        )
        self.step = ProjectStep.objects.create(
            id=601, project=self.project, milestone=self.milestone,
            title="Sketch the shape", description="Keep the existing sketch.", order=0,
        )
        self.material = MaterialItem.objects.create(
            id=701, project=self.project, name="Ruler", estimated_cost="2.50",
        )
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [
                Project, ProjectMilestone, ProjectStep, MaterialItem,
            ]):
                cursor.execute(sql)
        response = Mock(status_code=200)
        response.json.return_value = {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(PLAN)}]}],
        }
        provider = patch("requests.post", return_value=response)
        self.provider = provider.start()
        self.addCleanup(provider.stop)

    def state(self):
        return {
            model.__name__: list(model.objects.order_by("id").values())
            for model in (Project, ProjectMilestone, ProjectStep, MaterialItem)
        }

    def assert_saved_plan(self, project, plan):
        milestones = list(project.milestones.order_by("order", "id"))
        steps = list(project.steps.order_by("order", "id"))
        materials = list(project.materials.order_by("id"))
        saved_milestones = milestones[-len(plan["milestones"]):]
        saved_steps = steps[-len(plan["steps"]):]
        saved_materials = materials[-len(plan["materials"]):]
        self.assertEqual(
            [(row.title, row.description) for row in saved_milestones],
            [(row["title"], row["description"]) for row in plan["milestones"]],
        )
        self.assertEqual(
            [(row.title, row.description, row.milestone_id) for row in saved_steps],
            [(row["title"], row["description"],
              None if row["milestone_index"] is None else saved_milestones[row["milestone_index"]].pk)
             for row in plan["steps"]],
        )
        self.assertEqual(
            [(row.name, row.description, str(row.estimated_cost)) for row in saved_materials],
            [(row["name"], row["description"], row["estimated_cost"]) for row in plan["materials"]],
        )

    def test_new_project_plan_is_a_draft_until_reviewed_project_creation(self):
        before = self.state()
        draft = self.assert_response_fixture(self.client.post("/api/projects/plan/", {
            "title": "Build a bird feeder", "description": "Make a simple feeder together.",
            "difficulty": 2, "guidance": "Keep the steps short.",
        }, format="json"), "project-ai-plan-new.json")
        self.assertEqual(draft["plan"], PLAN)
        self.assertIsNone(draft["plan_version"])
        self.assertEqual(self.state(), before)
        self.assertEqual(self.provider.call_count, 1)

        reviewed = deepcopy(draft["plan"])
        reviewed["materials"][0]["estimated_cost"] = "6.25"
        created = self.client.post("/api/projects/", {
            "title": "Our reviewed bird feeder", "difficulty": 2,
            "assigned_to": self.child.pk, "plan_create": reviewed,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        project = Project.objects.get(title="Our reviewed bird feeder")
        self.assert_saved_plan(project, reviewed)
        self.assertEqual(self.provider.call_count, 1)

    def test_existing_project_plan_is_reviewed_appended_once_and_protects_current_work(self):
        before = self.state()
        draft = self.assert_response_fixture(self.client.post(
            f"/api/projects/{self.project.pk}/plan/", {"guidance": "Keep the existing sketch."}, format="json",
        ), "project-ai-plan-existing.json")
        self.assertEqual(draft["plan"], PLAN)
        self.assertRegex(draft["plan_version"], r"^[a-f0-9]{64}$")
        self.assertEqual(self.state(), before)
        request_body = self.provider.call_args.kwargs["json"]
        self.assertNotIn(self.project.parent_notes, json.dumps(request_body))
        reviewed = deepcopy(draft["plan"])
        reviewed["materials"][0]["estimated_cost"] = "6.25"
        payload = {"plan": reviewed, "plan_version": draft["plan_version"]}
        self.assert_response_fixture(self.client.post(
            f"/api/projects/{self.project.pk}/apply-plan/", payload, format="json",
        ), "project-ai-plan-applied.json")
        self.assert_saved_plan(self.project, reviewed)
        self.milestone.refresh_from_db()
        self.step.refresh_from_db()
        self.material.refresh_from_db()
        self.assertEqual(self.milestone.title, "Choose a design")
        self.assertEqual((self.step.title, self.step.description, self.step.milestone_id), (
            "Sketch the shape", "Keep the existing sketch.", self.milestone.pk,
        ))
        self.assertEqual(str(self.material.estimated_cost), "2.50")
        applied_state = self.state()
        repeated = self.client.post(f"/api/projects/{self.project.pk}/apply-plan/", payload, format="json")
        self.assertEqual(repeated.status_code, 409, repeated.content)
        self.assertEqual(self.state(), applied_state)
        self.assertEqual(self.provider.call_count, 1)

    def test_children_and_foreign_parents_cannot_generate_or_apply_a_saved_project_plan(self):
        before = self.state()
        for user in (self.child, self.other_parent):
            self.client.force_authenticate(user)
            for action in ("plan", "apply-plan"):
                with self.subTest(user=user.username, action=action):
                    payload = {"guidance": "Do not change another family."} if action == "plan" else {
                        "plan": PLAN, "plan_version": "0" * 64,
                    }
                    response = self.client.post(
                        f"/api/projects/{self.project.pk}/{action}/", payload, format="json",
                    )
                    self.assertEqual(response.status_code, 403 if user == self.child else 404, response.content)
        self.assertEqual(self.state(), before)
        self.provider.assert_not_called()
