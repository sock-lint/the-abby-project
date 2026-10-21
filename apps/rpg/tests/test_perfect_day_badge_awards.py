"""Perfect Day recognizes its badges in the same once-only daily transaction."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.activity.models import ActivityEvent
from apps.chores.models import Chore, ChoreCompletion
from apps.notifications.models import Notification
from apps.quests.models import ChallengeActivity, DailyChallenge
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, PerfectDayReceipt, UserInventory
from apps.rpg.tasks import evaluate_perfect_day_task
from config.tests.factories import make_family


@override_settings(COINS_PER_BADGE_RARITY={"common": 7}, RPG_ASSET_SUPPORT_POLICY=None)
class PerfectDayBadgeAwardsTests(TestCase):
    def setUp(self):
        household = make_family(
            "Perfect Day badge household", parents=[{"username": "pd-badge-parent"}],
            children=[{"username": "pd-badge-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.day = timezone.localdate(timezone=timezone.get_default_timezone())
        self.profile = self.child.character_profile
        self.profile.last_active_date = self.day
        self.profile.login_streak = 7
        self.profile.save(update_fields=["last_active_date", "login_streak"])
        chore = Chore.objects.create(
            family=household.family, title="Make the bed", created_by=self.parent,
            assigned_to=self.child, recurrence=Chore.Recurrence.DAILY,
        )
        self.completion = ChoreCompletion.objects.create(
            chore=chore, user=self.child, completed_date=self.day,
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=0, coin_reward_snapshot=0,
        )
        category = SkillCategory.objects.create(name="Synthetic Perfect Day skills")
        skill = Skill.objects.create(category=category, name="Planning")
        self.progress = SkillProgress.objects.create(user=self.child, skill=skill, xp_points=100, level=1, unlocked=True)
        self.badge = Badge.objects.create(
            name="A first Perfect Day", criteria_type=Badge.CriteriaType.PERFECT_DAYS_COUNT,
            criteria_value={"count": 1}, xp_bonus=25, rarity="common", award_coins=True,
        )
        self.loot = {}
        for trigger, slug, item_type in (
            (TriggerType.PERFECT_DAY, "frame-perfect-day", "cosmetic_frame"),
            (TriggerType.BADGE_EARNED, "title-perfect-day-badge", "cosmetic_title"),
        ):
            item = ItemDefinition.objects.create(slug=slug, name=slug, item_type=item_type, rarity="uncommon")
            self.loot[trigger] = item
            DropTable.objects.create(trigger_type=trigger, item=item, weight=1)

    def assert_awarded_once(self):
        self.profile.refresh_from_db()
        self.progress.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assertEqual(self.profile.login_streak, 7)
        self.assertEqual(self.progress.xp_points, 125)
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=self.badge).count(), 1)
        self.assertEqual(PerfectDayReceipt.objects.filter(user=self.child, day=self.day).count(), 1)
        self.assertEqual(CoinService.get_balance(self.child), 22)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").count(), 1)
        self.assertCountEqual(
            list(DropLog.objects.filter(user=self.child).values_list("trigger_type", "item_id")),
            [(trigger, item.pk) for trigger, item in self.loot.items()],
        )
        for item in self.loot.values():
            self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)
        self.assertEqual(Notification.objects.filter(user=self.child, notification_type="perfect_day").count(), 1)
        self.assertFalse(ChallengeActivity.objects.filter(user=self.child).exists())
        self.assertFalse(DailyChallenge.objects.filter(user=self.child).exists())
        self.assertFalse(ActivityEvent.objects.filter(subject=self.child, event_type="rpg.check_in_bonus").exists())

    def test_actual_daily_task_awards_threshold_badge_and_both_loot_sources_once(self):
        evaluate_perfect_day_task()
        evaluate_perfect_day_task()

        self.assert_awarded_once()

    def test_perfect_day_evaluates_the_badge_meta_scope(self):
        meta = Badge.objects.create(
            name="Z first recognition", criteria_type=Badge.CriteriaType.BADGES_EARNED_COUNT,
            criteria_value={"count": 1}, xp_bonus=0, rarity="common", award_coins=False,
        )

        evaluate_perfect_day_task()

        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=self.badge).exists())
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=meta).exists())
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type=TriggerType.BADGE_EARNED).count(), 2)

    def test_late_source_failure_rolls_back_perfect_day_badge_bonus_and_both_drops_for_retry(self):
        from apps.notifications.services import notify

        def fail_source_notice(*args, **kwargs):
            if kwargs.get("notification_type") == "perfect_day":
                self.assertTrue(UserBadge.objects.filter(user=self.child, badge=self.badge).exists())
                self.assertEqual(DropLog.objects.filter(user=self.child).count(), 2)
                raise RuntimeError("Perfect Day final notice failed")
            return notify(*args, **kwargs)

        with patch("apps.notifications.services.notify", side_effect=fail_source_notice):
            with self.assertRaisesRegex(RuntimeError, "Perfect Day final notice failed"):
                evaluate_perfect_day_task()

        self.profile.refresh_from_db()
        self.progress.refresh_from_db()
        self.assertEqual((self.profile.perfect_days_count, self.progress.xp_points), (0, 100))
        for model in (PerfectDayReceipt, UserBadge, DropLog, UserInventory, CoinLedger, Notification):
            self.assertFalse(model.objects.filter(user=self.child).exists())
        self.assertFalse(ActivityEvent.objects.filter(subject=self.child).exists())

        evaluate_perfect_day_task()
        evaluate_perfect_day_task()
        self.assert_awarded_once()

    def test_rejected_day_and_saved_receipt_never_trigger_backfill_badges(self):
        self.completion.status = ChoreCompletion.Status.REJECTED
        self.completion.save(update_fields=["status"])
        evaluate_perfect_day_task()
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

        self.completion.status = ChoreCompletion.Status.APPROVED
        self.completion.save(update_fields=["status"])
        self.profile.perfect_days_count = 1
        self.profile.save(update_fields=["perfect_days_count"])
        PerfectDayReceipt.objects.create(user=self.child, day=self.day, historical=True)
        evaluate_perfect_day_task()
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
