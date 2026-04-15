"""Tests for Tier-1.4 homework CRUD + templates + AI planning MCP tools."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.achievements.models import Skill, Subject
from apps.homework.models import (
    HomeworkAssignment,
    HomeworkSkillTag,
    HomeworkTemplate,
)
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    CreateHomeworkFromTemplateIn,
    CreateHomeworkTemplateIn,
    DeleteHomeworkIn,
    DeleteHomeworkTemplateIn,
    GetHomeworkTemplateIn,
    HomeworkSkillTagDraft,
    ListHomeworkTemplatesIn,
    PlanHomeworkIn,
    SetHomeworkSkillTagsIn,
    UpdateHomeworkIn,
    UpdateHomeworkTemplateIn,
)
from apps.mcp_server.tools import homework as hw
from apps.projects.models import SkillCategory, User


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        cat = SkillCategory.objects.create(name="Academics")
        subj = Subject.objects.create(name="Math", category=cat)
        self.skill = Skill.objects.create(
            name="Arithmetic", category=cat, subject=subj,
        )
        self.assignment = HomeworkAssignment.objects.create(
            title="Page 5-7",
            subject="math",
            effort_level=2,
            due_date=date.today() + timedelta(days=3),
            assigned_to=self.child,
            created_by=self.parent,
            reward_amount=Decimal("1.50"),
            coin_reward=10,
        )


class UpdateHomeworkTests(_Base):
    def test_partial_update(self) -> None:
        with override_user(self.parent):
            hw.update_homework(UpdateHomeworkIn(
                assignment_id=self.assignment.id,
                effort_level=5,
                coin_reward=50,
            ))
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.effort_level, 5)
        self.assertEqual(self.assignment.coin_reward, 50)

    def test_child_cannot_update(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            hw.update_homework(UpdateHomeworkIn(
                assignment_id=self.assignment.id, effort_level=5,
            ))


class DeleteHomeworkTests(_Base):
    def test_soft_delete(self) -> None:
        with override_user(self.parent):
            result = hw.delete_homework(DeleteHomeworkIn(
                assignment_id=self.assignment.id,
            ))
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_active)
        self.assertTrue(result["deleted"])


class SetSkillTagsTests(_Base):
    def test_replace_tags(self) -> None:
        with override_user(self.parent):
            hw.set_homework_skill_tags(SetHomeworkSkillTagsIn(
                assignment_id=self.assignment.id,
                skill_tags=[HomeworkSkillTagDraft(
                    skill_id=self.skill.id, xp_amount=25,
                )],
            ))
        self.assertEqual(
            HomeworkSkillTag.objects.filter(
                assignment=self.assignment,
            ).count(), 1,
        )

    def test_unknown_skill_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            hw.set_homework_skill_tags(SetHomeworkSkillTagsIn(
                assignment_id=self.assignment.id,
                skill_tags=[HomeworkSkillTagDraft(skill_id=999999)],
            ))


class PlanHomeworkTests(_Base):
    def test_plan_refuses_when_already_linked(self) -> None:
        from apps.projects.models import Project
        project = Project.objects.create(
            title="linked", created_by=self.parent, assigned_to=self.child,
        )
        self.assignment.project = project
        self.assignment.save()
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            hw.plan_homework(PlanHomeworkIn(
                assignment_id=self.assignment.id,
            ))

    def test_plan_raises_not_configured(self) -> None:
        # HomeworkService has no plan_assignment method today.
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            hw.plan_homework(PlanHomeworkIn(
                assignment_id=self.assignment.id,
            ))


class TemplateCrudTests(_Base):
    def test_create_and_list(self) -> None:
        with override_user(self.parent):
            r = hw.create_homework_template(CreateHomeworkTemplateIn(
                title="Math drill",
                subject="math",
                effort_level=3,
                skill_tags=[HomeworkSkillTagDraft(skill_id=self.skill.id)],
            ))
            listed = hw.list_homework_templates(
                ListHomeworkTemplatesIn(),
            )
        self.assertEqual(r["title"], "Math drill")
        self.assertEqual(listed["count"], 1)

    def test_update_template(self) -> None:
        tpl = HomeworkTemplate.objects.create(
            title="orig", subject="math", created_by=self.parent,
        )
        with override_user(self.parent):
            r = hw.update_homework_template(UpdateHomeworkTemplateIn(
                template_id=tpl.id, title="renamed", effort_level=4,
            ))
        tpl.refresh_from_db()
        self.assertEqual(tpl.title, "renamed")
        self.assertEqual(tpl.effort_level, 4)

    def test_delete_template(self) -> None:
        tpl = HomeworkTemplate.objects.create(
            title="t", subject="math", created_by=self.parent,
        )
        with override_user(self.parent):
            r = hw.delete_homework_template(
                DeleteHomeworkTemplateIn(template_id=tpl.id),
            )
        self.assertTrue(r["deleted"])

    def test_other_parents_template_hidden(self) -> None:
        other = User.objects.create_user(
            username="p2", password="pw", role="parent",
        )
        tpl = HomeworkTemplate.objects.create(
            title="t", subject="math", created_by=other,
        )
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            hw.get_homework_template(GetHomeworkTemplateIn(template_id=tpl.id))

    def test_create_from_template_spawns_assignment(self) -> None:
        tpl = HomeworkTemplate.objects.create(
            title="Page drill",
            subject="math",
            effort_level=3,
            reward_amount=Decimal("2.00"),
            coin_reward=15,
            created_by=self.parent,
            skill_tags=[{"skill_id": self.skill.id, "xp_amount": 20}],
        )
        with override_user(self.parent):
            result = hw.create_homework_from_template(
                CreateHomeworkFromTemplateIn(
                    template_id=tpl.id,
                    assigned_to_id=self.child.id,
                    due_date=date.today() + timedelta(days=2),
                ),
            )
        assignment = HomeworkAssignment.objects.get(pk=result["id"])
        self.assertEqual(assignment.title, "Page drill")
        self.assertEqual(assignment.assigned_to, self.child)
        self.assertEqual(
            HomeworkSkillTag.objects.filter(assignment=assignment).count(), 1,
        )
