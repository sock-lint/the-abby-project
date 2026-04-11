"""Tests for project-related MCP tools."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.mcp_server.schemas import (
    CreateProjectIn,
    GetProjectIn,
    ListProjectsIn,
    NewMilestone,
    NewProjectSkillTag,
    UpdateProjectStatusIn,
)
from apps.mcp_server.tools import projects as project_tools
from apps.projects.models import Project, SkillCategory, User
from apps.achievements.models import ProjectSkillTag, Skill, Subject


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
