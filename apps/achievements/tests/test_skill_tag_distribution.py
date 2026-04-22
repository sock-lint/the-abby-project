"""Tests for weighted skill-tag XP distribution across all four entity types.

Added 2026-04-21 when ChoreSkillTag, HabitSkillTag, and QuestSkillTag joined
ProjectSkillTag + HomeworkSkillTag as the five entry points that feed the
skill tree. Pins two invariants:

  1. ``SkillService.distribute_tagged_xp`` splits any pool proportionally
     across tag rows by ``xp_weight``.
  2. Chore approval / habit tap / quest completion each route through
     ``AwardService.grant(xp_tags=...)`` so the XP actually lands in
     ``SkillProgress`` instead of silently dropping.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.achievements.services import AwardService, SkillService
from apps.projects.models import User


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class DistributeTaggedXpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.category = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        self.persistence = Skill.objects.create(
            name="Persistence", category=self.category,
        )
        self.time_mgmt = Skill.objects.create(
            name="Time Management", category=self.category,
        )

    def _tag(self, skill, weight):
        """Build a stand-in tag object that SkillService can consume."""
        class _Tag:
            pass

        t = _Tag()
        t.skill = skill
        t.xp_weight = weight
        return t

    def test_distribute_tagged_xp_splits_by_weight(self):
        tags = [self._tag(self.persistence, 3), self._tag(self.time_mgmt, 1)]
        SkillService.distribute_tagged_xp(self.user, tags, 100)

        p = SkillProgress.objects.get(user=self.user, skill=self.persistence)
        t = SkillProgress.objects.get(user=self.user, skill=self.time_mgmt)
        self.assertEqual(p.xp_points, 75)  # 100 * 3/4
        self.assertEqual(t.xp_points, 25)  # 100 * 1/4

    def test_empty_tags_is_a_noop(self):
        SkillService.distribute_tagged_xp(self.user, [], 100)
        self.assertFalse(SkillProgress.objects.filter(user=self.user).exists())

    def test_zero_total_weight_is_a_noop(self):
        tags = [self._tag(self.persistence, 0)]
        SkillService.distribute_tagged_xp(self.user, tags, 100)
        self.assertFalse(
            SkillProgress.objects.filter(
                user=self.user, skill=self.persistence,
            ).exists()
        )


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class AwardServiceTaggedXpTests(TestCase):
    """Verify AwardService.grant(xp_tags=...) dispatches to the generic path."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.category = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        self.skill = Skill.objects.create(name="Persistence", category=self.category)

    def _tag(self, skill, weight):
        class _Tag:
            pass

        t = _Tag()
        t.skill = skill
        t.xp_weight = weight
        return t

    def test_grant_with_xp_tags_awards_skill_xp(self):
        AwardService.grant(
            self.user,
            xp_tags=[self._tag(self.skill, 1)],
            xp=50,
            xp_source_label="Chore: Dishes",
        )
        progress = SkillProgress.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(progress.xp_points, 50)

    def test_grant_with_empty_xp_tags_awards_nothing(self):
        """Untagged entities still complete without crash — they just
        don't credit the skill tree. This matches pre-2026-04-21
        behaviour for quests and habits."""
        AwardService.grant(
            self.user,
            xp_tags=[],
            xp=50,
            xp_source_label="untagged",
        )
        self.assertFalse(SkillProgress.objects.filter(user=self.user).exists())


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class ChoreApprovalSkillXpTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.category = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        self.skill = Skill.objects.create(name="Persistence", category=self.category)

    def test_tagged_chore_credits_skill_tree_on_approval(self):
        from apps.chores.models import Chore, ChoreCompletion, ChoreSkillTag
        from apps.chores.services import ChoreService
        from django.utils import timezone

        chore = Chore.objects.create(
            title="Dishes", assigned_to=self.child, created_by=self.parent,
            reward_amount=Decimal("0.50"), coin_reward=0, xp_reward=30,
        )
        ChoreSkillTag.objects.create(chore=chore, skill=self.skill, xp_weight=1)
        completion = ChoreCompletion.objects.create(
            chore=chore, user=self.child,
            completed_date=timezone.localdate(),
            reward_amount_snapshot=Decimal("0.50"),
            coin_reward_snapshot=0,
            status=ChoreCompletion.Status.PENDING,
        )

        ChoreService.approve_completion(completion, self.parent)

        progress = SkillProgress.objects.get(user=self.child, skill=self.skill)
        self.assertEqual(progress.xp_points, 30)

    def test_untagged_chore_still_awards_money_and_coins(self):
        """Back-compat: a chore without ChoreSkillTag rows awards no
        skill XP but still completes cleanly — doesn't raise."""
        from apps.chores.models import Chore, ChoreCompletion
        from apps.chores.services import ChoreService
        from django.utils import timezone

        chore = Chore.objects.create(
            title="Clean", assigned_to=self.child, created_by=self.parent,
            reward_amount=Decimal("0.25"), coin_reward=2, xp_reward=10,
        )
        completion = ChoreCompletion.objects.create(
            chore=chore, user=self.child,
            completed_date=timezone.localdate(),
            reward_amount_snapshot=Decimal("0.25"),
            coin_reward_snapshot=2,
            status=ChoreCompletion.Status.PENDING,
        )
        ChoreService.approve_completion(completion, self.parent)
        # No skill-tag rows → no SkillProgress row.
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class HabitTapSkillXpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.category = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        self.skill = Skill.objects.create(name="Persistence", category=self.category)

    def test_positive_tap_credits_skill_tree(self):
        from apps.habits.models import Habit, HabitSkillTag
        from apps.habits.services import HabitService

        habit = Habit.objects.create(
            name="Read 20 min", user=self.user, created_by=self.user,
            xp_reward=10,
        )
        HabitSkillTag.objects.create(habit=habit, skill=self.skill, xp_weight=1)

        HabitService.log_tap(self.user, habit, 1)

        progress = SkillProgress.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(progress.xp_points, 10)

    def test_negative_tap_awards_no_skill_xp(self):
        from apps.habits.models import Habit, HabitSkillTag
        from apps.habits.services import HabitService

        habit = Habit.objects.create(
            name="Screens after 9", user=self.user, created_by=self.user,
            xp_reward=10, habit_type=Habit.HabitType.BOTH,
        )
        HabitSkillTag.objects.create(habit=habit, skill=self.skill, xp_weight=1)

        HabitService.log_tap(self.user, habit, -1)

        self.assertFalse(SkillProgress.objects.filter(user=self.user).exists())


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class QuestCompletionSkillXpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.category = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        self.persistence = Skill.objects.create(
            name="Persistence", category=self.category,
        )
        self.time_mgmt = Skill.objects.create(
            name="Time Management", category=self.category,
        )

    def test_tagged_quest_distributes_xp_on_completion(self):
        from apps.quests.models import (
            Quest, QuestDefinition, QuestParticipant, QuestSkillTag,
        )
        from apps.quests.services import QuestService
        from django.utils import timezone
        from datetime import timedelta

        definition = QuestDefinition.objects.create(
            name="Dragon Slayer", description="",
            quest_type="boss", target_value=100, xp_reward=100, coin_reward=0,
        )
        QuestSkillTag.objects.create(
            quest_definition=definition, skill=self.persistence, xp_weight=3,
        )
        QuestSkillTag.objects.create(
            quest_definition=definition, skill=self.time_mgmt, xp_weight=1,
        )
        quest = Quest.objects.create(
            definition=definition,
            status=Quest.Status.ACTIVE,
            end_date=timezone.now() + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.user)

        QuestService._complete_quest(quest, self.user)

        p = SkillProgress.objects.get(user=self.user, skill=self.persistence)
        t = SkillProgress.objects.get(user=self.user, skill=self.time_mgmt)
        self.assertEqual(p.xp_points, 75)  # 100 * 3/4
        self.assertEqual(t.xp_points, 25)  # 100 * 1/4
