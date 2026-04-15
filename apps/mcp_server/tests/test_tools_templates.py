"""Tests for Tier-1.2 project template MCP tools."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    CreateProjectFromTemplateIn,
    CreateTemplateIn,
    DeleteTemplateIn,
    GetTemplateIn,
    ListTemplatesIn,
    SaveProjectAsTemplateIn,
    TemplateMaterialDraft,
    TemplateMilestoneDraft,
    TemplateResourceDraft,
    TemplateStepDraft,
    UpdateTemplateIn,
)
from apps.mcp_server.tools import templates as t
from apps.accounts.models import User
from apps.projects.models import (
    MaterialItem,
    Project,
    ProjectMilestone,
    ProjectResource,
    ProjectStep,
    ProjectTemplate,
    TemplateMilestone,
    TemplateResource,
    TemplateStep,
)


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )


class CreateAndReadTemplateTests(_Base):
    def test_create_with_nested_indexes(self) -> None:
        with override_user(self.parent):
            result = t.create_template(CreateTemplateIn(
                title="Birdhouse",
                milestones=[
                    TemplateMilestoneDraft(title="Cut"),
                    TemplateMilestoneDraft(title="Assemble"),
                ],
                materials=[TemplateMaterialDraft(name="Pine", estimated_cost=Decimal("8.50"))],
                steps=[
                    TemplateStepDraft(title="Measure", milestone_index=0),
                    TemplateStepDraft(title="Glue", milestone_index=1),
                ],
                resources=[
                    TemplateResourceDraft(
                        url="https://example.com/a", step_index=1,
                    ),
                ],
            ))
        template_id = result["id"]
        self.assertEqual(
            TemplateMilestone.objects.filter(template_id=template_id).count(), 2,
        )
        # Step correctly links to its milestone
        step = TemplateStep.objects.get(
            template_id=template_id, title="Glue",
        )
        self.assertIsNotNone(step.milestone_id)
        # Resource correctly links to the "Glue" step
        res = TemplateResource.objects.get(template_id=template_id)
        self.assertEqual(res.step_id, step.id)

    def test_create_rejects_bad_milestone_index(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            t.create_template(CreateTemplateIn(
                title="Bad",
                milestones=[TemplateMilestoneDraft(title="only")],
                steps=[TemplateStepDraft(title="x", milestone_index=5)],
            ))

    def test_child_cannot_create(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            t.create_template(CreateTemplateIn(title="X"))

    def test_list_parent_sees_all_child_sees_public_only(self) -> None:
        pub = ProjectTemplate.objects.create(
            title="Public", created_by=self.parent, is_public=True,
        )
        priv = ProjectTemplate.objects.create(
            title="Private", created_by=self.parent, is_public=False,
        )
        with override_user(self.parent):
            r = t.list_templates(ListTemplatesIn())
        ids = {x["id"] for x in r["templates"]}
        self.assertEqual(ids, {pub.id, priv.id})
        with override_user(self.child):
            r = t.list_templates(ListTemplatesIn())
        ids = {x["id"] for x in r["templates"]}
        self.assertEqual(ids, {pub.id})

    def test_get_private_template_hidden_from_child(self) -> None:
        priv = ProjectTemplate.objects.create(
            title="P", created_by=self.parent, is_public=False,
        )
        with override_user(self.child), self.assertRaises(MCPNotFoundError):
            t.get_template(GetTemplateIn(template_id=priv.id))


class UpdateAndDeleteTemplateTests(_Base):
    def test_update_template_partial(self) -> None:
        tpl = ProjectTemplate.objects.create(
            title="Orig", created_by=self.parent,
        )
        with override_user(self.parent):
            r = t.update_template(UpdateTemplateIn(
                template_id=tpl.id, title="New", is_public=True,
            ))
        tpl.refresh_from_db()
        self.assertEqual(tpl.title, "New")
        self.assertTrue(tpl.is_public)

    def test_delete_template(self) -> None:
        tpl = ProjectTemplate.objects.create(
            title="X", created_by=self.parent,
        )
        with override_user(self.parent):
            r = t.delete_template(DeleteTemplateIn(template_id=tpl.id))
        self.assertTrue(r["deleted"])
        self.assertFalse(ProjectTemplate.objects.filter(pk=tpl.id).exists())


class CloneRoundTripTests(_Base):
    def test_save_project_as_template_then_create_back(self) -> None:
        # Source project with milestones + steps + materials + resources
        project = Project.objects.create(
            title="Source",
            created_by=self.parent,
            assigned_to=self.child,
            status="completed",
        )
        ms1 = ProjectMilestone.objects.create(project=project, title="M1")
        ProjectMilestone.objects.create(project=project, title="M2")
        ProjectStep.objects.create(project=project, milestone=ms1, title="S1")
        ProjectStep.objects.create(project=project, title="S-loose")
        MaterialItem.objects.create(project=project, name="Wood")
        ProjectResource.objects.create(
            project=project, url="https://x", title="overview",
        )
        with override_user(self.parent):
            tpl_dict = t.save_project_as_template(
                SaveProjectAsTemplateIn(project_id=project.id, is_public=True),
            )
            new_project = t.create_project_from_template(
                CreateProjectFromTemplateIn(
                    template_id=tpl_dict["id"],
                    assigned_to_id=self.child.id,
                    title_override="Clone for Abby",
                ),
            )
        # Shape survived the round-trip.
        self.assertEqual(new_project["title"], "Clone for Abby")
        pid = new_project["id"]
        self.assertEqual(
            ProjectMilestone.objects.filter(project_id=pid).count(), 2,
        )
        self.assertEqual(
            ProjectStep.objects.filter(project_id=pid).count(), 2,
        )
        self.assertEqual(
            MaterialItem.objects.filter(project_id=pid).count(), 1,
        )
        # Step→milestone link preserved
        grouped_step = ProjectStep.objects.get(project_id=pid, title="S1")
        self.assertIsNotNone(grouped_step.milestone_id)
        loose_step = ProjectStep.objects.get(project_id=pid, title="S-loose")
        self.assertIsNone(loose_step.milestone_id)

    def test_create_project_from_template_requires_parent(self) -> None:
        tpl = ProjectTemplate.objects.create(
            title="T", created_by=self.parent, is_public=True,
        )
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            t.create_project_from_template(
                CreateProjectFromTemplateIn(
                    template_id=tpl.id, assigned_to_id=self.child.id,
                ),
            )
