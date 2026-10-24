"""A saved birthday recognizes badges without replaying gifts or activity."""
from datetime import date
from unittest.mock import patch

from celery.exceptions import Retry
from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.chronicle.tasks import chronicle_birthday_check
from apps.notifications.models import Notification, NotificationType
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


DAY = date(2026, 4, 21)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    COINS_PER_BADGE_RARITY={"common": 7, "uncommon": 13, "rare": 23, "epic": 37},
    BIRTHDAY_COINS_PER_YEAR=100,
    BIRTHDAY_COIN_GIFT=200,
    RPG_ASSET_SUPPORT_POLICY=None,
)
class BirthdayBadgeTests(TestCase):
    def setUp(self):
        household = make_family("Birthday household", children=[
            {"username": "birthday-child", "date_of_birth": date(2011, 4, 21)},
            {"username": "birthday-sibling", "date_of_birth": date(2012, 7, 4)},
        ])
        self.child, self.sibling = household.children
        self.other = make_family("Other birthday household", children=[
            {"username": "birthday-other", "date_of_birth": date(2011, 7, 4)},
        ]).children[0]
        category = SkillCategory.objects.create(name="Birthday skills")
        skill = Skill.objects.create(category=category, name="Birthday persistence")
        self.progress = SkillProgress.objects.create(
            user=self.child, skill=skill, xp_points=100, level=1, unlocked=True,
        )
        self.loot = ItemDefinition.objects.create(
            slug="birthday-test-streak-freeze", name="Birthday streak freeze", item_type="consumable",
            metadata={"effect": "streak_freeze", "duration_days": 1},
        )
        DropTable.objects.create(trigger_type=TriggerType.BADGE_EARNED, item=self.loot)

    def badge(self, *, count=1, name="01 Birthday badge", xp=25, rarity="common", coins=True):
        return Badge.objects.create(
            name=name, criteria_type=Badge.CriteriaType.BIRTHDAYS_LOGGED,
            criteria_value={"count": count}, xp_bonus=xp, rarity=rarity, award_coins=coins,
        )

    def previous_birthdays(self, count, *, user=None):
        user = user or self.child
        for offset in range(1, count + 1):
            ChronicleEntry.objects.create(
                user=user, kind=ChronicleEntry.Kind.BIRTHDAY,
                occurred_on=date(DAY.year - offset, 4, 21), chapter_year=DAY.year - offset - 1,
                title="Earlier birthday",
            )

    def run_task(self, *, today=DAY, **kwargs):
        with (
            patch("apps.chronicle.tasks.date", wraps=date) as task_date,
            patch("apps.accounts.models.date", wraps=date) as account_date,
        ):
            task_date.today.return_value = today
            account_date.today.return_value = today
            return chronicle_birthday_check(**kwargs)

    def assert_one_award(self, badge, *, xp=25, gift=False):
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100 + xp)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").count(), 1)
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type=TriggerType.BADGE_EARNED).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.loot).quantity, 1)
        gifts = CoinLedger.objects.filter(user=self.child, description="birthday_gift")
        self.assertEqual(gifts.count(), int(gift))
        if gift:
            self.assertEqual(gifts.get().amount, 200)
            entry = ChronicleEntry.objects.get(user=self.child, kind="birthday", occurred_on=DAY)
            self.assertEqual(entry.metadata["gift_coins"], 200)

    def test_scheduled_birthday_awards_and_gift_are_not_replayed(self):
        badge = self.badge()
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as activity:
            self.assertEqual(self.run_task(), {"birthdays": 1, "gifts": 1})
            self.assert_one_award(badge, gift=True)
            self.assertEqual(self.run_task(), {"birthdays": 1, "gifts": 0})
            self.assert_one_award(badge, gift=True)
        activity.assert_not_called()
        self.assertEqual(Notification.objects.filter(user=self.child, notification_type="birthday").count(), 1)

    def test_direct_birthday_service_awards_once_without_inventing_a_gift(self):
        badge = self.badge()
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as activity:
            entry = ChronicleService.record_birthday(self.child, on_date=DAY)
            self.assert_one_award(badge)
            self.assertEqual(ChronicleService.record_birthday(self.child, on_date=DAY).pk, entry.pk)
            self.assert_one_award(badge)
        activity.assert_not_called()

    def test_each_scheduled_birthday_threshold_recognizes_its_new_badge(self):
        for count, name in ((1, "First Birthday In-App"), (3, "Many Years"),
                            (5, "Decade Marker"), (10, "All the Years")):
            with self.subTest(count=count):
                user = make_family(f"Birthday tier {count}", children=[
                    {"username": f"birthday-tier-{count}", "date_of_birth": date(2011, 4, 21)},
                ]).children[0]
                self.previous_birthdays(count - 1, user=user)
                badge = self.badge(count=count, name=name, xp=0, coins=False)
                self.run_task()
                self.assertEqual(UserBadge.objects.filter(user=user, badge=badge).count(), 1)
                self.assertEqual(CoinLedger.objects.filter(user=user, description="birthday_gift").count(), 1)

    def test_each_direct_birthday_threshold_recognizes_its_new_badge(self):
        for count in (1, 3, 5, 10):
            with self.subTest(count=count):
                user = make_family(f"Direct birthday tier {count}", children=[
                    {"username": f"direct-birthday-tier-{count}"},
                ]).children[0]
                self.previous_birthdays(count - 1, user=user)
                badge = self.badge(count=count, name=f"Direct birthday {count}", xp=0, coins=False)
                ChronicleService.record_birthday(user, on_date=DAY)
                self.assertEqual(UserBadge.objects.filter(user=user, badge=badge).count(), 1)
                self.assertFalse(CoinLedger.objects.filter(user=user, description="birthday_gift").exists())

    def test_tenth_birthday_can_award_four_badges_with_one_drop_each(self):
        self.previous_birthdays(9)
        badges = [self.badge(count=count, name=name, xp=xp, rarity=rarity) for count, name, xp, rarity in (
            (1, "First Birthday In-App", 25, "common"), (3, "Many Years", 60, "uncommon"),
            (5, "Decade Marker", 100, "rare"), (10, "All the Years", 250, "epic"),
        )]
        self.run_task()
        self.run_task()
        self.assertEqual(set(UserBadge.objects.filter(user=self.child).values_list("badge_id", flat=True)),
                         {badge.pk for badge in badges})
        self.assertEqual(DropLog.objects.filter(user=self.child, trigger_type=TriggerType.BADGE_EARNED).count(), 4)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.loot).quantity, 4)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, description="birthday_gift").count(), 1)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100 + 25 + 60 + 100 + 250)

    def test_zero_bonus_birthday_badge_still_gets_one_drop(self):
        badge = self.badge(xp=0, coins=False)
        self.run_task()
        self.run_task()
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assertEqual(DropLog.objects.filter(user=self.child).count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").exists())
        self.assertEqual(CoinLedger.objects.get(user=self.child, description="birthday_gift").amount, 200)

    def test_birthday_badge_unlocks_meta_badge_with_one_drop_per_new_badge(self):
        birthday = self.badge(xp=20)
        collector = Badge.objects.create(
            name="02 First badge collected", criteria_type=Badge.CriteriaType.BADGES_EARNED_COUNT,
            criteria_value={"count": 1}, xp_bonus=20, rarity="common",
        )
        self.run_task()
        self.run_task()
        self.assertEqual(set(UserBadge.objects.filter(user=self.child).values_list("badge_id", flat=True)),
                         {birthday.pk, collector.pk})
        self.assertEqual(DropLog.objects.filter(user=self.child).count(), 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.loot).quantity, 2)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").count(), 2)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 140)

    def test_other_accounts_history_does_not_count_or_receive_rewards(self):
        self.badge(count=3)
        self.previous_birthdays(1)
        self.previous_birthdays(9, user=self.sibling)
        self.previous_birthdays(9, user=self.other)
        self.run_task()
        self.assertFalse(UserBadge.objects.exists())
        self.assertFalse(DropLog.objects.exists())
        self.assertFalse(CoinLedger.objects.filter(user__in=[self.sibling, self.other]).exists())

    def test_saved_birthday_replays_do_not_backfill_badges_or_gifts(self):
        ChronicleEntry.objects.create(
            user=self.child, kind="birthday", occurred_on=DAY, chapter_year=2025, title="Saved birthday",
        )
        self.badge()
        ChronicleService.record_birthday(self.child, on_date=DAY)
        self.run_task()
        self.assertFalse(UserBadge.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(DropLog.objects.exists())

    def test_direct_drop_failure_rolls_back_marker_and_payout_for_retry(self):
        badge = self.badge()
        with patch.object(DropLog.objects, "create", side_effect=RuntimeError("Birthday loot failed")):
            with self.assertRaisesRegex(RuntimeError, "Birthday loot failed"):
                ChronicleService.record_birthday(self.child, on_date=DAY)
        self.assertFalse(ChronicleEntry.objects.filter(user=self.child).exists())
        self.assertFalse(UserBadge.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)
        ChronicleService.record_birthday(self.child, on_date=DAY)
        self.assert_one_award(badge)

    def test_failed_child_rolls_back_gift_and_does_not_block_later_family(self):
        badge = self.badge()
        self.other.date_of_birth = date(2011, 4, 21)
        self.other.save(update_fields=["date_of_birth"])
        original_create = DropLog.objects.create

        def fail_first_child(**kwargs):
            if kwargs["user"].pk == self.child.pk:
                raise RuntimeError("Birthday loot failed")
            return original_create(**kwargs)

        with (
            patch.object(DropLog.objects, "create", side_effect=fail_first_child),
            patch.object(chronicle_birthday_check, "retry", side_effect=Retry()) as retry,
            self.assertRaises(Retry),
        ):
            self.run_task()
        retry_kwargs = retry.call_args.kwargs
        self.assertEqual(retry_kwargs["kwargs"], {"birthday_date": DAY.isoformat()})
        self.assertEqual(retry_kwargs["countdown"], 300)
        self.assertFalse(ChronicleEntry.objects.filter(user=self.child).exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertTrue(UserBadge.objects.filter(user=self.other, badge=badge).exists())
        self.assertEqual(CoinLedger.objects.filter(user=self.other, description="birthday_gift").count(), 1)

        self.run_task(today=date(2026, 4, 22), **retry_kwargs["kwargs"])
        self.assert_one_award(badge, gift=True)
        self.assertEqual(CoinLedger.objects.filter(user=self.other, description="birthday_gift").count(), 1)
        self.assertEqual(DropLog.objects.filter(user=self.other).count(), 1)
        self.assertEqual(ChronicleEntry.objects.get(user=self.child, kind="birthday").occurred_on, DAY)

    def test_exhausted_retry_budget_leaves_failed_birthday_unpaid(self):
        self.badge()
        chronicle_birthday_check.push_request(retries=3, called_directly=False, is_eager=True)
        try:
            with patch.object(DropLog.objects, "create", side_effect=RuntimeError("Birthday loot failed")):
                with self.assertRaisesRegex(RuntimeError, "Birthday loot failed"):
                    self.run_task()
        finally:
            chronicle_birthday_check.pop_request()
        self.assertFalse(ChronicleEntry.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())

    def test_birthday_notification_database_failure_preserves_gift_and_badge(self):
        badge = self.badge()
        original_create = Notification.objects.create

        def reject_birthday_notice(**kwargs):
            if kwargs.get("notification_type") == NotificationType.BIRTHDAY:
                kwargs = {**kwargs, "user": None}
            return original_create(**kwargs)

        with patch.object(Notification.objects, "create", side_effect=reject_birthday_notice):
            self.run_task()
        self.assert_one_award(badge, gift=True)
