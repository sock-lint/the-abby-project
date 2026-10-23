"""Multi-child and entry-ID operations hold one ordered household authority batch."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import quests, rewards
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger, Reward
from apps.rewards.services import CoinService, RewardService
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RemainingRPGAuthorityConcurrencyTests(TransactionTestCase):
    def setUp(self):
        # Older children make actor-first nested guards take IDs out of order.
        home = make_family("Ordered RPG household", children=[{"username": "ordered-rpg-child"},
                                                                {"username": "ordered-rpg-sibling"}])
        self.child, self.sibling = home.children
        self.actor = get_user_model().objects.create_user(username="ordered-rpg-parent", family=home.family,
                                                         role="parent", is_staff=True)
        self.other = make_family("Next ordered household").family
        self.definition = QuestDefinition.objects.create(name="Ordered shared practice", quest_type="boss",
                                                         target_value=100, is_system=True, is_cooperative=True)
        self.reward = Reward.objects.create(family=home.family, name="Saved ordered promise", cost_coins=5,
                                           stock=3, requires_parent_approval=True)
        CoinService.award_coins(self.child, 50, CoinLedger.Reason.ADJUSTMENT)
        self.redemption = RewardService.request_redemption(self.child, self.reward)

    def wire(self, name, params):
        with override_user(self.actor, scopes=frozenset({"mcp:read", "mcp:write"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def worker(self, call):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '12s'")
            return call()
        finally:
            connection.close()

    def assert_move_waits(self, module, attribute, name, params, target):
        ready, release = Event(), Event()
        pids = {}
        original = getattr(module, attribute)

        def held(*args, **kwargs):
            result = original(*args, **kwargs)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids["request"] = cursor.fetchone()[0]
            ready.set()
            if not release.wait(10):
                raise TimeoutError("Household operation was not released")
            return result

        def move():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids["move"] = cursor.fetchone()[0]
            member = get_user_model().objects.get(pk=target.pk)
            member.family = self.other
            member.save(update_fields=["family"])

        with patch.object(module, attribute, side_effect=held), ThreadPoolExecutor(max_workers=2) as pool:
            request = pool.submit(self.worker, lambda: self.wire(name, params))
            mover = None
            try:
                self.assertTrue(ready.wait(5), "SDK operation did not reach its serialized result")
                mover = pool.submit(self.worker, move)
                deadline, blocked = monotonic() + 4, False
                while monotonic() < deadline:
                    if mover.done():
                        mover.result()
                        break
                    if "move" in pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_blocking_pids(%s)", [pids["move"]])
                            blocked = pids["request"] in cursor.fetchone()[0]
                        if blocked:
                            break
                    sleep(0.01)
                self.assertTrue(blocked, "Family move escaped current-authority locks before serialization returned")
            finally:
                release.set()
            payload = request.result(timeout=15)
            if mover is not None:
                mover.result(timeout=15)
        self.assertNotIn("error", payload, payload)
        self.assertEqual(get_user_model().objects.get(pk=target.pk).family_id, self.other.pk)
        return payload

    def test_coop_keeps_every_participant_locked_after_native_start(self):
        payload = self.assert_move_waits(quests, "_quest_to_dict", "assign_co_op_quest", {
            "definition_id": self.definition.pk, "user_ids": [self.child.pk, self.sibling.pk],
        }, self.sibling)
        self.assertEqual(Quest.objects.get(pk=payload["id"]).participants.count(), 2)
        self.assertEqual({row["user"] for row in payload["participants"]}, {self.child.pk, self.sibling.pk})

    def test_redemption_entry_keeps_subject_locked_through_receipt_serialization(self):
        payload = self.assert_move_waits(rewards, "redemption_to_dict", "approve_redemption", {
            "redemption_id": self.redemption.pk,
        }, self.child)
        self.assertEqual(payload["status"], "approved")
        denied = self.wire("approve_redemption", {"redemption_id": self.redemption.pk})
        self.assertEqual(denied["error"]["code"], "not_found")

    def test_quest_entry_keeps_current_participant_locked_through_history_serialization(self):
        quest = Quest.objects.create(definition=self.definition, status="completed",
                                    end_date=timezone.now() + timedelta(days=7))
        QuestParticipant.objects.create(quest=quest, user=self.child, contribution=7)
        payload = self.assert_move_waits(quests, "_quest_to_dict", "get_quest", {"quest_id": quest.pk}, self.child)
        self.assertEqual(payload["participants"][0]["contribution"], 7)
        self.assertEqual(self.wire("get_quest", {"quest_id": quest.pk})["error"]["code"], "not_found")
