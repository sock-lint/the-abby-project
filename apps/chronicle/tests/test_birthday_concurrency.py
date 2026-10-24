"""Birthday writers hold the account gate before creating their reward marker."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event, local
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.chronicle.tasks import chronicle_birthday_check
from apps.notifications.models import Notification
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL account row locks")
@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    COINS_PER_BADGE_RARITY={"common": 7},
    BIRTHDAY_COINS_PER_YEAR=100,
    RPG_ASSET_SUPPORT_POLICY=None,
)
class BirthdayConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.day = date(2026, 4, 21)
        self.child = make_family(
            "Competing birthday household",
            children=[{"username": "birthday-race-child", "date_of_birth": date(2011, 4, 21)}],
        ).children[0]
        category = SkillCategory.objects.create(name="Birthday race skills")
        skill = Skill.objects.create(category=category, name="Birthday persistence")
        self.progress = SkillProgress.objects.create(
            user=self.child, skill=skill, xp_points=100, level=1, unlocked=True,
        )
        self.birthday_badge = Badge.objects.create(
            name="01 Birthday celebrated", criteria_type=Badge.CriteriaType.BIRTHDAYS_LOGGED,
            criteria_value={"count": 1}, xp_bonus=20, rarity="common", award_coins=True,
        )
        self.collection_badge = Badge.objects.create(
            name="02 First badge collected", criteria_type=Badge.CriteriaType.BADGES_EARNED_COUNT,
            criteria_value={"count": 1}, xp_bonus=20, rarity="common", award_coins=True,
        )
        self.loot = ItemDefinition.objects.create(
            slug="birthday-race-streak-freeze", name="Birthday streak freeze",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            metadata={"effect": "streak_freeze", "duration_days": 1},
        )
        DropTable.objects.create(trigger_type=TriggerType.BADGE_EARNED, item=self.loot, weight=1)

    def _writer(self, kind, *, ready, pids, label, state=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[label] = cursor.fetchone()[0]
            if state is not None:
                state.hold = True
            ready.set()
            if kind == "task":
                return chronicle_birthday_check()
            user = get_user_model().objects.get(pk=self.child.pk)
            return ChronicleService.record_birthday(user, on_date=self.day).pk
        finally:
            connection.close()

    def _overlap(self, first_kind, second_kind):
        """Observe the competitor waiting on the account before the first INSERT."""
        before_insert, release = Event(), Event()
        first_ready, second_ready = Event(), Event()
        state, pids = local(), {}
        original_save = ChronicleEntry.save

        def hold_birthday_insert(entry, *args, **kwargs):
            if (
                getattr(state, "hold", False) and entry._state.adding
                and entry.user_id == self.child.pk and entry.kind == ChronicleEntry.Kind.BIRTHDAY
            ):
                state.hold = False
                before_insert.set()
                if not release.wait(10):
                    raise TimeoutError("First birthday writer was not released")
            return original_save(entry, *args, **kwargs)

        with (
            patch.object(ChronicleEntry, "save", hold_birthday_insert),
            patch("apps.chronicle.tasks.date", wraps=date) as task_date,
            patch("apps.accounts.models.date", wraps=date) as account_date,
            ThreadPoolExecutor(max_workers=2) as workers,
        ):
            task_date.today.return_value = self.day
            account_date.today.return_value = self.day
            first = workers.submit(
                self._writer, first_kind, ready=first_ready, pids=pids, label="first", state=state,
            )
            second = None
            try:
                self.assertTrue(before_insert.wait(5), "First birthday writer never reached its marker INSERT")
                second = workers.submit(
                    self._writer, second_kind, ready=second_ready, pids=pids, label="second",
                )
                self.assertTrue(second_ready.wait(5), "Competing birthday connection did not start")
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    if second.done():
                        second.result()
                        self.fail("Competing birthday writer passed the account gate before the first committed")
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_blocking_pids(pid), query FROM pg_stat_activity WHERE pid = %s",
                            [pids["second"]],
                        )
                        row = cursor.fetchone()
                    if row and pids["first"] in row[0]:
                        self.assertIn('"projects_user"', row[1])
                        self.assertIn("FOR NO KEY UPDATE", row[1])
                        break
                    Event().wait(0.01)
                else:
                    self.fail("Competing birthday writer never waited for the account gate")
            finally:
                release.set()
            first_result = first.result(timeout=15)
            self.assertIsNotNone(second)
            return first_result, second.result(timeout=15)

    def _assert_rewards(self, *, gifted):
        entry = ChronicleEntry.objects.get(user=self.child, kind=ChronicleEntry.Kind.BIRTHDAY)
        self.assertEqual(entry.occurred_on, self.day)
        self.assertEqual(entry.metadata.get("gift_coins"), 1500 if gifted else None)
        gifts = CoinLedger.objects.filter(user=self.child, description="birthday_gift")
        self.assertEqual(list(gifts.values_list("amount", flat=True)), [1500] if gifted else [])
        self.assertEqual(
            Notification.objects.filter(user=self.child, notification_type="birthday").count(),
            1 if gifted else 0,
        )
        self.assertEqual(
            set(UserBadge.objects.filter(user=self.child).values_list("badge_id", flat=True)),
            {self.birthday_badge.pk, self.collection_badge.pk},
        )
        self.assertEqual(
            list(CoinLedger.objects.filter(user=self.child, reason=CoinLedger.Reason.BADGE_BONUS)
                 .order_by("pk").values_list("amount", flat=True)),
            [7, 7],
        )
        self.assertEqual(
            list(DropLog.objects.filter(user=self.child).order_by("pk")
                 .values_list("trigger_type", "item_id", "quantity")),
            [(TriggerType.BADGE_EARNED, self.loot.pk, 1)] * 2,
        )
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.loot).quantity, 2)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 140)

    def test_competing_scheduled_birthdays_pay_one_gift_and_each_new_badge_once(self):
        first, second = self._overlap("task", "task")

        self.assertEqual((first, second), ({"birthdays": 1, "gifts": 1}, {"birthdays": 1, "gifts": 0}))
        self._assert_rewards(gifted=True)

    def test_competing_direct_birthdays_create_one_entry_and_pay_each_new_badge_once(self):
        first, second = self._overlap("service", "service")

        self.assertEqual(first, second)
        self._assert_rewards(gifted=False)

    def test_direct_writer_after_scheduled_birthday_preserves_one_gift_and_badge_rewards(self):
        first, second = self._overlap("task", "service")

        self.assertEqual(first, {"birthdays": 1, "gifts": 1})
        self.assertEqual(second, ChronicleEntry.objects.get(user=self.child, kind="birthday").pk)
        self._assert_rewards(gifted=True)

    def test_scheduled_writer_after_direct_birthday_preserves_existing_no_gift_semantics(self):
        first, second = self._overlap("service", "task")

        self.assertEqual(first, ChronicleEntry.objects.get(user=self.child, kind="birthday").pk)
        self.assertEqual(second, {"birthdays": 1, "gifts": 0})
        self._assert_rewards(gifted=False)
