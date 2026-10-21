"""Inventory badge cascades serialize with grants and last-item consumption."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.inventory import grant_item
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL account and inventory row locks")
@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    COINS_PER_BADGE_RARITY={"common": 7},
    RPG_ASSET_SUPPORT_POLICY=None,
)
class InventoryBadgeConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.child = make_family(
            "Concurrent inventory badge family", children=[{"username": "inventory-badge-race"}],
        ).children[0]
        category = SkillCategory.objects.create(name="Concurrent collection skills")
        skill = Skill.objects.create(category=category, name="Persistence")
        self.progress = SkillProgress.objects.create(
            user=self.child, skill=skill, xp_points=100, level=1, unlocked=True,
        )
        frame = ItemDefinition.objects.create(
            slug="race-collection-frame", name="Collection frame", item_type="cosmetic_frame",
        )
        self.last_piece = ItemDefinition.objects.create(
            slug="race-collection-title", name="Collection title", item_type="cosmetic_title",
        )
        UserInventory.objects.create(user=self.child, item=frame, quantity=1)
        self.badge = Badge.objects.create(
            name="Concurrent complete collection", criteria_type="cosmetic_set_owned",
            criteria_value={"slugs": [frame.slug, self.last_piece.slug]},
            xp_bonus=20, rarity="common", award_coins=True,
        )
        self.bonus = ItemDefinition.objects.create(
            slug="race-badge-streak-freeze", name="Badge streak freeze", item_type="consumable",
            metadata={"effect": "streak_freeze", "duration_days": 1},
        )
        DropTable.objects.create(trigger_type=TriggerType.BADGE_EARNED, item=self.bonus, weight=1)

    @staticmethod
    def worker(action, ready, pids, label):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[label] = cursor.fetchone()[0]
            ready.set()
            return action()
        finally:
            connection.close()

    def overlap_badge_drop(self, second_action):
        """Hold the uncommitted badge loot until the competitor waits on its user."""
        drop_saved, release = Event(), Event()
        first_ready, second_ready = Event(), Event()
        pids = {}
        original_save = DropLog.save

        def pause_badge_drop(drop, *args, **kwargs):
            result = original_save(drop, *args, **kwargs)
            if drop.user_id == self.child.pk and drop.trigger_type == TriggerType.BADGE_EARNED:
                drop_saved.set()
                if not release.wait(10):
                    raise TimeoutError("Inventory badge cascade was not released")
            return result

        with patch.object(DropLog, "save", pause_badge_drop), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                self.worker, lambda: grant_item(self.child, self.last_piece),
                first_ready, pids, "first",
            )
            second = None
            try:
                self.assertTrue(drop_saved.wait(5), "Last-piece grant never produced its badge loot")
                second = pool.submit(self.worker, second_action, second_ready, pids, "second")
                self.assertTrue(second_ready.wait(5), "Competing database connection did not start")
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    if second.done():
                        second.result()
                        self.fail("Competing mutation finished before the badge cascade committed")
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_blocking_pids(pid), query FROM pg_stat_activity WHERE pid = %s",
                            [pids["second"]],
                        )
                        blockers, query = cursor.fetchone()
                    if pids["first"] in blockers:
                        # Both grant and use must take the account gate before
                        # touching an inventory stack or entering badge evaluation.
                        self.assertIn('"projects_user"', query)
                        self.assertIn("FOR NO KEY UPDATE", query)
                        break
                    Event().wait(0.01)
                else:
                    self.fail("Competing mutation never waited for the account award gate")
            finally:
                release.set()
            first.result(timeout=15)
            self.assertIsNotNone(second)
            return second.result(timeout=15)

    def assert_one_badge_payout(self):
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=self.badge).count(), 1)
        self.assertEqual(
            list(DropLog.objects.filter(user=self.child).values_list("trigger_type", "item_id", "quantity")),
            [(TriggerType.BADGE_EARNED, self.bonus.pk, 1)],
        )
        self.assertEqual(
            list(CoinLedger.objects.filter(user=self.child).values_list("reason", "amount")),
            [(CoinLedger.Reason.BADGE_BONUS, 7)],
        )
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 120)

    def test_competing_last_piece_grants_preserve_both_units_and_pay_the_collection_once(self):
        self.overlap_badge_drop(lambda: grant_item(self.child, self.last_piece))

        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.last_piece).quantity, 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.bonus).quantity, 1)
        self.assert_one_badge_payout()

    def test_collection_badge_loot_survives_competing_use_of_the_original_last_unit(self):
        UserInventory.objects.create(user=self.child, item=self.bonus, quantity=1)

        used = self.overlap_badge_drop(lambda: ConsumableService.use(self.child, self.bonus.pk))

        self.assertEqual(used["quantity_used"], 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.last_piece).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.bonus).quantity, 1)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).streak_freezes_used, 1)
        self.assert_one_badge_payout()
