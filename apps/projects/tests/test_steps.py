"""Tests for ProjectStep / ProjectResource viewsets and serializers."""
from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import (
    Project, ProjectMilestone, ProjectResource, ProjectStep, ProjectTemplate,
    TemplateMilestone, TemplateResource, TemplateStep, User,
)
from apps.projects.serializers import ProjectDetailSerializer


class _Fixture(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.other_child = User.objects.create_user(
            username="other", password="pw", role="child",
        )
        self.project = Project.objects.create(
            title="Birdhouse",
            created_by=self.parent,
            assigned_to=self.child,
            status="in_progress",
        )
        self.client = APIClient()


class ProjectStepPermissionTests(_Fixture):
    def test_parent_can_create_step(self) -> None:
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/steps/",
            {"project": self.project.id, "title": "Cut wood", "description": "Use the saw."},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(ProjectStep.objects.filter(project=self.project).count(), 1)

    def test_child_cannot_create_step(self) -> None:
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/steps/",
            {"project": self.project.id, "title": "Sneak"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_child_can_complete_own_step(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="Sand", order=0)
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/steps/{step.id}/complete/",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        step.refresh_from_db()
        self.assertTrue(step.is_completed)
        self.assertIsNotNone(step.completed_at)

    def test_other_child_cannot_complete_step(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="Sand", order=0)
        self.client.force_authenticate(self.other_child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/steps/{step.id}/complete/",
        )
        # The "other" child isn't assigned or a collaborator — should be blocked.
        self.assertEqual(resp.status_code, 403)
        step.refresh_from_db()
        self.assertFalse(step.is_completed)

    def test_child_can_uncomplete_own_step(self) -> None:
        from django.utils import timezone
        step = ProjectStep.objects.create(
            project=self.project, title="Sand", order=0,
            is_completed=True, completed_at=timezone.now(),
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/steps/{step.id}/uncomplete/",
        )
        self.assertEqual(resp.status_code, 200)
        step.refresh_from_db()
        self.assertFalse(step.is_completed)
        self.assertIsNone(step.completed_at)

    def test_child_cannot_delete_step(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="Sand", order=0)
        self.client.force_authenticate(self.child)
        resp = self.client.delete(
            f"/api/projects/{self.project.id}/steps/{step.id}/",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(ProjectStep.objects.filter(pk=step.id).exists())


class ReorderStepsTests(_Fixture):
    def test_reorder_renumbers_atomically(self) -> None:
        s1 = ProjectStep.objects.create(project=self.project, title="A", order=0)
        s2 = ProjectStep.objects.create(project=self.project, title="B", order=1)
        s3 = ProjectStep.objects.create(project=self.project, title="C", order=2)

        self.client.force_authenticate(self.parent)
        # Reverse the order.
        resp = self.client.post(
            f"/api/projects/{self.project.id}/steps/reorder/",
            [
                {"id": s3.id, "order": 0},
                {"id": s2.id, "order": 1},
                {"id": s1.id, "order": 2},
            ],
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        s1.refresh_from_db()
        s2.refresh_from_db()
        s3.refresh_from_db()
        self.assertEqual(s3.order, 0)
        self.assertEqual(s2.order, 1)
        self.assertEqual(s1.order, 2)


class ProjectResourcePermissionTests(_Fixture):
    def test_parent_creates_project_level_resource(self) -> None:
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/resources/",
            {
                "project": self.project.id,
                "title": "Overview video",
                "url": "https://example.com/video",
                "resource_type": "video",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(ProjectResource.objects.count(), 1)

    def test_child_cannot_create_resource(self) -> None:
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            f"/api/projects/{self.project.id}/resources/",
            {
                "project": self.project.id,
                "url": "https://example.com/video",
                "resource_type": "video",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_resource_step_filter(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="Build", order=0)
        ProjectResource.objects.create(
            project=self.project, step=step, url="https://x/step", resource_type="link",
        )
        ProjectResource.objects.create(
            project=self.project, step=None, url="https://x/proj", resource_type="link",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get(
            f"/api/projects/{self.project.id}/resources/?step=null",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://x/proj")

    def test_deleting_step_cascades_resources(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="Build", order=0)
        ProjectResource.objects.create(
            project=self.project, step=step, url="https://x/y",
        )
        self.assertEqual(ProjectResource.objects.count(), 1)
        step.delete()
        self.assertEqual(ProjectResource.objects.count(), 0)


class ProjectDetailSerializerNestingTests(_Fixture):
    def test_steps_nest_resources_and_top_level_only_project_level(self) -> None:
        """``resources`` top-level should only include step__isnull=True rows
        so step-scoped resources aren't double-counted."""
        step = ProjectStep.objects.create(project=self.project, title="Cut", order=0)
        ProjectResource.objects.create(
            project=self.project, step=step, url="https://x/a",
        )
        ProjectResource.objects.create(
            project=self.project, step=None, url="https://x/root",
        )

        data = ProjectDetailSerializer(self.project).data
        self.assertEqual(len(data["steps"]), 1)
        self.assertEqual(len(data["steps"][0]["resources"]), 1)
        self.assertEqual(data["steps"][0]["resources"][0]["url"], "https://x/a")

        # Top-level ``resources`` only includes the project-level one.
        self.assertEqual(len(data["resources"]), 1)
        self.assertEqual(data["resources"][0]["url"], "https://x/root")

    def test_step_serializer_exposes_milestone_fk(self) -> None:
        """``ProjectStepSerializer`` should round-trip the ``milestone`` FK so
        the frontend can group steps under their phase client-side."""
        ms = ProjectMilestone.objects.create(
            project=self.project, title="Build phase", order=0,
        )
        ProjectStep.objects.create(
            project=self.project, milestone=ms, title="Cut", order=0,
        )
        ProjectStep.objects.create(
            project=self.project, milestone=None, title="Loose", order=1,
        )

        data = ProjectDetailSerializer(self.project).data
        steps_by_title = {s["title"]: s for s in data["steps"]}
        self.assertEqual(steps_by_title["Cut"]["milestone"], ms.id)
        self.assertIsNone(steps_by_title["Loose"]["milestone"])


class TemplateCloneTests(_Fixture):
    def test_create_project_from_template_copies_steps_and_resources(self) -> None:
        """Template → new project should preserve the step→resource FK map."""
        template = ProjectTemplate.objects.create(
            title="Tmpl", created_by=self.parent,
        )
        t_step_a = TemplateStep.objects.create(
            template=template, title="A", order=0,
        )
        t_step_b = TemplateStep.objects.create(
            template=template, title="B", order=1,
        )
        TemplateResource.objects.create(
            template=template, step=t_step_a,
            url="https://x/a", resource_type="video",
        )
        TemplateResource.objects.create(
            template=template, step=t_step_b,
            url="https://x/b", resource_type="video",
        )
        TemplateResource.objects.create(
            template=template, step=None,
            url="https://x/overview", resource_type="link",
        )

        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/templates/{template.id}/create-project/",
            {"assigned_to_id": self.child.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        project = Project.objects.get(pk=resp.json()["id"])

        steps = list(project.steps.order_by("order"))
        self.assertEqual([s.title for s in steps], ["A", "B"])

        resources = list(project.resources.all())
        self.assertEqual(len(resources), 3)
        # Step A's resource should point at step 0's pk (not template pk).
        by_url = {r.url: r for r in resources}
        self.assertEqual(by_url["https://x/a"].step_id, steps[0].id)
        self.assertEqual(by_url["https://x/b"].step_id, steps[1].id)
        self.assertIsNone(by_url["https://x/overview"].step_id)

    def test_create_project_from_template_preserves_step_milestone_linkage(self) -> None:
        """Cloning a template should rebind step→milestone FKs to the NEW
        project's milestones, not leave them pointing at template pks."""
        template = ProjectTemplate.objects.create(
            title="Tmpl", created_by=self.parent,
        )
        t_ms_prep = TemplateMilestone.objects.create(
            template=template, title="Prep", order=0,
        )
        t_ms_build = TemplateMilestone.objects.create(
            template=template, title="Build", order=1,
        )
        TemplateStep.objects.create(
            template=template, milestone=t_ms_prep, title="Gather", order=0,
        )
        TemplateStep.objects.create(
            template=template, milestone=t_ms_build, title="Saw", order=1,
        )
        TemplateStep.objects.create(
            template=template, milestone=None, title="Admire", order=2,
        )

        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/templates/{template.id}/create-project/",
            {"assigned_to_id": self.child.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        project = Project.objects.get(pk=resp.json()["id"])

        prep, build = list(project.milestones.order_by("order"))
        # The cloned milestones must belong to the new project, not the template.
        self.assertEqual(prep.project_id, project.id)
        self.assertEqual(build.project_id, project.id)

        steps = {s.title: s for s in project.steps.all()}
        self.assertEqual(steps["Gather"].milestone_id, prep.id)
        self.assertEqual(steps["Saw"].milestone_id, build.id)
        self.assertIsNone(steps["Admire"].milestone_id)

    def test_save_project_as_template_preserves_step_milestone_linkage(self) -> None:
        """Saving a project as a template should rebind step→milestone FKs to
        the new ``TemplateMilestone`` rows, not the source project's pks."""
        ms_prep = ProjectMilestone.objects.create(
            project=self.project, title="Prep", order=0,
        )
        ms_build = ProjectMilestone.objects.create(
            project=self.project, title="Build", order=1,
        )
        ProjectStep.objects.create(
            project=self.project, milestone=ms_prep, title="Gather", order=0,
        )
        ProjectStep.objects.create(
            project=self.project, milestone=ms_build, title="Saw", order=1,
        )
        ProjectStep.objects.create(
            project=self.project, milestone=None, title="Admire", order=2,
        )

        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            "/api/templates/from-project/",
            {"project_id": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        template = ProjectTemplate.objects.get(pk=resp.json()["id"])

        t_prep, t_build = list(template.milestones.order_by("order"))
        # The cloned milestones must belong to the new template.
        self.assertEqual(t_prep.template_id, template.id)
        self.assertEqual(t_build.template_id, template.id)

        steps = {s.title: s for s in template.steps.all()}
        self.assertEqual(steps["Gather"].milestone_id, t_prep.id)
        self.assertEqual(steps["Saw"].milestone_id, t_build.id)
        self.assertIsNone(steps["Admire"].milestone_id)

    def test_save_project_as_template_copies_steps_and_resources(self) -> None:
        """Inverse direction: project → new template should preserve FK map."""
        p_step_a = ProjectStep.objects.create(
            project=self.project, title="A", order=0,
        )
        p_step_b = ProjectStep.objects.create(
            project=self.project, title="B", order=1,
        )
        ProjectResource.objects.create(
            project=self.project, step=p_step_a, url="https://x/a",
        )
        ProjectResource.objects.create(
            project=self.project, step=None, url="https://x/proj",
        )
        ProjectResource.objects.create(
            project=self.project, step=p_step_b, url="https://x/b",
        )

        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            "/api/templates/from-project/",
            {"project_id": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        template = ProjectTemplate.objects.get(pk=resp.json()["id"])
        steps = list(template.steps.order_by("order"))
        self.assertEqual([s.title for s in steps], ["A", "B"])

        by_url = {r.url: r for r in template.resources.all()}
        self.assertEqual(by_url["https://x/a"].step_id, steps[0].id)
        self.assertEqual(by_url["https://x/b"].step_id, steps[1].id)
        self.assertIsNone(by_url["https://x/proj"].step_id)
