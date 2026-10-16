"""AI drafts require a family connection and an explicit reviewed save."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from apps.homework.ai_settings import update_settings
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.projects.models import MaterialItem, Project, ProjectMilestone, ProjectStep
from apps.rewards.models import CoinLedger
from config.llm import LLMError
from config.tests.factories import make_family


PLAN = {
    "milestones": [{"title": "Prepare", "description": "Get ready."}],
    "steps": [{"title": "Gather materials", "description": "Use safe supplies.", "milestone_index": 0}],
    "materials": [{"name": "Wood", "description": "Scrap wood.", "estimated_cost": "0.00"}],
}
BRIEF = {"title": "Bird feeder", "description": "A public project brief.", "difficulty": 2, "guidance": "Keep it simple."}
URL = "/api/projects/plan/"


class ProjectAIPlanningTests(APITestCase):
    def setUp(self):
        self.house = make_family(
            parents=[{"username": "project-ai-parent"}, {"username": "project-ai-coparent"}],
            children=[{"username": "project-ai-child"}],
        )
        self.other = make_family(
            "Other project AI family", parents=[{"username": "other-project-ai-parent"}],
            children=[{"username": "other-project-ai-child"}],
        )
        self.parent = self.house.parents[0]
        self.child = self.house.children[0]
        self.client.force_authenticate(self.parent)
        self.connect()

    def connect(self, provider="openai", model="gpt-test", family=None):
        update_settings(family or self.house.family, provider=provider, model=model, api_key="synthetic-family-key")

    def project(self, **overrides):
        return Project.objects.create(
            **{"title": "Stored public title", "description": "Stored public description", "difficulty": 3,
               "created_by": self.parent, "assigned_to": self.child,
               "parent_notes": "Never send this private note", "bonus_amount": "91.23", **overrides},
        )

    def counts(self):
        return tuple(model.objects.count() for model in (
            Project, ProjectMilestone, ProjectStep, MaterialItem, PaymentLedger, CoinLedger, Notification,
        ))

    def draft_existing(self, project):
        response = self.client.post(f"/api/projects/{project.pk}/plan/", {"guidance": "Add a finishing task."}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    @patch("config.llm.complete_json")
    def test_new_preview_uses_selected_family_provider_without_any_writes(self, complete):
        for provider, model in (("openai", "gpt-test"), ("anthropic", "claude-test")):
            with self.subTest(provider=provider):
                self.connect(provider, model)
                generated = deepcopy(PLAN)
                generated["materials"][0]["estimated_cost"] = "999.99"
                complete.return_value = generated
                before = self.counts()
                response = self.client.post(URL, BRIEF, format="json")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.data, {"plan": PLAN, "plan_version": None})
                self.assertEqual(self.counts(), before)
                self.assertEqual(complete.call_args.kwargs["backend"], provider)
                self.assertEqual(complete.call_args.kwargs["model"], model)
                self.assertEqual(complete.call_args.kwargs["api_key"], "synthetic-family-key")
                self.assertEqual(complete.call_args.kwargs["max_tokens"], 8192)
                self.assertIn(BRIEF["description"], complete.call_args.kwargs["prompt"])
                self.assertIn(BRIEF["guidance"], complete.call_args.kwargs["prompt"])

    @patch("config.llm.complete_json", return_value=PLAN)
    def test_all_planning_actions_are_parent_only_and_family_scoped(self, complete):
        project = self.project()
        for user, expected in ((None, 401), (self.child, 403)):
            self.client.force_authenticate(user)
            for url, payload in ((URL, BRIEF), (f"/api/projects/{project.pk}/plan/", {}),
                                 (f"/api/projects/{project.pk}/apply-plan/", {"plan": PLAN, "plan_version": "0" * 64})):
                with self.subTest(user=user, url=url):
                    self.assertEqual(self.client.post(url, payload, format="json").status_code, expected)
        self.client.force_authenticate(self.other.parents[0])
        for action in ("plan", "apply-plan"):
            self.assertEqual(self.client.post(f"/api/projects/{project.pk}/{action}/", {}, format="json").status_code, 404)
        complete.assert_not_called()
        self.client.force_authenticate(self.house.parents[1])
        self.assertEqual(self.client.post(URL, BRIEF, format="json").status_code, 200)

    @patch("config.llm.complete_json")
    @override_settings(LLM_BACKEND="auto", ANTHROPIC_API_KEY="synthetic-deployment-key")
    def test_missing_or_corrupt_family_connection_never_uses_deployment_credentials(self, complete):
        project = self.project()
        update_settings(self.house.family, provider="default", model="")
        for url, payload in ((URL, BRIEF), (f"/api/projects/{project.pk}/plan/", {})):
            response = self.client.post(url, payload, format="json")
            self.assertEqual(response.status_code, 501)
            self.assertIn("Settings → Planning AI", response.data["error"])
        self.connect()
        with override_settings(SECRET_KEY="another-synthetic-key"):
            self.assertEqual(self.client.post(URL, BRIEF, format="json").status_code, 400)
        complete.assert_not_called()

    @patch("config.llm.complete_json")
    def test_request_validation_rejects_selectors_and_unbounded_text_without_provider_calls(self, complete):
        for fields in ({"title": ""}, {"title": "x" * 201}, {"description": "x" * 10001},
                       {"difficulty": 0}, {"difficulty": 6}, {"guidance": "x" * 2001},
                       {"provider": "openai"}, {"family": self.other.family.pk}, {"parent_notes": "private"}):
            with self.subTest(fields=tuple(fields)):
                self.assertEqual(self.client.post(URL, {**BRIEF, **fields}, format="json").status_code, 400)
        complete.assert_not_called()

    @patch("config.llm.complete_json")
    def test_invalid_provider_output_fails_safely_without_writes(self, complete):
        cases = [None, [], {}, {**PLAN, "steps": []}, {**PLAN, "bonus_amount": "999.00"},
                 {**PLAN, "milestones": PLAN["milestones"] * 11}, {**PLAN, "steps": PLAN["steps"] * 41},
                 {**PLAN, "materials": PLAN["materials"] * 41}]
        for index in (-1, 1, True, 0.0, "0"):
            cases.append({**PLAN, "steps": [{**PLAN["steps"][0], "milestone_index": index}]})
        cases.append({**PLAN, "steps": [{**PLAN["steps"][0], "title": "x" * 201}]})
        cases.append({**PLAN, "materials": [{**PLAN["materials"][0], "reimbursed": True}]})
        before = self.counts()
        for payload in cases:
            with self.subTest(payload_type=type(payload).__name__):
                complete.return_value = payload
                response = self.client.post(URL, BRIEF, format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertNotIn("synthetic-family-key", response.content.decode())
        self.assertEqual(self.counts(), before)

    @patch("config.llm.complete_json", side_effect=LLMError("private-provider-error"))
    def test_provider_errors_do_not_escape_to_the_response(self, complete):
        response = self.client.post(URL, BRIEF, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("private-provider-error", response.content.decode())

    def test_reviewed_plan_create_saves_all_items_and_links_atomically(self):
        reviewed = deepcopy(PLAN)
        reviewed["materials"][0]["estimated_cost"] = "12.34"
        response = self.client.post("/api/projects/", {
            "title": "Reviewed draft", "plan_create": reviewed, "bonus_amount": "5.00",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(pk=response.data["id"])
        self.assertEqual(project.status, "draft")
        self.assertEqual(project.bonus_amount, Decimal("5.00"))
        self.assertEqual(project.steps.get().milestone_id, project.milestones.get().pk)
        self.assertEqual(project.materials.get().estimated_cost, Decimal("12.34"))
        self.assertFalse(project.steps.get().is_completed)
        self.assertFalse(project.milestones.get().is_completed)

    def test_reviewed_plan_validation_prevents_writes_and_rejects_legacy_mix_or_updates(self):
        for price in ("-1.00", "1000000.00", "1.001", "NaN"):
            reviewed = deepcopy(PLAN)
            reviewed["materials"][0]["estimated_cost"] = price
            self.assertEqual(self.client.post("/api/projects/", {"title": "Invalid", "plan_create": reviewed}, format="json").status_code, 400)
        for legacy in ("steps_create", "resources_create"):
            self.assertEqual(self.client.post("/api/projects/", {"title": "Invalid", "plan_create": PLAN, legacy: []}, format="json").status_code, 400)
        self.assertFalse(Project.objects.exists())
        project = self.project()
        self.assertEqual(self.client.patch(f"/api/projects/{project.pk}/", {"plan_create": PLAN}, format="json").status_code, 400)
        self.assertFalse(project.steps.exists())

    def test_plan_create_rolls_back_the_project_and_prior_plan_items_if_insertion_fails(self):
        with patch("apps.projects.planning.MaterialItem.objects.create", side_effect=RuntimeError("synthetic insertion failure")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/projects/", {"title": "Rollback", "plan_create": PLAN}, format="json")
        self.assertFalse(Project.objects.exists())
        self.assertFalse(ProjectMilestone.objects.exists())
        self.assertFalse(ProjectStep.objects.exists())

    @patch("config.llm.complete_json", return_value=PLAN)
    def test_existing_preview_uses_public_context_and_captures_version_without_writes(self, complete):
        project = self.project()
        milestone = ProjectMilestone.objects.create(project=project, title="Old phase")
        ProjectStep.objects.create(project=project, title="Old task", milestone=milestone)
        MaterialItem.objects.create(project=project, name="Old supply", estimated_cost="87.65")
        before = self.counts()
        draft = self.draft_existing(project)
        self.assertEqual(draft["plan"], PLAN)
        self.assertRegex(draft["plan_version"], r"^[a-f0-9]{64}$")
        prompt = complete.call_args.kwargs["prompt"]
        for text in (project.title, project.description, "Old phase", "Old task", "Old supply", "Add a finishing task."):
            self.assertIn(text, prompt)
        for private in (project.parent_notes, self.parent.username, self.child.username, "91.23", "87.65"):
            self.assertNotIn(private, prompt)
        self.assertEqual(self.counts(), before)
        response = self.client.post(f"/api/projects/{project.pk}/plan/", {"title": "Cannot override existing context"}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("config.llm.complete_json", return_value=PLAN)
    def test_apply_appends_once_preserving_existing_progress_and_manual_fields(self, complete):
        project = self.project(status="in_progress")
        milestone = ProjectMilestone.objects.create(project=project, title="Keep phase", order=4, bonus_amount="7.50")
        step = ProjectStep.objects.create(project=project, title="Keep task", order=9, milestone=milestone)
        ProjectMilestone.objects.filter(pk=milestone.pk).update(is_completed=True)
        ProjectStep.objects.filter(pk=step.pk).update(is_completed=True)
        material = MaterialItem.objects.create(project=project, name="Keep supply", estimated_cost="8.00", is_purchased=True)
        draft = self.draft_existing(project)
        reward_counts = self.counts()[4:]
        url = f"/api/projects/{project.pk}/apply-plan/"
        response = self.client.post(url, draft, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data, {"applied": True})
        self.assertEqual(project.milestones.count(), 2)
        self.assertEqual(project.steps.count(), 2)
        self.assertEqual(project.materials.count(), 2)
        self.assertEqual(self.counts()[4:], reward_counts)
        added_phase = project.milestones.exclude(pk=milestone.pk).get()
        added_step = project.steps.exclude(pk=step.pk).get()
        self.assertEqual(added_phase.order, 5)
        self.assertEqual(added_step.order, 10)
        self.assertEqual(added_step.milestone_id, added_phase.pk)
        project.refresh_from_db()
        milestone.refresh_from_db()
        step.refresh_from_db()
        material.refresh_from_db()
        self.assertEqual(project.status, "in_progress")
        self.assertEqual(project.bonus_amount, Decimal("91.23"))
        self.assertEqual(project.parent_notes, "Never send this private note")
        self.assertEqual(milestone.bonus_amount, Decimal("7.50"))
        self.assertTrue(milestone.is_completed)
        self.assertTrue(step.is_completed)
        self.assertTrue(material.is_purchased)
        counts = self.counts()
        self.assertEqual(self.client.post(url, draft, format="json").status_code, 409)
        self.assertEqual(self.counts(), counts)

    @patch("config.llm.complete_json", return_value=PLAN)
    def test_stale_snapshot_and_changes_during_generation_require_a_fresh_plan(self, complete):
        project = self.project()
        step = ProjectStep.objects.create(project=project, title="Original")
        draft = self.draft_existing(project)
        ProjectStep.objects.filter(pk=step.pk).update(description="Edited after preview")
        before = self.counts()
        self.assertEqual(self.client.post(f"/api/projects/{project.pk}/apply-plan/", draft, format="json").status_code, 409)
        self.assertEqual(self.counts(), before)
        def edit_while_generating(**_kwargs):
            Project.objects.filter(pk=project.pk).update(description="Changed during provider request")
            return PLAN
        complete.side_effect = edit_while_generating
        draft = self.draft_existing(project)
        self.assertEqual(self.client.post(f"/api/projects/{project.pk}/apply-plan/", draft, format="json").status_code, 409)

    @patch("config.llm.complete_json", return_value=PLAN)
    def test_apply_rejects_malformed_plan_and_preserves_legacy_project_create(self, complete):
        project = self.project()
        draft = self.draft_existing(project)
        for body in ({**draft, "plan_version": "invalid"}, {**draft, "family": self.other.family.pk},
                     {**draft, "plan": {**PLAN, "steps": []}}):
            self.assertEqual(self.client.post(f"/api/projects/{project.pk}/apply-plan/", body, format="json").status_code, 400)
        self.assertFalse(project.steps.exists())
        response = self.client.post("/api/projects/", {"title": "Legacy", "steps_create": [{"title": "Old path"}]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(ProjectStep.objects.filter(project_id=response.data["id"], title="Old path").exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ProjectPlanApplyConcurrencyTests(TransactionTestCase):
    def test_two_simultaneous_apply_requests_append_the_reviewed_plan_only_once(self):
        from apps.projects.planning import project_plan_snapshot

        family = make_family(parents=[{"username": "apply-race-a"}, {"username": "apply-race-b"}])
        project = Project.objects.create(title="Concurrent append", created_by=family.parents[0])
        version, _ = project_plan_snapshot(project)
        payload = {"plan": PLAN, "plan_version": version}
        barrier = Barrier(2)

        def apply(user):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '3s'")
                    cursor.execute("SET statement_timeout = '5s'")
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait(timeout=5)
                response = client.post(f"/api/projects/{project.pk}/apply-plan/", payload, format="json")
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(apply, parent) for parent in family.parents]
            self.assertEqual(sorted(future.result(timeout=10) for future in futures), [200, 409])
        self.assertEqual(project.milestones.count(), 1)
        self.assertEqual(project.steps.count(), 1)
        self.assertEqual(project.materials.count(), 1)
