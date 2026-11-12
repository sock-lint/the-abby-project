"""Modern challenge mutations retain household authority through their response."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import OperationalError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.families.models import Family
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import challenges
from apps.quests import goal_views
from apps.quests.goals import create_goal
from apps.quests.models import ChallengeGoal, ChallengePin
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChallengeMutationAuthorityConcurrencyTests(TransactionTestCase):
    def setUp(self):
        home = make_family("Locked challenge family", children=[{"username": "challenge-lock-child"}])
        self.child = home.children[0]
        # The target predates the actor, exercising sorted member admission.
        self.parent = get_user_model().objects.create_user(
            username="challenge-lock-parent", family=home.family, role="parent", is_staff=True,
        )
        self.occurrence = create_goal(self.parent, self.child, {
            **self.fields(), "target": Decimal("3.000"),
        })

    def fields(self, **overrides):
        return {"user_id": self.child.pk, "name": "Three saved habits", "description": "",
                "trigger_type": "habit_log", "metric": "count", "target": "3", "unit": "actions",
                "period": "this_week", "repeat_weekly": False, "coin_reward": 0, "xp_reward": 0,
                "skill_tags": [], **overrides}

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:read", "mcp:write"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    @staticmethod
    def worker(operation):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '12s'")
            return operation()
        finally:
            connection.close()

    def held_response(self, owner, attribute, name, params, *, operation=None):
        ready, release = Event(), Event()
        original = getattr(owner, attribute)

        def held(*args, **kwargs):
            result = original(*args, **kwargs)
            ready.set()
            if not release.wait(10):
                raise TimeoutError("Challenge response was not released")
            return result

        with patch.object(owner, attribute, autospec=True, side_effect=held), ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(self.worker, operation or (lambda: self.wire(name, params)))
            try:
                self.assertTrue(ready.wait(5), "Registered request did not reach its response")
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

    def test_preview_retains_authority_during_validation(self):
        result = self.held_response(
            challenges.GoalWriteSerializer, "is_valid", "preview_challenge_goal", self.fields(),
        )
        self.assertTrue(result["valid"])
        self.assertEqual(ChallengeGoal.objects.count(), 1)

    def test_create_retains_authority_through_serialization(self):
        result = self.held_response(challenges, "occurrence_payload", "create_challenge_goal", self.fields(
            name="A new locked goal", request_id=str(uuid4()),
        ))
        self.assertTrue(result["id"].startswith("goal:"))
        self.assertEqual(ChallengeGoal.objects.count(), 2)
        self.assertFalse(CoinLedger.objects.exists())

    def test_uuid_recovery_retains_authority_through_serialization(self):
        params = self.fields(name="Recover the locked goal", request_id=str(uuid4()))
        original = self.wire("create_challenge_goal", params)
        self.assertNotIn("error", original, original)
        count = ChallengeGoal.objects.count()
        result = self.held_response(challenges, "occurrence_payload", "create_challenge_goal", params)
        self.assertEqual(result["id"], original["id"])
        self.assertEqual(ChallengeGoal.objects.count(), count)
        self.assertFalse(CoinLedger.objects.exists())

    def test_rest_create_retains_authority_through_serialization(self):
        def create():
            client = APIClient()
            client.force_authenticate(self.parent)
            response = client.post("/api/challenges/goals/", self.fields(
                name="A REST locked goal", request_id=str(uuid4()),
            ), format="json")
            self.assertEqual(response.status_code, 201, response.data)
            return response.data

        result = self.held_response(goal_views, "occurrence_payload", None, None, operation=create)
        self.assertTrue(result["id"].startswith("goal:"))
        self.assertEqual(ChallengeGoal.objects.count(), 2)
        self.assertFalse(CoinLedger.objects.exists())

    def test_pin_retains_actor_and_target_authority_after_native_save(self):
        challenge_id = f"goal:{self.occurrence.pk}"
        result = self.held_response(challenges, "set_pin", "pin_challenge", {
            "user_id": self.child.pk, "challenge_id": challenge_id,
        })
        self.assertEqual(result["pin"], challenge_id)
        self.assertEqual(ChallengePin.objects.get(user=self.child).occurrence_id, self.occurrence.pk)

    def test_unpin_retains_actor_and_target_authority_after_native_save(self):
        ChallengePin.objects.create(user=self.child, occurrence=self.occurrence)
        result = self.held_response(challenges, "set_pin", "unpin_challenge", {
            "user_id": self.child.pk, "challenge_id": f"goal:{self.occurrence.pk}",
        })
        self.assertIsNone(result["pin"])
        self.assertIsNone(ChallengePin.objects.get(user=self.child).occurrence_id)
