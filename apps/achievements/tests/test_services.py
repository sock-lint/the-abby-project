"""Tests for SkillService and BadgeService business logic."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.achievements.models import (
    XP_THRESHOLDS,
    Badge,
    MilestoneSkillTag,
    ProjectSkillTag,
    Skill,
    SkillPrerequisite,
    SkillProgress,
    Subject,
    UserBadge,
)
from apps.achievements.services import BadgeService, SkillService
from apps.projects.models import Project, ProjectMilestone, SkillCategory, User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="child", password="pw", role="child")
        self.category = SkillCategory.objects.create(name="Woodworking", icon="wood")
        self.subject = Subject.objects.create(name="Measuring", category=self.category)
        self.skill_a = Skill.objects.create(name="Sawing", category=self.category, subject=self.subject)
        self.skill_b = Skill.objects.create(name="Drilling", category=self.category, subject=self.subject)


class LevelForXpTests(_Fixture):
    def test_thresholds(self):
        self.assertEqual(SkillService.level_for_xp(0), 0)
        self.assertEqual(SkillService.level_for_xp(99), 0)
        self.assertEqual(SkillService.level_for_xp(100), 1)
        self.assertEqual(SkillService.level_for_xp(299), 1)
        self.assertEqual(SkillService.level_for_xp(300), 2)
        self.assertEqual(SkillService.level_for_xp(2500), 6)
        # Above max threshold caps at top level.
        self.assertEqual(SkillService.level_for_xp(99_999), 6)


class AwardXpTests(_Fixture):
    def test_creates_progress_on_first_award(self):
        progress = SkillService.award_xp(self.child, self.skill_a, 150)
        self.assertEqual(progress.xp_points, 150)
        self.assertEqual(progress.level, 1)
        self.assertTrue(progress.unlocked)

    def test_adds_to_existing(self):
        SkillService.award_xp(self.child, self.skill_a, 50)
        SkillService.award_xp(self.child, self.skill_a, 60)
        progress = SkillProgress.objects.get(user=self.child, skill=self.skill_a)
        self.assertEqual(progress.xp_points, 110)
        self.assertEqual(progress.level, 1)

    def test_locked_skill_gets_no_xp(self):
        locked = Skill.objects.create(
            name="Advanced Joinery", category=self.category,
            subject=self.subject, is_locked_by_default=True,
        )
        progress = SkillService.award_xp(self.child, locked, 500)
        self.assertFalse(progress.unlocked)
        self.assertEqual(progress.xp_points, 0)


class DistributeProjectXpTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="Birdhouse", created_by=self.parent,
            assigned_to=self.child, difficulty=1,
        )

    def test_weighted_distribution(self):
        ProjectSkillTag.objects.create(project=self.project, skill=self.skill_a, xp_weight=1)
        ProjectSkillTag.objects.create(project=self.project, skill=self.skill_b, xp_weight=3)

        SkillService.distribute_project_xp(self.child, self.project, 400)

        sp_a = SkillProgress.objects.get(user=self.child, skill=self.skill_a)
        sp_b = SkillProgress.objects.get(user=self.child, skill=self.skill_b)
        self.assertEqual(sp_a.xp_points, 100)  # 1/4 of 400
        self.assertEqual(sp_b.xp_points, 300)  # 3/4 of 400

    def test_no_tags_is_noop(self):
        SkillService.distribute_project_xp(self.child, self.project, 100)
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())


class EvaluateUnlocksTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.locked = Skill.objects.create(
            name="Dovetail Joints", category=self.category,
            subject=self.subject, is_locked_by_default=True,
        )
        SkillPrerequisite.objects.create(
            skill=self.locked, required_skill=self.skill_a, required_level=2,
        )

    def test_unlocks_when_prereq_met(self):
        # Drive skill_a to level 2.
        SkillProgress.objects.create(
            user=self.child, skill=self.skill_a, xp_points=300, level=2,
        )
        newly_unlocked = SkillService.evaluate_unlocks(self.child)
        self.assertIn(self.locked, newly_unlocked)
        progress = SkillProgress.objects.get(user=self.child, skill=self.locked)
        self.assertTrue(progress.unlocked)

    def test_stays_locked_when_prereq_below(self):
        SkillProgress.objects.create(
            user=self.child, skill=self.skill_a, xp_points=100, level=1,
        )
        newly_unlocked = SkillService.evaluate_unlocks(self.child)
        self.assertEqual(newly_unlocked, [])


class GetSkillTreeTests(_Fixture):
    def test_nests_skills_under_subjects(self):
        SkillService.award_xp(self.child, self.skill_a, 150)
        tree = SkillService.get_skill_tree(self.child, self.category)
        self.assertEqual(len(tree), 1)
        node = tree[0]
        self.assertEqual(node["name"], "Measuring")
        skill_names = [s["name"] for s in node["skills"]]
        self.assertIn("Sawing", skill_names)
        self.assertIn("Drilling", skill_names)

    def test_orphan_skills_go_to_other(self):
        Skill.objects.create(name="Orphaned", category=self.category)
        tree = SkillService.get_skill_tree(self.child, self.category)
        # Last bucket should be Other.
        self.assertEqual(tree[-1]["name"], "Other")
        self.assertTrue(any(s["name"] == "Orphaned" for s in tree[-1]["skills"]))


class BadgeServiceTests(_Fixture):
    def _make_badge(self, criteria_type, criteria_value, name="Test Badge", rarity="common"):
        return Badge.objects.create(
            name=name, description="d", criteria_type=criteria_type,
            criteria_value=criteria_value, rarity=rarity,
        )

    def test_projects_completed_badge(self):
        badge = self._make_badge("projects_completed", {"count": 1})
        Project.objects.create(
            title="Done", created_by=self.parent, assigned_to=self.child,
            status="completed",
        )
        newly = BadgeService.evaluate_badges(self.child)
        self.assertIn(badge, newly)
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())

    def test_idempotent_no_duplicates(self):
        badge = self._make_badge("projects_completed", {"count": 1})
        Project.objects.create(
            title="Done", created_by=self.parent, assigned_to=self.child,
            status="completed",
        )
        BadgeService.evaluate_badges(self.child)
        BadgeService.evaluate_badges(self.child)
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)

    def test_first_project_badge(self):
        badge = self._make_badge("first_project", {}, name="First Project")
        Project.objects.create(
            title="Hello", created_by=self.parent, assigned_to=self.child,
            status="completed",
        )
        newly = BadgeService.evaluate_badges(self.child)
        self.assertIn(badge, newly)

    def test_skill_level_reached_badge(self):
        badge = self._make_badge("skill_level_reached", {"level": 2}, name="L2 Skill")
        SkillProgress.objects.create(
            user=self.child, skill=self.skill_a, xp_points=300, level=2,
        )
        newly = BadgeService.evaluate_badges(self.child)
        self.assertIn(badge, newly)

    def test_criteria_not_met_awards_nothing(self):
        self._make_badge("projects_completed", {"count": 5})
        newly = BadgeService.evaluate_badges(self.child)
        self.assertEqual(newly, [])

    def test_badge_awards_coins(self):
        from apps.rewards.services import CoinService
        badge = self._make_badge(
            "first_project", {},
            name="Rare Badge", rarity="rare",
        )
        Project.objects.create(
            title="x", created_by=self.parent, assigned_to=self.child,
            status="completed",
        )
        BadgeService.evaluate_badges(self.child)
        # Rare → per COINS_PER_BADGE_RARITY default map, some coins awarded.
        balance = CoinService.get_balance(self.child)
        self.assertGreater(balance, 0)
