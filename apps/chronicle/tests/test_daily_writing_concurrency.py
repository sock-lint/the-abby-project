"""The journal and older Today clients serialize one shared coin payout."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, local
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.rewards.models import CoinLedger
from apps.wellbeing.models import DailyWellbeingEntry
from apps.wellbeing.services import WellbeingService


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class DailyWritingConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="daily-writing", role="child")

    def _request(self, kind, *, pids=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            if pids is not None:
                pids.append(pid)
            if kind == "journal":
                entry = ChronicleService.write_journal(self.user, title="A day", summary="A few words.")
                return entry.metadata["reward_receipt"]["coins_awarded"]
            if kind == "note":
                return WellbeingService.submit_gratitude(self.user, ["A private thought."])["coin_awarded"]
            return WellbeingService.get_or_create_today(self.user).pk
        finally:
            connection.close()

    def _overlap(self, first_kind, second_kind):
        first_ready, release_first = Event(), Event()
        worker_state = local()
        second_pids = []
        model = DailyWellbeingEntry if first_kind == "get" else ChronicleEntry
        original_save = model.save

        def held_save(entry, *args, **kwargs):
            if getattr(worker_state, "hold", False) and entry._state.adding:
                worker_state.hold = False
                first_ready.set()
                if not release_first.wait(10):
                    raise TimeoutError("First daily writer was not released")
            return original_save(entry, *args, **kwargs)

        def first_request():
            worker_state.hold = True
            return self._request(first_kind)

        with patch.object(model, "save", held_save), patch(
            "apps.chronicle.services.GameLoopService.on_task_completed", return_value={},
        ), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(first_request)
            try:
                self.assertTrue(first_ready.wait(5), "First writer did not reach pending insert")
                second = pool.submit(self._request, second_kind, pids=second_pids)
                deadline = monotonic() + 4
                waited = False
                while monotonic() < deadline:
                    if second.done():
                        second.result()
                        break
                    if second_pids:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [second_pids[0]],
                            )
                            row = cursor.fetchone()
                        if row and row[0] == "Lock":
                            waited = True
                            break
                    sleep(0.01)
                self.assertTrue(waited, "Competing request did not serialize behind the author lock")
            finally:
                release_first.set()
            return first.result(timeout=15), second.result(timeout=15)

    def test_journal_first_blocks_legacy_writer_and_pays_once(self):
        self.assertEqual(self._overlap("journal", "note"), (2, 0))
        self.assertEqual(CoinLedger.objects.get(user=self.user).amount, 2)
        self.assertEqual(ChronicleEntry.objects.filter(user=self.user).count(), 2)
        self.assertIsNotNone(DailyWellbeingEntry.objects.get(user=self.user).coin_paid_at)

    def test_legacy_writer_first_blocks_journal_and_pays_once(self):
        self.assertEqual(self._overlap("note", "journal"), (2, 0))
        self.assertEqual(CoinLedger.objects.get(user=self.user).amount, 2)
        self.assertEqual(ChronicleEntry.objects.filter(user=self.user).count(), 2)

    def test_fresh_today_get_cannot_deadlock_journal_sentinel_creation(self):
        _, coins = self._overlap("get", "journal")
        self.assertEqual(coins, 2)
        self.assertEqual(DailyWellbeingEntry.objects.filter(user=self.user).count(), 1)
        self.assertEqual(CoinLedger.objects.get(user=self.user).amount, 2)
