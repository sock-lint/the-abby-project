"""Tests for project-related MCP tools."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    CreateProjectIn,
    GetProjectIn,
    ListProjectsIn,
    NewMilestone,
    NewProjectSkillTag,
    NewResource,
    NewStep,
    UpdateProjectStatusIn,
)
from apps.mcp_server.tools import projects as project_tools
from apps.achievements.models import ProjectSkillTag, Skill, SkillCategory, Subject
from apps.accounts.models import User
from apps.projects.models import (
    Project, ProjectMilestone, ProjectResource, ProjectStep,
)


class CreateProjectTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="mom", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="kid", password="pw", role="child",
        )
        self.category = SkillCategory.objects.create(name="Electronics")
        subject = Subject.objects.create(name="Basics", category=self.category)
        self.skill = Skill.objects.create(
            name="Soldering", category=self.category, subject=subject,
        )

    def test_parent_can_create_project_with_skill_tags(self) -> None:
        payload = CreateProjectIn(
            title="Build a weather station",
            description="First hardware build",
            assigned_to_id=self.child.id,
            difficulty=2,
            category_id=self.category.id,
            bonus_amount=Decimal("5.00"),
            payment_kind="required",
            milestones=[
                NewMilestone(title="Gather parts"),
                NewMilestone(title="Assemble circuit"),
            ],
            skill_tags=[NewProjectSkillTag(skill_id=self.skill.id, xp_weight=1)],
        )
        with override_user(self.parent):
            result = project_tools.create_project(payload)

        self.assertEqual(result["title"], "Build a weather station")
        self.assertEqual(len(result["milestones"]), 2)
        self.assertEqual(len(result["skill_tags"]), 1)
        project = Project.objects.get(pk=result["id"])
        self.assertEqual(project.assigned_to, self.child)
        self.assertEqual(project.created_by, self.parent)
        self.assertEqual(
            ProjectSkillTag.objects.filter(project=project).count(), 1,
        )

    def test_child_cannot_create_project(self) -> None:
        payload = CreateProjectIn(
            title="Sneaky", assigned_to_id=self.child.id,
        )
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            project_tools.create_project(payload)

    def test_create_project_with_steps_and_resources(self) -> None:
        """Steps and resources should materialize as rows; step_index should
        resolve to the real ``ProjectStep.pk`` the loop just created."""
        payload = CreateProjectIn(
            title="Rocket",
            assigned_to_id=self.child.id,
            steps=[
                NewStep(title="Gather", description="Parts"),
                NewStep(title="Assemble", description="Glue pieces"),
                NewStep(title="Launch", description="Countdown"),
            ],
            resources=[
                NewResource(
                    url="https://example.com/overview.mp4",
                    title="Overview",
                    resource_type="video",
                ),  # project-level
                NewResource(
                    url="https://example.com/assemble.mp4",
                    title="Assemble walkthrough",
                    resource_type="video",
                    step_index=1,
                ),
            ],
        )
        with override_user(self.parent):
            result = project_tools.create_project(payload)

        project = Project.objects.get(pk=result["id"])
        steps = list(ProjectStep.objects.filter(project=project).order_by("order"))
        self.assertEqual([s.title for s in steps], ["Gather", "Assemble", "Launch"])

        resources = list(ProjectResource.objects.filter(project=project))
        self.assertEqual(len(resources), 2)
        project_level = [r for r in resources if r.step_id is None]
        step_scoped = [r for r in resources if r.step_id == steps[1].id]
        self.assertEqual(len(project_level), 1)
        self.assertEqual(project_level[0].url, "https://example.com/overview.mp4")
        self.assertEqual(len(step_scoped), 1)
        self.assertEqual(step_scoped[0].url, "https://example.com/assemble.mp4")

    def test_create_project_links_steps_to_milestones_via_index(self) -> None:
        """``milestone_index`` on a NewStep should resolve to the matching
        ``ProjectMilestone.pk`` so steps render under the right phase."""
        payload = CreateProjectIn(
            title="Birdhouse",
            assigned_to_id=self.child.id,
            milestones=[
                NewMilestone(title="Prep"),
                NewMilestone(title="Build"),
            ],
            steps=[
                NewStep(title="Gather", milestone_index=0),
                NewStep(title="Saw", milestone_index=1),
                NewStep(title="Admire", milestone_index=None),
            ],
        )
        with override_user(self.parent):
            result = project_tools.create_project(payload)

        project = Project.objects.get(pk=result["id"])
        prep, build = list(
            ProjectMilestone.objects.filter(project=project).order_by("order")
        )
        steps = {s.title: s for s in ProjectStep.objects.filter(project=project)}
        self.assertEqual(steps["Gather"].milestone_id, prep.id)
        self.assertEqual(steps["Saw"].milestone_id, build.id)
        self.assertIsNone(steps["Admire"].milestone_id)

    def test_create_project_rejects_out_of_range_milestone_index(self) -> None:
        """A ``milestone_index`` outside the milestones list should fail
        validation BEFORE any DB writes — no half-created project."""
        payload = CreateProjectIn(
            title="Bad ms idx",
            assigned_to_id=self.child.id,
            milestones=[NewMilestone(title="only")],
            steps=[NewStep(title="solo", milestone_index=5)],
        )
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            project_tools.create_project(payload)
        self.assertFalse(Project.objects.filter(title="Bad ms idx").exists())

    def test_create_project_rejects_out_of_range_step_index(self) -> None:
        """step_index validation must happen BEFORE any DB writes so a bad
        payload can't half-create a project."""
        payload = CreateProjectIn(
            title="Bad",
            assigned_to_id=self.child.id,
            steps=[NewStep(title="only step")],
            resources=[
                NewResource(url="https://example.com/oops", step_index=5),
            ],
        )
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            project_tools.create_project(payload)
        # No project row should have been created.
        self.assertFalse(Project.objects.filter(title="Bad").exists())


class ListAndGetProjectTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child_a = User.objects.create_user(
            username="a", password="pw", role="child",
        )
        self.child_b = User.objects.create_user(
            username="b", password="pw", role="child",
        )
        self.project_a = Project.objects.create(
            title="A's project",
            created_by=self.parent,
            assigned_to=self.child_a,
            status="active",
        )
        self.project_b = Project.objects.create(
            title="B's project",
            created_by=self.parent,
            assigned_to=self.child_b,
            status="active",
        )

    def test_child_only_sees_own_projects(self) -> None:
        with override_user(self.child_a):
            result = project_tools.list_projects(ListProjectsIn())
        ids = {p["id"] for p in result["projects"]}
        self.assertEqual(ids, {self.project_a.id})

    def test_parent_sees_all_projects(self) -> None:
        with override_user(self.parent):
            result = project_tools.list_projects(ListProjectsIn())
        ids = {p["id"] for p in result["projects"]}
        self.assertEqual(ids, {self.project_a.id, self.project_b.id})

    def test_parent_can_filter_to_one_child(self) -> None:
        with override_user(self.parent):
            result = project_tools.list_projects(
                ListProjectsIn(assigned_to_id=self.child_b.id),
            )
        ids = {p["id"] for p in result["projects"]}
        self.assertEqual(ids, {self.project_b.id})

    def test_child_cannot_get_another_childs_project(self) -> None:
        from apps.mcp_server.errors import MCPNotFoundError
        with override_user(self.child_a), self.assertRaises(MCPNotFoundError):
            project_tools.get_project(GetProjectIn(project_id=self.project_b.id))


class UpdateStatusTests(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p2", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c2", password="pw", role="child",
        )
        self.project = Project.objects.create(
            title="T",
            created_by=self.parent,
            assigned_to=self.child,
            status="active",
        )

    def test_child_cannot_mark_completed(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            project_tools.update_project_status(
                UpdateProjectStatusIn(
                    project_id=self.project.id, status="completed",
                ),
            )

    def test_child_can_move_to_in_review(self) -> None:
        with override_user(self.child):
            result = project_tools.update_project_status(
                UpdateProjectStatusIn(
                    project_id=self.project.id, status="in_review",
                ),
            )
        self.assertEqual(result["status"], "in_review")
