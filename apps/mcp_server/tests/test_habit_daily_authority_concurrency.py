"""Registered habit/daily requests keep household authority until results return."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import OperationalError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.families.models import Family
from apps.habits.models import Habit
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import daily_challenges, habits
from apps.quests.models import DailyChallenge
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HabitDailyAuthorityConcurrencyTests(TransactionTestCase):
    def setUp(self):
        # The subject predates the actor so actor-first nested guards would
        # violate the station's sorted-account lock order.
        home = make_family("Locked routine household", children=[{"username": "locked-routine-child"}])
        self.child = home.children[0]
        self.parent = get_user_model().objects.create_user(
            username="locked-routine-parent", family=home.family, role="parent", is_staff=True,
        )
        self.other = make_family("Next routine household").family
        self.habit = Habit.objects.create(name="Saved locked routine", user=self.child, created_by=self.parent, xp_reward=0)
        self.daily = DailyChallenge.objects.create(
            user=self.child, date=timezone.localdate(timezone=ZoneInfo(home.family.timezone)),
            challenge_type="chore", target_value=1, current_progress=1,
            completed_at=timezone.now(), coin_reward=11, xp_reward=0,
        )

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:read", "mcp:write"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def worker(self, operation):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '12s'")
            return operation()
        finally:
            connection.close()

    def assert_held_until_result_returns(self, module, attribute, name, params):
        ready, release = Event(), Event()
        original = getattr(module, attribute)

        def held(*args, **kwargs):
            result = original(*args, **kwargs)
            ready.set()
            if not release.wait(10):
                raise TimeoutError("Routine response was not released")
            return result

        with patch.object(module, attribute, side_effect=held), ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(self.worker, lambda: self.wire(name, params))
            try:
                self.assertTrue(ready.wait(5), "SDK request did not materialize its response")
                for model, pk in ((Family, self.parent.family_id), (get_user_model(), self.parent.pk),
                                  (get_user_model(), self.child.pk)):
                    with self.subTest(model=model.__name__, pk=pk):
                        with self.assertRaises(OperationalError) as raised:
                            with transaction.atomic():
                                model.objects.select_for_update(no_key=True, nowait=True).get(pk=pk)
                        cause = raised.exception.__cause__
                        self.assertEqual(getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None), "55P03")
            finally:
                release.set()
            payload = request.result(timeout=15)
        self.assertNotIn("error", payload, payload)
        return payload

    def test_habit_read_retains_authority_through_serialization(self):
        payload = self.assert_held_until_result_returns(
            habits, "_habit_to_dict", "get_habit", {"habit_id": self.habit.pk},
        )
        self.assertEqual(payload["name"], "Saved locked routine")

    def test_habit_create_retains_target_authority_after_native_insert(self):
        payload = self.assert_held_until_result_returns(
            habits, "_habit_to_dict", "create_habit", {"name": "New locked routine", "user_id": self.child.pk},
        )
        self.assertEqual(Habit.objects.get(pk=payload["id"]).user_id, self.child.pk)

    def test_daily_read_retains_authority_through_serialization(self):
        payload = self.assert_held_until_result_returns(
            daily_challenges, "daily_challenge_to_dict", "get_daily_challenge", {"user_id": self.child.pk},
        )
        self.assertEqual(payload["id"], self.daily.pk)

    def test_daily_claim_retains_authority_after_native_payout(self):
        payload = self.assert_held_until_result_returns(
            daily_challenges.DailyChallengeService, "claim_reward", "claim_daily_challenge", {"user_id": self.child.pk},
        )
        self.assertEqual((payload["already_claimed"], payload["coins"]), (False, 11))
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)

    def test_real_user_move_waits_for_habit_list_serialization(self):
        ready, release = Event(), Event()
        pids = {}
        original = habits._habit_to_dict

        def held(habit):
            payload = original(habit)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids["reader"] = cursor.fetchone()[0]
            ready.set()
            if not release.wait(10):
                raise TimeoutError("Routine list was not released")
            return payload

        def move():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids["mover"] = cursor.fetchone()[0]
            user = get_user_model().objects.get(pk=self.child.pk)
            user.family = self.other
            user.save(update_fields=["family"])

        with patch.object(habits, "_habit_to_dict", side_effect=held), ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(self.worker, lambda: self.wire("list_habits", {}))
            mover = None
            try:
                self.assertTrue(ready.wait(5), "Habit list did not reach serialization")
                mover = pool.submit(self.worker, move)
                deadline, blocked = monotonic() + 4, False
                while monotonic() < deadline:
                    if mover.done():
                        mover.result()
                        break
                    if "mover" in pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_blocking_pids(%s)", [pids["mover"]])
                            blocked = pids["reader"] in cursor.fetchone()[0]
                        if blocked:
                            break
                    sleep(0.01)
                self.assertTrue(blocked, "A real family move escaped the habit response's account lock")
            finally:
                release.set()
            payload = reader.result(timeout=15)
            if mover is not None:
                mover.result(timeout=15)
        self.assertNotIn("error", payload, payload)
        self.assertEqual(payload["habits"][0]["id"], self.habit.pk)
        self.assertEqual(get_user_model().objects.get(pk=self.child.pk).family_id, self.other.pk)
        self.assertEqual(self.wire("get_habit", {"habit_id": self.habit.pk})["error"]["code"], "not_found")
