"""Live accomplishments grant their promised loot once with the source award."""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.achievements.services import BadgeService
from apps.activity.models import ActivityEvent
from apps.activity.services import ActivityLogService
from apps.chores.models import Chore, ChoreCompletion
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.quests.models import ChallengeActivity, DailyChallenge, Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.constants import TriggerType
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import DropLog, DropTable, ItemDefinition, PerfectDayReceipt, UserInventory
from apps.rpg.tasks import evaluate_perfect_day_task
from config.tests.factories import make_family


class AccomplishmentDropFixture:
    def setUp(self):
        household = make_family(
            "Accomplishment household",
            parents=[{"username": "accomplishment-parent"}],
            children=[{"username": "accomplishment-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.day = timezone.localdate()
        self.profile = self.child.character_profile
        self.profile.last_active_date = self.day
        self.profile.save(update_fields=["last_active_date"])
        self.chore = Chore.objects.create(
            family=household.family, title="Make the bed",
            created_by=self.parent, assigned_to=self.child,
            recurrence=Chore.Recurrence.DAILY,
        )
        ChoreCompletion.objects.create(
            chore=self.chore, user=self.child, completed_date=self.day,
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=0, coin_reward_snapshot=0,
        )
        self.title = ItemDefinition.objects.create(
            slug="title-accomplished", name="Accomplished", icon="A",
            item_type=ItemDefinition.ItemType.COSMETIC_TITLE,
            rarity=ItemDefinition.Rarity.UNCOMMON,
        )

    def seed_drop(self, trigger, item=None, weight=1):
        return DropTable.objects.create(
            trigger_type=trigger, item=item or self.title, weight=weight,
        )

    def badge(self):
        return Badge.objects.create(
            name="First daily chore", description="Finish a chore",
            criteria_type=Badge.CriteriaType.CHORE_COMPLETIONS,
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False,
        )

    def assert_single_drop(self, trigger):
        self.assertEqual(
            list(DropLog.objects.filter(user=self.child).values_list("trigger_type", "item_id")),
            [(trigger, self.title.pk)],
        )
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.title).quantity, 1)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class AccomplishmentDropTests(AccomplishmentDropFixture, TestCase):
    @patch("apps.rpg.services.random.random", return_value=0.999999)
    def test_real_badge_earn_grants_one_drop_and_replay_does_not_repeat_it(self, _roll):
        badge = self.badge()
        self.seed_drop(TriggerType.BADGE_EARNED)

        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"chore"}), [badge])
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"chore"}), [])

        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        self.assert_single_drop(TriggerType.BADGE_EARNED)

    @patch("apps.rpg.services.random.random", return_value=0.999999)
    def test_real_perfect_day_grants_one_drop_and_task_replay_does_not_repeat_it(self, _roll):
        self.seed_drop(TriggerType.PERFECT_DAY)

        evaluate_perfect_day_task()
        evaluate_perfect_day_task()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assert_single_drop(TriggerType.PERFECT_DAY)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_perfect_day_excludes_even_overwhelmingly_weighted_common_items(self, _roll):
        common = ItemDefinition.objects.create(
            name="Common title", item_type=ItemDefinition.ItemType.COSMETIC_TITLE,
            rarity=ItemDefinition.Rarity.COMMON,
        )
        self.seed_drop(TriggerType.PERFECT_DAY, common, weight=1_000_000)
        self.seed_drop(TriggerType.PERFECT_DAY)

        # Pick the largest resulting weight: if Common participates at all,
        # its normal tier budget beats the only Uncommon candidate's budget.
        def choose_heaviest(population, weights, k):
            return [population[max(range(len(population)), key=lambda index: weights[index])]]

        with patch("apps.rpg.services.random.choices", side_effect=choose_heaviest):
            evaluate_perfect_day_task()

        self.assert_single_drop(TriggerType.PERFECT_DAY)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=common).exists())

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_perfect_day_common_only_pool_cannot_substitute_or_rearm_later(self, _roll):
        common = ItemDefinition.objects.create(
            name="Common-only title", item_type=ItemDefinition.ItemType.COSMETIC_TITLE,
            rarity=ItemDefinition.Rarity.COMMON,
        )
        self.seed_drop(TriggerType.PERFECT_DAY, common)

        evaluate_perfect_day_task()
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertEqual(CoinService.get_balance(self.child), 15)

        self.seed_drop(TriggerType.PERFECT_DAY)
        evaluate_perfect_day_task()
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertEqual(CoinService.get_balance(self.child), 15)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_supported_catalog_filters_unavailable_accomplishment_rewards(self, _roll):
        unavailable = ItemDefinition.objects.create(
            name="Unfitted crown", item_type=ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
            rarity=ItemDefinition.Rarity.UNCOMMON,
        )
        self.seed_drop(TriggerType.BADGE_EARNED, unavailable, weight=1_000_000)
        self.seed_drop(TriggerType.BADGE_EARNED)
        self.badge()

        BadgeService.evaluate_badges(self.child, scopes={"chore"})

        self.assert_single_drop(TriggerType.BADGE_EARNED)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=unavailable).exists())

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_unavailable_only_pool_preserves_badge_without_retroactive_loot(self, _roll):
        unavailable = ItemDefinition.objects.create(
            name="Unfitted crown", item_type=ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
            rarity=ItemDefinition.Rarity.UNCOMMON,
        )
        self.seed_drop(TriggerType.BADGE_EARNED, unavailable)
        badge = self.badge()

        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"chore"}), [badge])
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.seed_drop(TriggerType.BADGE_EARNED)
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"chore"}), [])
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())

    def seed_unrelated_progress(self):
        self.profile.login_streak = 7
        self.profile.longest_login_streak = 9
        self.profile.save(update_fields=["login_streak", "longest_login_streak"])
        definition = QuestDefinition.objects.create(
            name="Unrelated collection", quest_type="collection", target_value=10,
        )
        quest = Quest.objects.create(
            definition=definition, end_date=timezone.now() + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        return quest

    def assert_unrelated_progress_untouched(self, quest):
        self.profile.refresh_from_db()
        quest.refresh_from_db()
        self.assertEqual((self.profile.login_streak, self.profile.longest_login_streak), (7, 9))
        self.assertEqual(quest.current_progress, 0)
        self.assertFalse(ChallengeActivity.objects.filter(user=self.child).exists())
        self.assertFalse(DailyChallenge.objects.filter(user=self.child).exists())
        self.assertFalse(ActivityEvent.objects.filter(
            subject=self.child, event_type="rpg.check_in_bonus",
        ).exists())

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_badge_loot_does_not_repeat_activity_streak_checkin_or_quest_credit(self, _roll):
        quest = self.seed_unrelated_progress()
        yesterday = self.day - timedelta(days=1)
        self.profile.last_active_date = yesterday
        self.profile.save(update_fields=["last_active_date"])
        badge = self.badge()
        badge.award_coins = True
        badge.save(update_fields=["award_coins"])
        self.seed_drop(TriggerType.BADGE_EARNED)

        BadgeService.evaluate_badges(self.child, scopes={"chore"})

        self.assert_single_drop(TriggerType.BADGE_EARNED)
        self.assert_unrelated_progress_untouched(quest)
        self.assertEqual(self.profile.last_active_date, yesterday)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("reason", flat=True)), ["badge_bonus"])

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_perfect_day_loot_does_not_repeat_checkin_or_quest_credit(self, _roll):
        quest = self.seed_unrelated_progress()
        self.seed_drop(TriggerType.PERFECT_DAY)

        evaluate_perfect_day_task()

        self.assert_single_drop(TriggerType.PERFECT_DAY)
        self.assert_unrelated_progress_untouched(quest)
        self.assertEqual(CoinService.get_balance(self.child), 15)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_preexisting_badge_marker_never_receives_backfilled_loot(self, _roll):
        badge = self.badge()
        UserBadge.objects.create(user=self.child, badge=badge)
        self.seed_drop(TriggerType.BADGE_EARNED)

        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"chore"}), [])

        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_historical_perfect_day_receipt_never_receives_backfilled_loot(self, _roll):
        PerfectDayReceipt.objects.create(user=self.child, day=self.day, historical=True)
        self.profile.perfect_days_count = 1
        self.profile.save(update_fields=["perfect_days_count"])
        CoinLedger.objects.create(user=self.child, amount=15, reason="adjustment")
        self.seed_drop(TriggerType.PERFECT_DAY)

        evaluate_perfect_day_task()

        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertEqual(CoinService.get_balance(self.child), 15)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)

    def fail_after_drop(self, trigger):
        original_record = ActivityLogService.record

        def fail(*args, **kwargs):
            if kwargs.get("event_type") == "rpg.drop_rolled":
                self.assertTrue(DropLog.objects.filter(user=self.child, trigger_type=trigger).exists())
                self.assertTrue(UserInventory.objects.filter(user=self.child, item=self.title).exists())
                raise RuntimeError("Accomplishment audit storage failed")
            return original_record(*args, **kwargs)

        return patch.object(ActivityLogService, "record", side_effect=fail)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_badge_drop_failure_rolls_back_marker_xp_coins_and_inventory_for_retry(self, _roll):
        category = SkillCategory.objects.create(name="Accomplishment skills")
        skill = Skill.objects.create(category=category, name="Persistence")
        progress = SkillProgress.objects.create(user=self.child, skill=skill, xp_points=100, level=1)
        badge = self.badge()
        badge.xp_bonus = 15
        badge.award_coins = True
        badge.save(update_fields=["xp_bonus", "award_coins"])
        self.seed_drop(TriggerType.BADGE_EARNED)

        with self.fail_after_drop(TriggerType.BADGE_EARNED):
            with self.assertRaisesRegex(RuntimeError, "audit storage failed"):
                BadgeService.evaluate_badges(self.child, scopes={"chore"})

        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        progress.refresh_from_db()
        self.assertEqual(progress.xp_points, 100)

        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"chore"}), [badge])
        self.assert_single_drop(TriggerType.BADGE_EARNED)
        progress.refresh_from_db()
        self.assertEqual(progress.xp_points, 115)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").count(), 1)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_perfect_day_drop_failure_rolls_back_receipt_coins_and_inventory_for_retry(self, _roll):
        self.seed_drop(TriggerType.PERFECT_DAY)

        with self.fail_after_drop(TriggerType.PERFECT_DAY):
            with self.assertRaisesRegex(RuntimeError, "audit storage failed"):
                evaluate_perfect_day_task()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 0)
        self.assertFalse(PerfectDayReceipt.objects.filter(user=self.child).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

        evaluate_perfect_day_task()
        self.assert_single_drop(TriggerType.PERFECT_DAY)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assertEqual(CoinService.get_balance(self.child), 15)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_optional_badge_drop_notification_failure_preserves_loot_without_partial_notice(self, _roll):
        badge = self.badge()
        self.seed_drop(TriggerType.BADGE_EARNED)

        def fail_after_notification(*args, **kwargs):
            notify(*args, **kwargs)
            raise RuntimeError("Optional drop notification unavailable")

        with patch("apps.notifications.services._push_now") as push:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertLogs("apps.rpg.services", level="ERROR"), patch(
                    "apps.notifications.services.notify", side_effect=fail_after_notification,
                ):
                    self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"chore"}), [badge])
            push.assert_not_called()

        self.assert_single_drop(TriggerType.BADGE_EARNED)
        self.assertFalse(Notification.objects.filter(user=self.child, notification_type="drop_received").exists())

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_optional_perfect_day_drop_notification_failure_preserves_source_award(self, _roll):
        self.seed_drop(TriggerType.PERFECT_DAY)

        def fail_drop_notice(*args, **kwargs):
            if kwargs.get("notification_type") == "drop_received":
                raise RuntimeError("Optional drop notification unavailable")
            return notify(*args, **kwargs)

        with self.assertLogs("apps.rpg.services", level="ERROR"), patch(
            "apps.notifications.services.notify", side_effect=fail_drop_notice,
        ):
            evaluate_perfect_day_task()

        self.assert_single_drop(TriggerType.PERFECT_DAY)
        self.assertEqual(CoinService.get_balance(self.child), 15)
        self.assertTrue(Notification.objects.filter(user=self.child, notification_type="perfect_day").exists())

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_drop_push_waits_for_the_accomplishment_transaction_commit(self, _roll):
        self.badge()
        self.seed_drop(TriggerType.BADGE_EARNED)

        with patch("apps.notifications.services._push_now") as push:
            with self.captureOnCommitCallbacks(execute=True):
                BadgeService.evaluate_badges(self.child, scopes={"chore"})
                self.assert_single_drop(TriggerType.BADGE_EARNED)
                self.assertTrue(Notification.objects.filter(user=self.child, notification_type="drop_received").exists())
                push.assert_not_called()
            push.assert_called_once()
            self.assertEqual(push.call_args.args[0].notification_type, "drop_received")

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_later_outer_rollback_discards_loot_notice_and_external_push(self, _roll):
        badge = self.badge()
        self.seed_drop(TriggerType.BADGE_EARNED)

        with patch("apps.notifications.services._push_now") as push:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaisesRegex(RuntimeError, "Source transaction failed"):
                    with transaction.atomic():
                        BadgeService.evaluate_badges(self.child, scopes={"chore"})
                        self.assert_single_drop(TriggerType.BADGE_EARNED)
                        self.assertTrue(Notification.objects.filter(user=self.child, notification_type="drop_received").exists())
                        raise RuntimeError("Source transaction failed")
            push.assert_not_called()

        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=badge).exists())
        self.assertFalse(DropLog.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(Notification.objects.filter(user=self.child, notification_type="drop_received").exists())


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class InstalledAccomplishmentDropContentTests(AccomplishmentDropFixture, TestCase):
    def setUp(self):
        # Load before the synthetic fixture item exists: the result must come
        # from actual installed content, not a macro swept over test artwork.
        ContentPack(settings.BASE_DIR / "content/rpg/initial").load()
        super().setUp()

    def test_initial_content_gives_a_level_zero_child_supported_uncommon_perfect_day_loot(self):
        self.assertEqual(self.profile.level, 0)

        evaluate_perfect_day_task()

        drop = DropLog.objects.select_related("item").get(user=self.child, trigger_type=TriggerType.PERFECT_DAY)
        self.assertIn(drop.item.rarity, {"uncommon", "rare", "epic", "legendary"})
        self.assertNotEqual(drop.item_id, self.title.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=drop.item).quantity, 1)
        from apps.rpg.catalog_support import random_item_is_available

        self.assertTrue(random_item_is_available(drop.item))
