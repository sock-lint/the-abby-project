"""Concurrent delivery cannot pay an accomplishment's loot twice."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, local
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from apps.achievements.models import UserBadge
from apps.achievements.services import BadgeService
from apps.rewards.services import CoinService
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, PerfectDayReceipt
from apps.rpg.tasks import evaluate_perfect_day_task
from apps.rpg.tests.test_accomplishment_drops import AccomplishmentDropFixture


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class AccomplishmentDropConcurrencyTests(AccomplishmentDropFixture, TransactionTestCase):
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

    def overlapping_awards(self, action):
        """Hold the first saved drop until the competitor waits for its award."""
        drop_saved, release_first = Event(), Event()
        first_ready, second_ready = Event(), Event()
        state, pids = local(), {}
        original_save = DropLog.save

        def hold_saved_drop(log, *args, **kwargs):
            result = original_save(log, *args, **kwargs)
            if getattr(state, "hold", False):
                state.hold = False
                drop_saved.set()
                if not release_first.wait(10):
                    raise TimeoutError("First accomplishment drop was not released")
            return result

        def first_action():
            state.hold = True
            return action()

        with patch.object(DropLog, "save", hold_saved_drop), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.worker, first_action, first_ready, pids, "first")
            try:
                self.assertTrue(drop_saved.wait(5), "First award never saved its drop")
                second = pool.submit(self.worker, action, second_ready, pids, "second")
                self.assertTrue(second_ready.wait(5), "Second award connection did not start")
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    if second.done():
                        second.result()
                        self.fail("Second award completed before the first source award committed")
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids["second"]])
                        if pids["first"] in cursor.fetchone()[0]:
                            break
                    Event().wait(0.01)
                else:
                    self.fail("Second accomplishment never waited for the first award")
            finally:
                release_first.set()
            return first.result(timeout=15), second.result(timeout=15)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_concurrent_badge_evaluations_grant_one_drop(self, _roll):
        badge = self.badge()
        self.seed_drop(TriggerType.BADGE_EARNED)

        results = self.overlapping_awards(
            lambda: BadgeService.evaluate_badges(self.child, scopes={"chore"}),
        )

        self.assertEqual(sorted(len(result) for result in results), [0, 1])
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assert_single_drop(TriggerType.BADGE_EARNED)

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_concurrent_perfect_day_deliveries_grant_one_drop(self, _roll):
        self.seed_drop(TriggerType.PERFECT_DAY)

        results = self.overlapping_awards(evaluate_perfect_day_task)

        self.assertEqual(sum("1/" in result for result in results), 1)
        self.assertEqual(PerfectDayReceipt.objects.filter(user=self.child, day=self.day).count(), 1)
        self.assert_single_drop(TriggerType.PERFECT_DAY)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.perfect_days_count, 1)
        self.assertEqual(CoinService.get_balance(self.child), 15)
