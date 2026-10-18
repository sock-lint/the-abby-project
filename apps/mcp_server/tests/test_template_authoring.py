"""Reusable learning plans preserve their authoring and retry boundaries."""
from uuid import uuid4
from unittest.mock import patch

from django.test import TestCase
from pydantic import ValidationError

from apps.achievements.models import (
    MilestoneSkillTag, ProjectSkillTag, Skill, SkillCategory,
)
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPValidationError
from apps.mcp_server.template_schemas import (
    CreateProjectFromTemplateIn, CreateTemplateIn, SaveProjectAsTemplateIn, UpdateTemplateIn,
)
from apps.mcp_server.tools import templates as tools
from apps.projects.models import Project, ProjectMilestone, ProjectTemplate, TemplateAuthoringReceipt
from config.tests.factories import make_family


class TemplateSkillRoundTripTests(TestCase):
    def setUp(self):
        household = make_family(
            "Template family", parents=[{"username": "template-parent"}],
            children=[{"username": "template-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        category = SkillCategory.objects.create(name="Template making")
        self.skill = Skill.objects.create(name="Measuring", category=category)
        self.project = Project.objects.create(
            title="Learning plan", created_by=self.parent, assigned_to=self.child,
        )
        self.milestone = ProjectMilestone.objects.create(
            project=self.project, title="Measure carefully",
        )
        ProjectSkillTag.objects.create(project=self.project, skill=self.skill, xp_weight=3)
        MilestoneSkillTag.objects.create(milestone=self.milestone, skill=self.skill, xp_amount=27)

    def test_template_round_trip_preserves_skill_weights_and_milestone_xp(self):
        with override_user(self.parent):
            template = tools.save_project_as_template(SaveProjectAsTemplateIn(project_id=self.project.pk))
            clone = tools.create_project_from_template(CreateProjectFromTemplateIn(
                template_id=template["id"], assigned_to_id=self.child.pk,
            ))
        project = Project.objects.get(pk=clone["id"])
        self.assertEqual(list(project.skill_tags.values_list("skill_id", "xp_weight")), [(self.skill.pk, 3)])
        self.assertEqual(list(project.milestones.get().skill_tags.values_list("skill_id", "xp_amount")), [(self.skill.pk, 27)])

    def test_create_and_structure_replace_preserve_links_and_skill_wiring(self):
        with override_user(self.parent):
            saved = tools.create_template(CreateTemplateIn(
                title="First", skill_tags=[{"skill_id": self.skill.pk, "xp_weight": 2}],
                milestones=[{"title": "Old milestone"}], steps=[{"title": "Old step", "milestone_index": 0}],
            ))
            edited = tools.update_template(UpdateTemplateIn(
                template_id=saved["id"], title="Revised", skill_tags=[],
                milestones=[{"title": "New milestone", "skill_tags": [{"skill_id": self.skill.pk, "xp_amount": 31}]}],
                materials=[{"name": "Ruler"}], steps=[{"title": "New step", "milestone_index": 0}],
                resources=[{"url": "https://example.com/guide", "step_index": 0}],
            ))
        template = ProjectTemplate.objects.get(pk=saved["id"])
        milestone, step = template.milestones.get(), template.steps.get()
        self.assertEqual((template.title, milestone.title, step.title), ("Revised", "New milestone", "New step"))
        self.assertEqual(step.milestone_id, milestone.pk)
        self.assertEqual(template.resources.get().step_id, step.pk)
        self.assertEqual(edited["skill_tags"], [])
        self.assertEqual(edited["milestones"][0]["skill_tags"], [{"skill_id": self.skill.pk, "xp_amount": 31}])
        self.assertEqual(template.materials.get().name, "Ruler")

    def test_structural_failure_rolls_back_metadata_and_deleted_content(self):
        with override_user(self.parent):
            saved = tools.create_template(CreateTemplateIn(title="Original", milestones=[{"title": "Keep me"}]))
            with patch("apps.mcp_server.tools.templates._write_structure", side_effect=RuntimeError("synthetic failed write")):
                with self.assertRaises(RuntimeError):
                    tools.update_template(UpdateTemplateIn(
                        template_id=saved["id"], title="Wrong", milestones=[], materials=[], steps=[], resources=[],
                    ))
        template = ProjectTemplate.objects.get(pk=saved["id"])
        self.assertEqual(template.title, "Original")
        self.assertEqual(template.milestones.get().title, "Keep me")

    def test_structural_arrays_must_be_complete_and_indices_valid(self):
        with self.assertRaises(ValidationError):
            UpdateTemplateIn(template_id=1, milestones=[])
        with override_user(self.parent):
            with self.assertRaises(MCPValidationError):
                tools.create_template(CreateTemplateIn(title="Invalid", steps=[{"title": "Bad link", "milestone_index": 9}]))
        self.assertFalse(ProjectTemplate.objects.exists())

    def test_invalid_and_duplicate_skill_ids_leave_no_template(self):
        for tags in ([{"skill_id": 999999}], [{"skill_id": self.skill.pk}, {"skill_id": self.skill.pk}]):
            with override_user(self.parent), self.assertRaises(MCPValidationError):
                tools.create_template(CreateTemplateIn(title="Invalid", skill_tags=tags))
        self.assertFalse(ProjectTemplate.objects.exists())

    def test_create_retry_returns_original_response_after_template_changes_or_deletion(self):
        params = CreateTemplateIn(title="Retry safe", request_id=uuid4())
        with override_user(self.parent):
            original = tools.create_template(params)
            ProjectTemplate.objects.filter(pk=original["id"]).update(title="Changed later")
            self.assertEqual(tools.create_template(params), original)
            ProjectTemplate.objects.get(pk=original["id"]).delete()
            self.assertEqual(tools.create_template(params), original)
            with self.assertRaises(MCPValidationError):
                tools.create_template(CreateTemplateIn(title="Different", request_id=params.request_id))
        self.assertEqual(TemplateAuthoringReceipt.objects.count(), 1)
        self.assertFalse(ProjectTemplate.objects.exists())

    def test_save_and_draft_instantiation_are_duplicate_safe(self):
        save = SaveProjectAsTemplateIn(project_id=self.project.pk, request_id=uuid4())
        with override_user(self.parent):
            template = tools.save_project_as_template(save)
            self.assertEqual(tools.save_project_as_template(save), template)
            request = CreateProjectFromTemplateIn(template_id=template["id"], assigned_to_id=self.child.pk, status="draft", request_id=uuid4())
            project = tools.create_project_from_template(request)
            Project.objects.filter(pk=project["id"]).update(title="Later edit")
            self.assertEqual(tools.create_project_from_template(request), project)
            with self.assertRaises(MCPValidationError):
                tools.create_project_from_template(request.model_copy(update={"status": "in_progress"}))
        self.assertEqual(project["status"], "draft")
        self.assertEqual(Project.objects.count(), 2)
        self.assertEqual(ProjectTemplate.objects.count(), 1)

    def test_cross_family_creation_and_replacement_are_hidden(self):
        other = make_family("Other template family", parents=[{"username": "other-template-parent"}], children=[{"username": "other-template-child"}])
        with override_user(self.parent):
            saved = tools.create_template(CreateTemplateIn(title="Private"))
            with self.assertRaises(MCPNotFoundError):
                tools.create_project_from_template(CreateProjectFromTemplateIn(template_id=saved["id"], assigned_to_id=other.children[0].pk))
            with self.assertRaises(MCPValidationError):
                tools.create_project_from_template(CreateProjectFromTemplateIn(template_id=saved["id"], assigned_to_id=self.parent.pk))
        with override_user(other.parents[0]), self.assertRaises(MCPNotFoundError):
            tools.update_template(UpdateTemplateIn(template_id=saved["id"], title="Intrusion"))
        self.assertEqual(ProjectTemplate.objects.get(pk=saved["id"]).title, "Private")

    def test_authoring_rejects_negative_or_overprecision_costs_before_writes(self):
        for payload in ({"bonus_amount": "-1.00"}, {"materials_budget": "1000000.00"}, {"materials": [{"name": "Ruler", "estimated_cost": "0.001"}]}):
            with self.assertRaises(ValidationError):
                CreateTemplateIn(title="Bad price", **payload)
        self.assertFalse(ProjectTemplate.objects.exists())
