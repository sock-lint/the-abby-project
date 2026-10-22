"""Exact saved challenge reads retain old promises without materializing goals."""
import json
from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pydantic import ValidationError

from apps.mcp_server import challenge_schemas
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import challenges
from apps.quests.goals import _snapshot
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, ChallengePin, Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GetChallengeTests(TestCase):
    def setUp(self):
        household = make_family(
            "Exact MCP challenge", parents=[{"username": "exact-parent", "is_staff": True}],
            children=[{"username": "exact-child"}, {"username": "exact-sibling"}],
        )
        self.parent, self.child, self.sibling = household.parents[0], *household.children
        other = make_family("Other exact challenge", parents=[{"username": "other-exact-parent", "is_staff": True}],
                            children=[{"username": "other-exact-child"}])
        self.other_parent, self.other_child = other.parents[0], other.children[0]

    def params(self, challenge_id, **changes):
        return challenge_schemas.GetChallengeIn(challenge_id=challenge_id, **changes)

    def occurrence(self, child=None, *, untimed=False):
        child = child or self.child
        now = timezone.now()
        definition = QuestDefinition.objects.create(
            name=f"Saved reading {child.pk}", quest_type="collection", target_value=3,
            is_system=True, duration_days=None if untimed else 2,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        goal = ChallengeGoal.objects.create(
            user=child, family=child.family, is_catalog=True, catalog_definition=definition,
            name="The frozen title", description="The accepted promise", metric="count", target=3,
            unit="actions", trigger_filter=definition.trigger_filter, coin_reward=7,
            timezone_name="America/Phoenix", starts_at=now - timedelta(days=10),
            ends_at=None if untimed else now - timedelta(days=8),
        )
        return ChallengeOccurrence.objects.create(
            goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at, snapshot=_snapshot(goal), progress=1,
        )

    def read_without_writes(self, params, actor=None):
        with override_user(actor or self.parent), CaptureQueriesContext(connection) as captured:
            result = challenges.get_challenge(params)
        self.assertFalse(any(row["sql"].lstrip().upper().startswith((
            "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP",
        )) for row in captured))
        self.assertEqual(result, json.loads(json.dumps(result)))
        return result

    def test_old_retry_attempt_is_readable_beyond_the_latest_hundred_without_new_attempts(self):
        occurrence = self.occurrence()
        ChallengeOccurrence.objects.bulk_create([
            ChallengeOccurrence(
                goal=occurrence.goal, starts_at=timezone.now() + timedelta(minutes=index),
                ends_at=timezone.now() + timedelta(days=1, minutes=index), snapshot=occurrence.snapshot,
            ) for index in range(101)
        ])
        # These newer rows deliberately belong to another goal so the expired
        # one-time catalog promise remains eligible for its explicit retry.
        noise = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, name="Later history", metric="count", target=3,
            unit="actions", starts_at=timezone.now(), ends_at=timezone.now() + timedelta(days=1),
        )
        ChallengeOccurrence.objects.exclude(pk=occurrence.pk).update(goal=noise)
        ChallengePin.objects.create(user=self.child, occurrence=occurrence)
        with override_user(self.parent):
            recent = challenges.list_challenges(challenge_schemas.ListChallengesIn(user_id=self.child.pk, limit=100))
        self.assertNotIn(f"goal:{occurrence.pk}", [row["id"] for row in recent["results"]])
        before = list(ChallengeOccurrence.objects.order_by("pk").values())
        result = self.read_without_writes(self.params(f"goal:{occurrence.pk}", user_id=self.child.pk))
        self.assertEqual(result["id"], f"goal:{occurrence.pk}")
        self.assertTrue(result["saved_state_only"])
        self.assertTrue(result["pinned"])
        self.assertEqual(result["retry"], {
            "allowed": True, "reason": None, "latest_attempt_id": f"goal:{occurrence.pk}",
        })
        self.assertEqual(result["qualifying_triggers"], ["reading_logged"])
        self.assertEqual(before, list(ChallengeOccurrence.objects.order_by("pk").values()))
        self.assertFalse(CoinLedger.objects.exists())

    def test_retired_catalog_detail_keeps_frozen_rewards_and_saved_origin(self):
        occurrence = self.occurrence()
        occurrence.goal.catalog_definition.delete()
        ChallengeGoal.objects.filter(pk=occurrence.goal_id).update(name="Edited title", coin_reward=999)
        result = self.read_without_writes(self.params(f"goal:{occurrence.pk}", user_id=self.child.pk))
        self.assertEqual(result["origin"], "catalog")
        self.assertEqual(result["name"], "The frozen title")
        self.assertEqual(result["rewards"]["coins"], 7)
        self.assertEqual(result["retry"]["reason"], "retired")
        self.assertEqual(result["reward_receipt"]["status"], "pending")

    def test_untimed_reading_detail_has_no_deadline_and_cannot_start_a_retry(self):
        occurrence = self.occurrence(untimed=True)
        result = self.read_without_writes(self.params(f"goal:{occurrence.pk}"), actor=self.child)
        self.assertIsNone(result["ends_at"])
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["retry"]["reason"], "not_expired")

    def test_legacy_detail_keeps_saved_reward_items_without_new_quest_or_pin(self):
        occurrence = self.occurrence()
        quest = Quest.objects.create(
            definition=occurrence.goal.catalog_definition, end_date=timezone.now() + timedelta(days=2),
            reward_items_snapshot=[],
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        result = self.read_without_writes(self.params(f"legacy:{quest.pk}", user_id=self.child.pk))
        self.assertEqual(result["origin"], "legacy")
        self.assertIsNone(result["goal_definition_id"])
        self.assertEqual(result["retry"]["reason"], "not_catalog")
        self.assertEqual(Quest.objects.count(), 1)
        self.assertFalse(ChallengePin.objects.exists())

    def test_parent_explicit_selection_child_self_and_foreign_missing_equivalence(self):
        occurrence = self.occurrence()
        foreign = self.occurrence(self.other_child)
        child_result = self.read_without_writes(self.params(f"goal:{occurrence.pk}"), actor=self.child)
        self.assertEqual(child_result["user_id"], self.child.pk)
        with override_user(self.parent):
            with self.assertRaises(MCPValidationError):
                challenges.get_challenge(self.params(f"goal:{occurrence.pk}"))
            for challenge_id in (f"goal:{foreign.pk}", "goal:999999", "legacy:999999"):
                with self.subTest(challenge_id=challenge_id), self.assertRaisesMessage(MCPNotFoundError, "Challenge not found."):
                    challenges.get_challenge(self.params(challenge_id, user_id=self.child.pk))
            with self.assertRaises(MCPNotFoundError):
                challenges.get_challenge(self.params(f"goal:{occurrence.pk}", user_id=self.parent.pk))
        with override_user(self.other_parent), self.assertRaises(MCPNotFoundError):
            challenges.get_challenge(self.params(f"goal:{occurrence.pk}", user_id=self.child.pk))
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            challenges.get_challenge(self.params(f"goal:{occurrence.pk}", user_id=self.sibling.pk))

    def test_stale_actor_permissions_and_target_membership_are_rechecked(self):
        occurrence = self.occurrence()
        User = get_user_model()
        users = User.objects.filter(pk=self.parent.pk)
        original = {"family_id": self.parent.family_id, "role": self.parent.role,
                    "is_active": self.parent.is_active, "is_staff": self.parent.is_staff}
        for changes in ({"family_id": self.other_parent.family_id}, {"role": "child"},
                        {"is_active": False}, {"is_staff": False}):
            users.update(**changes)
            try:
                with self.subTest(changes=changes), override_user(self.parent), self.assertRaises(MCPPermissionDenied):
                    challenges.get_challenge(self.params(f"goal:{occurrence.pk}", user_id=self.child.pk))
            finally:
                users.update(**original)

        from apps.mcp_server.tools.rpg_management import _target
        def move_after_selection(*args, **kwargs):
            result = _target(*args, **kwargs)
            User.objects.filter(pk=self.child.pk).update(family_id=self.other_parent.family_id)
            return result
        with override_user(self.parent), patch(
            "apps.mcp_server.tools.challenges._household_target", side_effect=move_after_selection,
        ), self.assertRaises(MCPNotFoundError):
            challenges.get_challenge(self.params(f"goal:{occurrence.pk}", user_id=self.child.pk))

    def test_detail_input_is_bounded_and_discovery_requires_household_read_scope(self):
        for value in ("goal:0", "legacy:-1", "goal:9223372036854775808", "definition:1", "goal:1 extra"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.params(value)
        entry = mcp._tool_manager.get_tool("get_challenge")
        self.assertIsNotNone(entry)
        self.assertTrue(entry.annotations.readOnlyHint)
        self.assertFalse(entry.annotations.destructiveHint)
        self.assertTrue(entry.annotations.idempotentHint)
        for field in ("id", "name", "status", "retry", "qualifying_triggers", "reward_receipt"):
            self.assertIn(field, entry.fn_metadata.output_schema["properties"])
        with override_user(self.parent, scopes=frozenset({"mcp:read"})):
            self.assertIn("get_challenge", {tool.name for tool in async_to_sync(mcp.list_tools)()})
        with override_user(self.parent, scopes=frozenset({"mcp:catalog"})):
            self.assertNotIn("get_challenge", {tool.name for tool in async_to_sync(mcp.list_tools)()})
