"""Cross-family scoping for MCP tools that accept ``assigned_to_id``.

Pinned because four tools used raw ``User.objects.get(pk=...)`` to resolve
``assigned_to_id`` without a family check — a parent could create a project,
update one, spawn one from a template, or commit an ingestion job assigned
to another family's child. All four now route through ``resolve_target_user``.
"""
from __future__ import annotations

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError
from apps.mcp_server.schemas import (
    CreateProjectFromTemplateIn,
    CreateProjectIn,
    UpdateProjectIn,
)
from apps.mcp_server.tools import projects as project_tools
from apps.mcp_server.tools import templates as template_tools
from apps.projects.models import Project, ProjectTemplate
from config.tests.factories import make_family


class _FamilyFixture(TestCase):
    def setUp(self):
        self.a = make_family(
            "A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "B",
            parents=[{"username": "bp"}],
            children=[{"username": "bc"}],
        )


class CreateProjectCrossFamilyTests(_FamilyFixture):
    def test_create_project_for_own_child_succeeds(self):
        with override_user(self.a.parents[0]):
            result = project_tools.create_project(
                CreateProjectIn(
                    title="Birdhouse",
                    assigned_to_id=self.a.children[0].id,
                ),
            )
        self.assertIn("id", result)
        self.assertTrue(Project.objects.filter(pk=result["id"]).exists())

    def test_create_project_for_foreign_child_raises_not_found(self):
        with override_user(self.a.parents[0]):
            with self.assertRaises(MCPNotFoundError):
                project_tools.create_project(
                    CreateProjectIn(
                        title="Sneaky",
                        assigned_to_id=self.b.children[0].id,
                    ),
                )
        self.assertFalse(Project.objects.filter(title="Sneaky").exists())


class UpdateProjectCrossFamilyTests(_FamilyFixture):
    def test_update_assigned_to_foreign_child_raises_not_found(self):
        project = Project.objects.create(
            title="P", assigned_to=self.a.children[0],
            created_by=self.a.parents[0],
        )
        with override_user(self.a.parents[0]):
            with self.assertRaises(MCPNotFoundError):
                project_tools.update_project(
                    UpdateProjectIn(
                        project_id=project.id,
                        assigned_to_id=self.b.children[0].id,
                    ),
                )
        project.refresh_from_db()
        self.assertEqual(project.assigned_to_id, self.a.children[0].id)


class CreateProjectFromTemplateCrossFamilyTests(_FamilyFixture):
    def test_template_to_foreign_child_raises_not_found(self):
        template = ProjectTemplate.objects.create(
            title="Tpl", description="x", difficulty=2,
            created_by=self.a.parents[0], family=self.a.family,
        )
        with override_user(self.a.parents[0]):
            with self.assertRaises(MCPNotFoundError):
                template_tools.create_project_from_template(
                    CreateProjectFromTemplateIn(
                        template_id=template.id,
                        assigned_to_id=self.b.children[0].id,
                    ),
                )
        self.assertFalse(Project.objects.filter(title="Tpl").exists())
