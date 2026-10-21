"""Positive habits recognize saved milestones independently of their XP pool."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.activity.models import ActivityEvent
from apps.activity.services import ActivityLogService
from apps.habits.models import Habit, HabitLog, HabitSkillTag
from apps.habits.services import HabitService
from apps.quests.models import ChallengeActivity
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(COINS_PER_BADGE_RARITY={"common": 7}, RPG_ASSET_SUPPORT_POLICY=None)
class ZeroXpHabitBadgeAwardsTests(TestCase):
    def setUp(self):
        household = make_family(
            "Zero XP habit milestones", parents=[{"username": "habit-badge-parent"}],
            children=[{"username": "habit-badge-child"}, {"username": "habit-badge-sibling"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.habit = Habit.objects.create(
            user=self.child, created_by=self.parent, name="Daily stretch", xp_reward=0,
        )
        category = SkillCategory.objects.create(name="Synthetic habit skills")
        skill = Skill.objects.create(category=category, name="Consistency")
        self.progress = SkillProgress.objects.create(
            user=self.child, skill=skill, xp_points=100, level=1, unlocked=True,
        )
        HabitSkillTag.objects.create(habit=self.habit, skill=skill)
        self.loot = ItemDefinition.objects.create(
            slug="title-habit-milestone", name="Steady", item_type="cosmetic_title", rarity="uncommon",
        )
        DropTable.objects.create(trigger_type=TriggerType.BADGE_EARNED, item=self.loot, weight=1)

    def badge(self, kind=Badge.CriteriaType.HABIT_MAX_STRENGTH, *, name="Habit milestone", value=None, xp=25):
        return Badge.objects.create(
            name=name, criteria_type=kind, criteria_value=value or {"strength": 1},
            xp_bonus=xp, rarity="common", award_coins=True,
        )

    def assert_one_award(self, badge):
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assertFalse(UserBadge.objects.filter(user=self.sibling).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 125)
        self.assertEqual(CoinService.get_balance(self.child), 7)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").count(), 1)
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type=TriggerType.BADGE_EARNED).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.loot).quantity, 1)

    def test_zero_xp_positive_tap_awards_badge_bonus_and_one_drop_without_habit_xp(self):
        self.habit.skill_tags.all().delete()
        badge = self.badge()
        profile = self.child.character_profile
        before = (profile.login_streak, profile.last_active_date)

        result = HabitService.log_tap(self.child, self.habit, 1)

        self.assertEqual(result, {"direction": 1, "xp_reward": 0, "new_strength": 1})
        self.assert_one_award(badge)
        self.assertFalse(ActivityEvent.objects.filter(subject=self.child, event_type="award.xp").exists())
        self.assertEqual(ChallengeActivity.objects.filter(user=self.child).count(), 1)
        profile.refresh_from_db()
        self.assertEqual((profile.login_streak, profile.last_active_date), before)
        with self.assertRaisesRegex(ValueError, "Daily limit reached"):
            HabitService.log_tap(self.child, self.habit, 1)
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"habit", "badges"}), [])
        self.assert_one_award(badge)

    def test_zero_xp_tap_checks_all_habit_criteria_and_the_badge_meta_scope(self):
        badges = [
            self.badge(name="A strength", xp=0),
            self.badge(Badge.CriteriaType.HABIT_COUNT_AT_STRENGTH, name="B breadth", value={"count": 1, "strength": 1}, xp=0),
            self.badge(Badge.CriteriaType.HABIT_TAPS_LIFETIME, name="C lifetime", value={"count": 1}, xp=0),
            self.badge(Badge.CriteriaType.BADGES_EARNED_COUNT, name="Z collector", value={"count": 3}, xp=0),
        ]

        HabitService.log_tap(self.child, self.habit, 1)

        self.assertSetEqual(set(UserBadge.objects.filter(user=self.child).values_list("badge_id", flat=True)), {badge.pk for badge in badges})
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type=TriggerType.BADGE_EARNED).count(), 4)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)

    def test_negative_and_rejected_taps_never_evaluate_or_award_badges(self):
        # Already eligible criteria make an accidental evaluation observable.
        self.badge(value={"strength": 0})
        self.habit.habit_type = Habit.HabitType.BOTH
        self.habit.strength = 2
        self.habit.save(update_fields=["habit_type", "strength"])
        HabitService.log_tap(self.child, self.habit, -1)
        for changes, direction in [
            ({"is_active": False}, 1),
            ({"is_active": True, "pending_parent_review": True}, 1),
            ({"pending_parent_review": False, "habit_type": Habit.HabitType.NEGATIVE}, 1),
            ({"habit_type": Habit.HabitType.POSITIVE}, -1),
            ({}, 0),
        ]:
            for field, value in changes.items():
                setattr(self.habit, field, value)
            self.habit.save()
            with self.assertRaises(ValueError):
                HabitService.log_tap(self.child, self.habit, direction)

        self.assertEqual(HabitLog.objects.filter(user=self.child).count(), 1)
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(ChallengeActivity.objects.filter(user=self.child).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)

    def test_badge_drop_failure_rolls_back_tap_strength_bonus_and_loot_then_retry_pays_once(self):
        badge = self.badge()
        record = ActivityLogService.record

        def fail_after_drop(*args, **kwargs):
            if kwargs.get("event_type") == "rpg.drop_rolled":
                self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())
                self.assertTrue(DropLog.objects.filter(user=self.child).exists())
                raise RuntimeError("Habit badge drop audit failed")
            return record(*args, **kwargs)

        with patch.object(ActivityLogService, "record", side_effect=fail_after_drop):
            with self.assertRaisesRegex(RuntimeError, "Habit badge drop audit failed"):
                HabitService.log_tap(self.child, self.habit, 1)

        self.habit.refresh_from_db()
        self.progress.refresh_from_db()
        self.assertEqual((self.habit.strength, self.progress.xp_points), (0, 100))
        for model in (HabitLog, UserBadge, DropLog, UserInventory, CoinLedger, ChallengeActivity):
            self.assertFalse(model.objects.filter(user=self.child).exists())
        self.assertFalse(ActivityEvent.objects.filter(subject=self.child).exists())

        HabitService.log_tap(self.child, self.habit, 1)
        self.assert_one_award(badge)
        self.assertEqual(HabitLog.objects.filter(user=self.child, direction=1).count(), 1)
