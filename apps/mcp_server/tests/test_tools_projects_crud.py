"""Tests for Tier-1.1 project CRUD MCP tools.

Covers project update/delete/activate/approve/request-changes + nested
milestone/step/material/resource CRUD. Existing ``test_tools_projects.py``
covers the original create/list/get/update-status/complete-milestone
surface.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.achievements.models import MilestoneSkillTag, Skill, Subject
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    AddMaterialIn,
    AddMilestoneIn,
    AddResourceIn,
    AddStepIn,
    DeleteMaterialIn,
    DeleteMilestoneIn,
    DeleteProjectIn,
    DeleteResourceIn,
    DeleteStepIn,
    NewMilestoneSkillTag,
    ProjectActionIn,
    RequestProjectChangesIn,
    StepActionIn,
    UpdateMaterialIn,
    UpdateMilestoneIn,
    UpdateProjectIn,
    UpdateResourceIn,
    UpdateStepIn,
)
from apps.mcp_server.tools import projects as project_tools
from apps.accounts.models import User
from apps.projects.models import (
    MaterialItem,
    Project,
    ProjectMilestone,
    ProjectResource,
    ProjectStep,
)
from apps.achievements.models import SkillCategory


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.category = SkillCategory.objects.create(name="Engineering")
        self.project = Project.objects.create(
            title="Base",
            description="desc",
            created_by=self.parent,
            assigned_to=self.child,
            category=self.category,
            status="active",
        )


class UpdateProjectTests(_Base):
    def test_partial_update_only_changes_provided_fields(self) -> None:
        with override_user(self.parent):
            result = project_tools.update_project(UpdateProjectIn(
                project_id=self.project.id,
                title="Renamed",
                materials_budget=Decimal("42.50"),
            ))
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, "Renamed")
        self.assertEqual(self.project.materials_budget, Decimal("42.50"))
        # Untouched
        self.assertEqual(self.project.description, "desc")

    def test_unknown_assignee_rejected(self) -> None:
        # Unknown assignee now routes through ``resolve_target_user``, which
        # raises ``MCPNotFoundError`` for both "doesn't exist" and
        # "exists but in another family" — same error shape on purpose so
        # the tool can't leak existence of foreign-family users.
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            project_tools.update_project(UpdateProjectIn(
                project_id=self.project.id, assigned_to_id=999999,
            ))

    def test_child_cannot_update(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            project_tools.update_project(UpdateProjectIn(
                project_id=self.project.id, title="Hijacked",
            ))


class DeleteProjectTests(_Base):
    def test_parent_can_delete(self) -> None:
        pid = self.project.id
        with override_user(self.parent):
            result = project_tools.delete_project(DeleteProjectIn(project_id=pid))
        self.assertTrue(result["deleted"])
        self.assertFalse(Project.objects.filter(pk=pid).exists())

    def test_child_cannot_delete(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            project_tools.delete_project(
                DeleteProjectIn(project_id=self.project.id),
            )


class StatusTransitionActionTests(_Base):
    def test_activate_from_draft(self) -> None:
        self.project.status = "draft"
        self.project.save()
        with override_user(self.parent):
            result = project_tools.activate_project(
                ProjectActionIn(project_id=self.project.id),
            )
        self.assertEqual(result["status"], "in_progress")

    def test_activate_rejects_wrong_status(self) -> None:
        # project is 'active', not draft/in_review
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            project_tools.activate_project(
                ProjectActionIn(project_id=self.project.id),
            )

    def test_approve_completes(self) -> None:
        with override_user(self.parent):
            result = project_tools.approve_project(
                ProjectActionIn(project_id=self.project.id),
            )
        self.assertEqual(result["status"], "completed")
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.completed_at)

    def test_request_changes_records_notes(self) -> None:
        with override_user(self.parent):
            project_tools.request_project_changes(RequestProjectChangesIn(
                project_id=self.project.id,
                parent_notes="Please re-measure the brackets.",
            ))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "in_progress")
        self.assertIn("brackets", self.project.parent_notes)


class MilestoneCrudTests(_Base):
    def setUp(self) -> None:
        super().setUp()
        subject = Subject.objects.create(name="Basics", category=self.category)
        self.skill = Skill.objects.create(
            name="Soldering", category=self.category, subject=subject,
        )

    def test_add_milestone_with_skill_tags(self) -> None:
        with override_user(self.parent):
            result = project_tools.add_milestone(AddMilestoneIn(
                project_id=self.project.id,
                title="Wire up the board",
                bonus_amount=Decimal("3.00"),
                skill_tags=[NewMilestoneSkillTag(
                    skill_id=self.skill.id, xp_amount=20,
                )],
            ))
        self.assertEqual(result["title"], "Wire up the board")
        ms = ProjectMilestone.objects.get(pk=result["id"])
        self.assertEqual(
            MilestoneSkillTag.objects.filter(milestone=ms).count(), 1,
        )

    def test_update_milestone_replaces_skill_tags(self) -> None:
        ms = ProjectMilestone.objects.create(
            project=self.project, title="old",
        )
        MilestoneSkillTag.objects.create(
            milestone=ms, skill=self.skill, xp_amount=5,
        )
        with override_user(self.parent):
            project_tools.update_milestone(UpdateMilestoneIn(
                milestone_id=ms.id,
                title="new",
                skill_tags=[],  # explicit empty list replaces the set
            ))
        ms.refresh_from_db()
        self.assertEqual(ms.title, "new")
        self.assertEqual(
            MilestoneSkillTag.objects.filter(milestone=ms).count(), 0,
        )

    def test_delete_milestone_ungroups_steps(self) -> None:
        ms = ProjectMilestone.objects.create(project=self.project, title="x")
        step = ProjectStep.objects.create(
            project=self.project, milestone=ms, title="s",
        )
        with override_user(self.parent):
            project_tools.delete_milestone(DeleteMilestoneIn(milestone_id=ms.id))
        step.refresh_from_db()
        self.assertIsNone(step.milestone_id)  # SET_NULL, not CASCADE

    def test_child_cannot_add_milestone(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            project_tools.add_milestone(AddMilestoneIn(
                project_id=self.project.id, title="x",
            ))


class StepCrudTests(_Base):
    def test_add_step_with_milestone(self) -> None:
        ms = ProjectMilestone.objects.create(project=self.project, title="m")
        with override_user(self.parent):
            result = project_tools.add_step(AddStepIn(
                project_id=self.project.id,
                title="Cut",
                milestone_id=ms.id,
            ))
        self.assertEqual(result["milestone_id"], ms.id)

    def test_add_step_rejects_milestone_on_other_project(self) -> None:
        other = Project.objects.create(
            title="other", created_by=self.parent, assigned_to=self.child,
        )
        other_ms = ProjectMilestone.objects.create(project=other, title="x")
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            project_tools.add_step(AddStepIn(
                project_id=self.project.id,
                title="x",
                milestone_id=other_ms.id,
            ))

    def test_update_step_clear_milestone(self) -> None:
        ms = ProjectMilestone.objects.create(project=self.project, title="m")
        step = ProjectStep.objects.create(
            project=self.project, milestone=ms, title="s",
        )
        with override_user(self.parent):
            result = project_tools.update_step(UpdateStepIn(
                step_id=step.id, clear_milestone=True,
            ))
        self.assertIsNone(result["milestone_id"])

    def test_delete_step(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="s")
        with override_user(self.parent):
            result = project_tools.delete_step(DeleteStepIn(step_id=step.id))
        self.assertTrue(result["deleted"])
        self.assertFalse(ProjectStep.objects.filter(pk=step.id).exists())

    def test_child_can_complete_own_step(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="s")
        with override_user(self.child):
            result = project_tools.complete_step(StepActionIn(step_id=step.id))
        self.assertTrue(result["is_completed"])

    def test_child_cannot_complete_other_child_step(self) -> None:
        other_child = User.objects.create_user(
            username="other", password="pw", role="child",
        )
        step = ProjectStep.objects.create(project=self.project, title="s")
        # Audit C8: child step access is now scoped via the queryset
        # (assignee or collaborator), so a non-member sees NotFound
        # rather than PermissionDenied — closes the existence-leak.
        with override_user(other_child), self.assertRaises(MCPNotFoundError):
            project_tools.complete_step(StepActionIn(step_id=step.id))

    def test_uncomplete_step(self) -> None:
        step = ProjectStep.objects.create(
            project=self.project, title="s", is_completed=True,
        )
        with override_user(self.child):
            result = project_tools.uncomplete_step(StepActionIn(step_id=step.id))
        self.assertFalse(result["is_completed"])


class MaterialCrudTests(_Base):
    def test_add_update_delete_material(self) -> None:
        with override_user(self.parent):
            added = project_tools.add_material(AddMaterialIn(
                project_id=self.project.id,
                name="Wire",
                estimated_cost=Decimal("2.00"),
            ))
            updated = project_tools.update_material(UpdateMaterialIn(
                material_id=added["id"], name="Stranded Wire",
            ))
            deleted = project_tools.delete_material(
                DeleteMaterialIn(material_id=added["id"]),
            )
        self.assertEqual(updated["name"], "Stranded Wire")
        self.assertTrue(deleted["deleted"])
        self.assertFalse(MaterialItem.objects.filter(pk=added["id"]).exists())


class ResourceCrudTests(_Base):
    def test_add_resource_project_level(self) -> None:
        with override_user(self.parent):
            result = project_tools.add_resource(AddResourceIn(
                project_id=self.project.id,
                url="https://example.com/vid.mp4",
                title="Overview",
                resource_type="video",
            ))
        self.assertIsNone(result["step_id"])
        self.assertEqual(result["resource_type"], "video")

    def test_add_resource_step_scoped(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="s")
        with override_user(self.parent):
            result = project_tools.add_resource(AddResourceIn(
                project_id=self.project.id,
                url="https://example.com/a",
                step_id=step.id,
            ))
        self.assertEqual(result["step_id"], step.id)

    def test_update_resource_clear_step_promotes_to_project_level(self) -> None:
        step = ProjectStep.objects.create(project=self.project, title="s")
        res = ProjectResource.objects.create(
            project=self.project, step=step, url="https://x",
        )
        with override_user(self.parent):
            result = project_tools.update_resource(UpdateResourceIn(
                resource_id=res.id, clear_step=True,
            ))
        self.assertIsNone(result["step_id"])

    def test_delete_resource(self) -> None:
        res = ProjectResource.objects.create(
            project=self.project, url="https://x",
        )
        with override_user(self.parent):
            result = project_tools.delete_resource(
                DeleteResourceIn(resource_id=res.id),
            )
        self.assertTrue(result["deleted"])
