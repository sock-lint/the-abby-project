"""Tests for Tier-2.1 skill-tree + badge authoring MCP tools."""
from __future__ import annotations

from django.test import TestCase

from apps.achievements.models import Badge, Skill, SkillPrerequisite, Subject
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    AddSkillPrerequisiteIn,
    CreateBadgeIn,
    CreateCategoryIn,
    CreateSkillIn,
    CreateSubjectIn,
    DeleteBadgeIn,
    DeleteCategoryIn,
    DeleteSkillIn,
    DeleteSubjectIn,
    RemoveSkillPrerequisiteIn,
    SkillPrereqDraft,
    UpdateBadgeIn,
    UpdateCategoryIn,
    UpdateSkillIn,
    UpdateSubjectIn,
)
from apps.mcp_server.tools import achievements as ach
from apps.achievements.models import SkillCategory
from apps.accounts.models import User


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )


class CategoryCrudTests(_Base):
    def test_create_update_delete(self) -> None:
        with override_user(self.parent):
            created = ach.create_category(CreateCategoryIn(
                name="Woodworking", icon="🪵", color="#8B4513",
            ))
            updated = ach.update_category(UpdateCategoryIn(
                category_id=created["id"], icon="🌲",
            ))
            deleted = ach.delete_category(
                DeleteCategoryIn(category_id=created["id"]),
            )
        self.assertEqual(updated["icon"], "🌲")
        self.assertTrue(deleted["deleted"])

    def test_duplicate_name_rejected(self) -> None:
        SkillCategory.objects.create(name="Taken")
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            ach.create_category(CreateCategoryIn(name="Taken"))

    def test_child_cannot_create(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            ach.create_category(CreateCategoryIn(name="Sneaky"))


class SubjectCrudTests(_Base):
    def test_create_subject(self) -> None:
        cat = SkillCategory.objects.create(name="Woodworking")
        with override_user(self.parent):
            r = ach.create_subject(CreateSubjectIn(
                category_id=cat.id, name="Joinery",
            ))
        self.assertEqual(r["category_id"], cat.id)

    def test_duplicate_subject_in_same_category_rejected(self) -> None:
        cat = SkillCategory.objects.create(name="X")
        Subject.objects.create(category=cat, name="Dup")
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            ach.create_subject(CreateSubjectIn(
                category_id=cat.id, name="Dup",
            ))


class SkillCrudTests(_Base):
    def test_create_with_prerequisites(self) -> None:
        cat = SkillCategory.objects.create(name="Math")
        base = Skill.objects.create(name="Addition", category=cat)
        with override_user(self.parent):
            r = ach.create_skill(CreateSkillIn(
                category_id=cat.id,
                name="Subtraction",
                prerequisites=[SkillPrereqDraft(
                    required_skill_id=base.id, required_level=2,
                )],
            ))
        skill = Skill.objects.get(pk=r["id"])
        self.assertEqual(
            SkillPrerequisite.objects.filter(skill=skill).count(), 1,
        )

    def test_update_skill_clear_subject(self) -> None:
        cat = SkillCategory.objects.create(name="C")
        subj = Subject.objects.create(name="S", category=cat)
        skill = Skill.objects.create(name="K", category=cat, subject=subj)
        with override_user(self.parent):
            ach.update_skill(UpdateSkillIn(
                skill_id=skill.id, clear_subject=True,
            ))
        skill.refresh_from_db()
        self.assertIsNone(skill.subject_id)

    def test_add_prerequisite_idempotent(self) -> None:
        cat = SkillCategory.objects.create(name="C")
        a = Skill.objects.create(name="A", category=cat)
        b = Skill.objects.create(name="B", category=cat)
        with override_user(self.parent):
            first = ach.add_skill_prerequisite(AddSkillPrerequisiteIn(
                skill_id=a.id, required_skill_id=b.id, required_level=2,
            ))
            second = ach.add_skill_prerequisite(AddSkillPrerequisiteIn(
                skill_id=a.id, required_skill_id=b.id, required_level=3,
            ))
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(second["required_level"], 3)

    def test_remove_prerequisite(self) -> None:
        cat = SkillCategory.objects.create(name="C")
        a = Skill.objects.create(name="A", category=cat)
        b = Skill.objects.create(name="B", category=cat)
        SkillPrerequisite.objects.create(skill=a, required_skill=b)
        with override_user(self.parent):
            r = ach.remove_skill_prerequisite(RemoveSkillPrerequisiteIn(
                skill_id=a.id, required_skill_id=b.id,
            ))
        self.assertTrue(r["deleted"])

    def test_self_reference_prerequisite_rejected(self) -> None:
        cat = SkillCategory.objects.create(name="C")
        a = Skill.objects.create(name="A", category=cat)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            ach.add_skill_prerequisite(AddSkillPrerequisiteIn(
                skill_id=a.id, required_skill_id=a.id,
            ))

    def test_delete_skill(self) -> None:
        cat = SkillCategory.objects.create(name="C")
        skill = Skill.objects.create(name="S", category=cat)
        with override_user(self.parent):
            r = ach.delete_skill(DeleteSkillIn(skill_id=skill.id))
        self.assertTrue(r["deleted"])


class BadgeCrudTests(_Base):
    def test_create_badge_with_criteria(self) -> None:
        with override_user(self.parent):
            r = ach.create_badge(CreateBadgeIn(
                name="First Project",
                description="Complete your first project.",
                criteria_type="first_project",
                rarity="common",
                xp_bonus=25,
            ))
        badge = Badge.objects.get(pk=r["id"])
        self.assertEqual(badge.criteria_type, "first_project")

    def test_update_badge(self) -> None:
        badge = Badge.objects.create(
            name="B",
            description="d",
            criteria_type="first_project",
        )
        with override_user(self.parent):
            ach.update_badge(UpdateBadgeIn(
                badge_id=badge.id,
                rarity="legendary",
                xp_bonus=100,
            ))
        badge.refresh_from_db()
        self.assertEqual(badge.rarity, "legendary")
        self.assertEqual(badge.xp_bonus, 100)

    def test_delete_badge(self) -> None:
        badge = Badge.objects.create(
            name="Gone", description="", criteria_type="first_clock_in",
        )
        with override_user(self.parent):
            r = ach.delete_badge(DeleteBadgeIn(badge_id=badge.id))
        self.assertTrue(r["deleted"])

    def test_invalid_criteria_type_rejected_at_schema(self) -> None:
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            CreateBadgeIn(
                name="Bad",
                description="",
                criteria_type="not_a_real_type",  # type: ignore[arg-type]
            )
