"""Tests for the 2026-04-23 content-review badge criteria.

Covers the 8 new criterion checkers:

- ``_habit_taps_lifetime`` — cumulative positive habit taps
- ``_habit_count_at_strength`` — N habits at ≥ strength S
- ``_badges_earned_count`` — universal badge-collector ladder
- ``_co_op_project_completed`` — completed collaborative projects
- ``_boss_quests_completed`` / ``_collection_quests_completed`` — quest subtype ladders
- ``_chronicle_milestones_logged`` — Chronicle MILESTONE-kind entries
- ``_cosmetic_set_owned`` — owning every slug in a named cosmetic set

Plus a regression test for the ``_category_mastery`` fix: locked-by-default
skills no longer count toward category-mastery requirements.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings

CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

from apps.achievements.criteria import (
    _badges_earned_count,
    _category_mastery,
    _chronicle_milestones_logged,
    _co_op_project_completed,
    _collection_quests_completed,
    _cosmetic_set_owned,
    _boss_quests_completed,
    _habit_count_at_strength,
    _habit_taps_lifetime,
)
from apps.projects.models import User


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class HabitCriteriaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def test_habit_taps_lifetime_counts_positive_only(self):
        from apps.habits.models import Habit, HabitLog

        habit = Habit.objects.create(
            user=self.user, created_by=self.user, name="Read", strength=0,
        )
        for _ in range(3):
            HabitLog.objects.create(habit=habit, user=self.user, direction=1)
        # Negative taps must NOT count.
        HabitLog.objects.create(habit=habit, user=self.user, direction=-1)
        HabitLog.objects.create(habit=habit, user=self.user, direction=-1)

        self.assertTrue(_habit_taps_lifetime(self.user, {"count": 3}))
        self.assertFalse(_habit_taps_lifetime(self.user, {"count": 4}))

    def test_habit_count_at_strength_uses_active_habits(self):
        from apps.habits.models import Habit

        Habit.objects.create(
            user=self.user, created_by=self.user, name="A", strength=5, is_active=True,
        )
        Habit.objects.create(
            user=self.user, created_by=self.user, name="B", strength=6, is_active=True,
        )
        # Below threshold — does not count.
        Habit.objects.create(
            user=self.user, created_by=self.user, name="C", strength=3, is_active=True,
        )
        # Inactive — does not count even at +10.
        Habit.objects.create(
            user=self.user, created_by=self.user, name="D", strength=10, is_active=False,
        )

        self.assertTrue(_habit_count_at_strength(self.user, {"count": 2, "strength": 5}))
        self.assertFalse(_habit_count_at_strength(self.user, {"count": 3, "strength": 5}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class BadgesEarnedCountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def test_badges_earned_count_tracks_userbadge_rows(self):
        from apps.achievements.models import Badge, UserBadge

        self.assertFalse(_badges_earned_count(self.user, {"count": 1}))
        for i in range(3):
            badge = Badge.objects.create(
                name=f"Test Badge {i}",
                description="x",
                criteria_type=Badge.CriteriaType.FIRST_PROJECT,
            )
            UserBadge.objects.create(user=self.user, badge=badge)
        self.assertTrue(_badges_earned_count(self.user, {"count": 3}))
        self.assertFalse(_badges_earned_count(self.user, {"count": 4}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class CoOpProjectCriteriaTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.owner = User.objects.create_user(
            username="owner", password="pw", role="child",
        )
        self.helper = User.objects.create_user(
            username="helper", password="pw", role="child",
        )

    def test_co_op_project_completed_counts_collab_rows(self):
        from apps.projects.models import Project, ProjectCollaborator

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            project = Project.objects.create(
                title="Shared Project",
                description="desc",
                assigned_to=self.owner,
                created_by=self.parent,
                status=Project.Status.COMPLETED,
            )
        ProjectCollaborator.objects.create(project=project, user=self.helper)

        self.assertTrue(_co_op_project_completed(self.helper, {"count": 1}))
        # Owner (assigned_to) is NOT counted as a co-op participant.
        self.assertFalse(_co_op_project_completed(self.owner, {"count": 1}))

    def test_co_op_ignores_non_completed_projects(self):
        from apps.projects.models import Project, ProjectCollaborator

        project = Project.objects.create(
            title="WIP Project",
            description="desc",
            assigned_to=self.owner,
            created_by=self.parent,
            status=Project.Status.IN_PROGRESS,
        )
        ProjectCollaborator.objects.create(project=project, user=self.helper)
        self.assertFalse(_co_op_project_completed(self.helper, {"count": 1}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class QuestSubtypeCriteriaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def _complete_quest(self, name, *, quest_type):
        from django.utils import timezone
        from apps.quests.models import Quest, QuestDefinition, QuestParticipant

        defn = QuestDefinition.objects.create(
            name=name, description=name, quest_type=quest_type,
            target_value=100, duration_days=7,
        )
        quest = Quest.objects.create(
            definition=defn, status=Quest.Status.COMPLETED,
            end_date=timezone.now() + timezone.timedelta(days=1),
        )
        QuestParticipant.objects.create(quest=quest, user=self.user)
        return quest

    def test_boss_quests_completed_filters_by_type(self):
        from apps.quests.models import QuestDefinition

        self._complete_quest("Dragon", quest_type=QuestDefinition.QuestType.BOSS)
        self._complete_quest("Collection A", quest_type=QuestDefinition.QuestType.COLLECTION)
        self._complete_quest("Collection B", quest_type=QuestDefinition.QuestType.COLLECTION)

        self.assertTrue(_boss_quests_completed(self.user, {"count": 1}))
        self.assertFalse(_boss_quests_completed(self.user, {"count": 2}))
        self.assertTrue(_collection_quests_completed(self.user, {"count": 2}))
        self.assertFalse(_collection_quests_completed(self.user, {"count": 3}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ChronicleMilestonesCriterionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def test_chronicle_milestones_logged_counts_milestone_kind_only(self):
        from apps.chronicle.models import ChronicleEntry

        ChronicleEntry.objects.create(
            user=self.user, kind=ChronicleEntry.Kind.MILESTONE,
            occurred_on=date(2025, 6, 1), chapter_year=2024,
            title="Graduated",
        )
        ChronicleEntry.objects.create(
            user=self.user, kind=ChronicleEntry.Kind.MILESTONE,
            occurred_on=date(2026, 6, 1), chapter_year=2025,
            title="Another milestone",
        )
        # Different kind — must NOT count.
        ChronicleEntry.objects.create(
            user=self.user, kind=ChronicleEntry.Kind.BIRTHDAY,
            occurred_on=date(2026, 4, 1), chapter_year=2025,
            title="Birthday",
        )

        self.assertTrue(_chronicle_milestones_logged(self.user, {"count": 2}))
        self.assertFalse(_chronicle_milestones_logged(self.user, {"count": 3}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class CosmeticSetOwnedCriterionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def _make_cosmetic(self, slug, item_type):
        from apps.rpg.models import ItemDefinition
        return ItemDefinition.objects.create(
            slug=slug, name=slug, icon="x", item_type=item_type,
        )

    def test_cosmetic_set_owned_requires_every_slug(self):
        from apps.rpg.models import ItemDefinition, UserInventory

        frame = self._make_cosmetic("frame-scholar", ItemDefinition.ItemType.COSMETIC_FRAME)
        title = self._make_cosmetic("title-scholar", ItemDefinition.ItemType.COSMETIC_TITLE)
        theme = self._make_cosmetic("theme-library", ItemDefinition.ItemType.COSMETIC_THEME)

        UserInventory.objects.create(user=self.user, item=frame, quantity=1)
        UserInventory.objects.create(user=self.user, item=title, quantity=1)
        # Missing theme — must not satisfy.
        self.assertFalse(_cosmetic_set_owned(
            self.user,
            {"slugs": ["frame-scholar", "title-scholar", "theme-library"]},
        ))

        UserInventory.objects.create(user=self.user, item=theme, quantity=1)
        self.assertTrue(_cosmetic_set_owned(
            self.user,
            {"slugs": ["frame-scholar", "title-scholar", "theme-library"]},
        ))

    def test_cosmetic_set_owned_false_on_empty_slugs(self):
        self.assertFalse(_cosmetic_set_owned(self.user, {}))
        self.assertFalse(_cosmetic_set_owned(self.user, {"slugs": []}))


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class CategoryMasteryUnlockedFixTests(TestCase):
    """Regression: _category_mastery now excludes locked-by-default skills."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )

    def test_locked_by_default_skills_do_not_block(self):
        from apps.achievements.models import Skill, SkillCategory, SkillProgress

        cat = SkillCategory.objects.create(name="Life Skills")
        unlocked_a = Skill.objects.create(
            category=cat, name="Budgeting", is_locked_by_default=False,
        )
        unlocked_b = Skill.objects.create(
            category=cat, name="Planning", is_locked_by_default=False,
        )
        # This one is age-gated — must NOT block the badge.
        Skill.objects.create(
            category=cat, name="Driving", is_locked_by_default=True,
        )

        SkillProgress.objects.create(user=self.user, skill=unlocked_a, level=3)
        SkillProgress.objects.create(user=self.user, skill=unlocked_b, level=3)

        # Even without a Driving progress row, category mastery passes.
        self.assertTrue(_category_mastery(
            self.user, {"category": "Life Skills", "min_level": 3},
        ))
