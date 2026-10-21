"""Household RPG management preserves saved promises and server decisions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.models import MCPMutationReceipt
from apps.mcp_server.server import mcp
from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount
from apps.quests.goals import create_goal, ingest_activity, list_goals, set_pin
from apps.quests.models import ChallengeOccurrence, ChallengeSchedule
from apps.rewards.models import CoinLedger, Reward
from apps.rewards.services import CoinService, RewardService
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


MANAGEMENT_TOOLS = {
    "retry_challenge", "update_challenge_schedule", "list_expeditions", "get_expedition",
    "start_expedition", "claim_expedition", "list_reward_redemptions", "get_reward_redemption",
    "deliver_reward_redemption",
}


class RPGManagementRegistryTests(SimpleTestCase):
    def test_household_management_tools_are_registered(self):
        self.assertTrue(MANAGEMENT_TOOLS.issubset({entry.name for entry in mcp._tool_manager.list_tools()}))

    def test_all_management_results_advertise_real_fields(self):
        expected = {
            "retry_challenge": "retry_of", "update_challenge_schedule": "schedule",
            "list_expeditions": "expeditions", "get_expedition": "loot", "start_expedition": "loot",
            "claim_expedition": "freshly_claimed", "list_reward_redemptions": "redemptions",
            "get_reward_redemption": "delivered_at", "deliver_reward_redemption": "delivered_at",
        }
        for name, field in expected.items():
            with self.subTest(name=name):
                schema = mcp._tool_manager.get_tool(name).fn_metadata.output_schema
                self.assertIn(field, schema.get("properties", {}))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RPGManagementTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 20, 19, tzinfo=datetime_timezone.utc)
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "MCP household RPG", parents=[{"username": "management-parent", "is_staff": True}],
            children=[{"username": "management-child"}, {"username": "management-sibling"}],
        )
        self.parent, self.child, self.sibling = household.parents[0], *household.children
        foreign = make_family(
            "Foreign household RPG", parents=[{"username": "foreign-management-parent", "is_staff": True}],
            children=[{"username": "foreign-management-child"}],
        )
        self.foreign_parent, self.foreign_child = foreign.parents[0], foreign.children[0]
        species = PetSpecies.objects.create(slug="management-legacy", name="Management companion")
        potion = PotionType.objects.create(slug="base", name="Base")
        self.mount = UserMount.objects.create(user=self.child, species=species, potion=potion)
        self.sibling_mount = UserMount.objects.create(user=self.sibling, species=species, potion=potion)
        self.food = ItemDefinition.objects.create(slug="management-food", name="Training snack", item_type="food")
        DropTable.objects.create(trigger_type="expedition_returned", item=self.food, weight=10)
        self.reward = Reward.objects.create(family=self.parent.family, name="A real-world outing", cost_coins=10, stock=10)

    def tools(self):
        from apps.mcp_server.tools import rpg_management
        return rpg_management

    def inputs(self):
        from apps.mcp_server import rpg_management_schemas
        return rpg_management_schemas

    def start(self, **overrides):
        return self.inputs().StartExpeditionIn(**{
            "mount_id": self.mount.pk, "tier": "short", "request_id": uuid4(), **overrides,
        })

    def make_trip(self, *, user=None, ready=True, status="active"):
        mount = self.mount if user is None or user == self.child else self.sibling_mount
        return MountExpedition.objects.create(
            mount=mount, tier="short", status=status, started_at=self.now - timedelta(hours=3),
            returns_at=self.now - timedelta(hours=1) if ready else self.now + timedelta(hours=1),
            loot={"coins": 15, "items": [{"item_id": self.food.pk, "quantity": 1}]},
        )

    def make_redemption(self, *, child=None, approved=False, kind="real_world"):
        child = child or self.child
        reward = self.reward
        if kind != "real_world":
            reward = Reward.objects.create(
                family=self.parent.family, name=f"A saved {kind} gift", cost_coins=10,
                fulfillment_kind=kind, item_definition=self.food,
            )
        CoinService.award_coins(child, 50, CoinLedger.Reason.ADJUSTMENT)
        row = RewardService.request_redemption(child, reward)
        if approved:
            row = RewardService.approve(row, self.parent)
        return row

    def test_retry_catalog_contention_is_retryable_without_a_successor(self):
        from apps.quests.availability import RetryCatalogBusy
        original = self.catalog_attempt()
        original.snapshot["items"] = [{"item_id": self.food.pk, "quantity": 1}]
        original.save(update_fields=["snapshot"])
        with override_user(self.parent), patch(
            "apps.quests.controls.lock_retry_reward_catalog",
            side_effect=RetryCatalogBusy("Reward catalog is changing. Refresh and try again."),
        ):
            result = async_to_sync(mcp.call_tool)("retry_challenge", {"params": {
                "challenge_id": f"goal:{original.pk}", "user_id": self.child.pk,
            }, "confirmation": True})
        payload = result.structuredContent if hasattr(result, "structuredContent") else result[1]
        self.assertEqual(payload["error"]["code"], "retry_conflict")
        self.assertIs(payload["error"]["retryable"], True)
        self.assertEqual(payload["error"]["message"], "Reward catalog is changing. Refresh and try again.")
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=original).exists())

    def test_unavailable_retry_reward_is_not_a_transient_transport_conflict(self):
        original = self.catalog_attempt()
        original.snapshot["items"] = [{"item_id": self.food.pk, "quantity": 1}]
        original.save(update_fields=["snapshot"])
        with override_user(self.parent), patch("apps.quests.availability.item_is_available", return_value=False):
            result = async_to_sync(mcp.call_tool)("retry_challenge", {"params": {
                "challenge_id": f"goal:{original.pk}", "user_id": self.child.pk,
            }, "confirmation": True})
        payload = result.structuredContent if hasattr(result, "structuredContent") else result[1]
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["message"], "reward_unavailable")
        self.assertIs(payload["error"]["retryable"], False)
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=original).exists())

    def catalog_attempt(self):
        from apps.quests.models import QuestDefinition
        with patch("django.utils.timezone.now", return_value=self.now - timedelta(days=10)):
            QuestDefinition.objects.create(
                name="An expired catalog goal", quest_type="collection", target_value=2, duration_days=2,
                is_system=True, coin_reward=7, trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            list_goals(self.child)
        return ChallengeOccurrence.objects.get(goal__user=self.child)

    def weekly(self):
        return create_goal(self.parent, self.child, {
            "name": "Weekly chores", "description": "Current promise", "metric": "count", "target": Decimal(2),
            "unit": "actions", "trigger_type": "chore_complete", "period": "this_week", "repeat_weekly": True,
            "coin_reward": 3, "xp_reward": 0, "skill_tags": [],
        })

    def test_parent_selection_and_child_family_boundaries_apply_to_all_tools(self):
        ins, tools = self.inputs(), self.tools()
        for actor, selected, error in (
            (self.parent, None, MCPValidationError),
            (self.parent, self.parent.pk, MCPNotFoundError),
            (self.foreign_parent, self.child.pk, MCPNotFoundError),
            (self.child, self.sibling.pk, MCPPermissionDenied),
            (None, None, MCPPermissionDenied),
        ):
            calls = (
                lambda: tools.retry_challenge(ins.RetryChallengeIn(user_id=selected, challenge_id="goal:1")),
                lambda: tools.update_challenge_schedule(ins.UpdateChallengeScheduleIn(
                    user_id=selected, goal_definition_id=1, expected_revision=0, request_id=uuid4(), paused=True)),
                lambda: tools.list_expeditions(ins.ListExpeditionsIn(user_id=selected)),
                lambda: tools.get_expedition(ins.GetExpeditionIn(user_id=selected, expedition_id=1)),
                lambda: tools.start_expedition(self.start(user_id=selected)),
                lambda: tools.claim_expedition(ins.ClaimExpeditionIn(user_id=selected, expedition_id=1)),
                lambda: tools.list_reward_redemptions(ins.ListRewardRedemptionsIn(user_id=selected)),
                lambda: tools.get_reward_redemption(ins.GetRewardRedemptionIn(user_id=selected, redemption_id=1)),
                lambda: tools.deliver_reward_redemption(ins.DeliverRewardRedemptionIn(user_id=selected, redemption_id=1)),
            )
            with self.subTest(actor=actor, selected=selected), override_user(actor):
                for call in calls:
                    with self.assertRaises(error):
                        call()
        self.assertFalse(MCPMutationReceipt.objects.exists())
        self.assertFalse(MountExpedition.objects.exists())

    def test_read_scope_hides_writes_and_writes_require_confirmation(self):
        reads = {"list_expeditions", "get_expedition", "list_reward_redemptions", "get_reward_redemption"}
        with override_user(self.parent, scopes=frozenset({"mcp:read"})):
            names = {entry.name for entry in async_to_sync(mcp.list_tools)()}
            denied = async_to_sync(mcp.call_tool)("start_expedition", {"params": {}})
        self.assertTrue(reads.issubset(names))
        self.assertTrue((MANAGEMENT_TOOLS - reads).isdisjoint(names))
        self.assertEqual(denied.structuredContent["error"]["code"], "permission_denied")
        ins = self.inputs()
        writes = {
            "start_expedition": self.start(user_id=self.child.pk),
            "retry_challenge": ins.RetryChallengeIn(user_id=self.child.pk, challenge_id="goal:1"),
            "update_challenge_schedule": ins.UpdateChallengeScheduleIn(
                user_id=self.child.pk, goal_definition_id=1, expected_revision=0, request_id=uuid4(), paused=True,
            ),
            "claim_expedition": ins.ClaimExpeditionIn(user_id=self.child.pk, expedition_id=1),
            "deliver_reward_redemption": ins.DeliverRewardRedemptionIn(user_id=self.child.pk, redemption_id=1),
        }
        with override_user(self.parent, scopes=frozenset({"mcp:write"})):
            for name, params in writes.items():
                for acknowledgement in ({}, {"confirmation": False}, {"confirmation": "true"}):
                    with self.subTest(name=name, acknowledgement=acknowledgement):
                        result = async_to_sync(mcp.call_tool)(name, {
                            "params": params.model_dump(mode="json", exclude_none=True), **acknowledgement,
                        })
                        self.assertTrue(result.isError)
                        code = "invalid_input" if acknowledgement.get("confirmation") == "true" else "confirmation_required"
                        self.assertEqual(result.structuredContent["error"]["code"], code)
        self.assertFalse(MountExpedition.objects.exists())

    def read_calls(self, trip, redemption):
        return {
            "list_expeditions": {"user_id": self.child.pk},
            "get_expedition": {"user_id": self.child.pk, "expedition_id": trip.pk},
            "list_reward_redemptions": {"user_id": self.child.pk},
            "get_reward_redemption": {"user_id": self.child.pk, "redemption_id": redemption.pk},
        }

    def test_read_transport_rechecks_stale_actor_membership_role_and_activity(self):
        trip, redemption = self.make_trip(), self.make_redemption()
        actors = type(self.parent).objects.filter(pk=self.parent.pk)
        original = {"family_id": self.parent.family_id, "role": self.parent.role,
                    "is_active": self.parent.is_active, "is_staff": self.parent.is_staff}
        for changes in (
            {"family_id": self.foreign_parent.family_id}, {"role": "child"},
            {"is_active": False}, {"is_staff": False},
        ):
            actors.update(**changes)
            try:
                for name, params in self.read_calls(trip, redemption).items():
                    with self.subTest(changes=changes, tool=name), override_user(
                        self.parent, scopes=frozenset({"mcp:read"}),
                    ):
                        result = async_to_sync(mcp.call_tool)(name, {"params": params})
                        self.assertTrue(getattr(result, "isError", False), "A stale actor retained household read access.")
                        self.assertEqual(set(result.structuredContent), {"error"})
                        self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")
            finally:
                actors.update(**original)

    def test_read_transport_rechecks_target_changes_after_initial_selection(self):
        trip, redemption = self.make_trip(), self.make_redemption()
        targets = type(self.child).objects.filter(pk=self.child.pk)
        original = {"family_id": self.child.family_id, "role": self.child.role,
                    "is_active": self.child.is_active}
        select_target = self.tools()._target
        for changes in (
            {"family_id": self.foreign_parent.family_id}, {"role": "parent"}, {"is_active": False},
        ):
            def select_then_change(user_id, **kwargs):
                actor, target = select_target(user_id, **kwargs)
                targets.update(**changes)
                return actor, target

            for name, params in self.read_calls(trip, redemption).items():
                try:
                    with self.subTest(changes=changes, tool=name), override_user(
                        self.parent, scopes=frozenset({"mcp:read"}),
                    ), patch.object(self.tools(), "_target", side_effect=select_then_change):
                        result = async_to_sync(mcp.call_tool)(name, {"params": params})
                        if changes.get("is_active") is False:
                            self.assertFalse(getattr(result, "isError", False), "Inactive children retain readable history.")
                        else:
                            self.assertTrue(getattr(result, "isError", False), "A changed target retained household read access.")
                            self.assertEqual(set(result.structuredContent), {"error"})
                            self.assertEqual(result.structuredContent["error"]["code"], "not_found")
                finally:
                    targets.update(**original)

    def test_inactive_child_history_is_readable_but_all_management_writes_stay_denied(self):
        original, weekly = self.catalog_attempt(), self.weekly()
        trip, redemption = self.make_trip(), self.make_redemption(approved=True)
        before_coins = list(CoinLedger.objects.values_list("pk", "amount"))
        type(self.child).objects.filter(pk=self.child.pk).update(is_active=False)
        for name, params in self.read_calls(trip, redemption).items():
            with self.subTest(read=name), override_user(self.parent, scopes=frozenset({"mcp:read"})):
                result = async_to_sync(mcp.call_tool)(name, {"params": params})
                self.assertFalse(getattr(result, "isError", False), "Inactive children retain readable history.")
                payload = result.structuredContent if hasattr(result, "structuredContent") else result[1]
                if name.startswith("list_"):
                    rows = payload["expeditions" if name == "list_expeditions" else "redemptions"]
                    self.assertEqual([row["id"] for row in rows], [trip.pk if name == "list_expeditions" else redemption.pk])
                else:
                    self.assertEqual(payload["id"], trip.pk if name == "get_expedition" else redemption.pk)
        writes = {
            "retry_challenge": {"challenge_id": f"goal:{original.pk}"},
            "update_challenge_schedule": {"goal_definition_id": weekly.goal_id, "expected_revision": 0,
                                          "request_id": str(uuid4()), "paused": True},
            "start_expedition": {"mount_id": self.mount.pk, "tier": "short", "request_id": str(uuid4())},
            "claim_expedition": {"expedition_id": trip.pk},
            "deliver_reward_redemption": {"redemption_id": redemption.pk},
        }
        for name, params in writes.items():
            with self.subTest(write=name), override_user(self.parent, scopes=frozenset({"mcp:write"})):
                result = async_to_sync(mcp.call_tool)(name, {
                    "params": {"user_id": self.child.pk, **params}, "confirmation": True,
                })
                self.assertTrue(result.isError)
                self.assertEqual(result.structuredContent["error"]["code"], "not_found")
        self.assertEqual(list(CoinLedger.objects.values_list("pk", "amount")), before_coins)
        self.assertFalse(MCPMutationReceipt.objects.exists())
        trip.refresh_from_db()
        redemption.refresh_from_db()
        self.assertEqual(trip.status, "active")
        self.assertEqual(redemption.status, "approved")

    def test_expired_catalog_retry_is_exact_and_never_replays_old_sources(self):
        original = self.catalog_attempt()
        snapshot = deepcopy(original.snapshot)
        ingest_activity(self.child, "chore_complete", "old", "chore_complete", occurred_at=original.starts_at + timedelta(hours=1))
        set_pin(self.child, f"goal:{original.pk}")
        params = self.inputs().RetryChallengeIn(user_id=self.child.pk, challenge_id=f"goal:{original.pk}")
        with override_user(self.parent):
            result = self.tools().retry_challenge(params)
            replay = self.tools().retry_challenge(params)
        self.assertEqual(result, replay)
        self.assertEqual(result["retry_of"], f"goal:{original.pk}")
        self.assertEqual(result["progress"], "0")
        self.assertTrue(result["pinned"])
        original.refresh_from_db()
        self.assertEqual(original.snapshot, snapshot)
        self.assertEqual(ChallengeOccurrence.objects.count(), 2)
        self.assertFalse(CoinLedger.objects.exists())
        ingest_activity(self.child, "chore_complete", "old", "chore_complete", occurred_at=self.now)
        successor = ChallengeOccurrence.objects.get(retry_of=original)
        self.assertEqual(successor.progress, 0)
        set_pin(self.child, f"goal:{successor.pk}", clear=True)
        with override_user(self.parent):
            self.assertFalse(self.tools().retry_challenge(params)["pinned"])

    def test_retry_rejects_active_parent_goal_and_wrong_selected_child_without_changes(self):
        original = self.weekly()
        ins = self.inputs()
        with override_user(self.parent):
            with self.assertRaises(MCPValidationError):
                self.tools().retry_challenge(ins.RetryChallengeIn(user_id=self.child.pk, challenge_id=f"goal:{original.pk}"))
            with self.assertRaises(MCPNotFoundError):
                self.tools().retry_challenge(ins.RetryChallengeIn(user_id=self.sibling.pk, challenge_id=f"goal:{original.pk}"))
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_weekly_schedule_uuid_retry_revision_and_frozen_current_promise(self):
        original = self.weekly()
        saved = deepcopy(original.snapshot)
        params = self.inputs().UpdateChallengeScheduleIn(
            user_id=self.child.pk, goal_definition_id=original.goal_id, expected_revision=0, request_id=uuid4(),
            next_week={"target": "4", "coin_reward": 9, "name": "Future chores"},
        )
        with override_user(self.parent):
            first = self.tools().update_challenge_schedule(params)
            self.assertEqual(self.tools().update_challenge_schedule(params), first)
            self.assertEqual(first["schedule"]["revision"], 1)
            self.assertEqual(first["schedule"]["next_week"]["target"], "4")
            self.assertEqual(first["schedule"]["next_week"]["coin_reward"], 9)
            with self.assertRaisesMessage(MCPValidationError, "changed"):
                self.tools().update_challenge_schedule(params.model_copy(update={"request_id": uuid4()}))
            with self.assertRaises(MCPValidationError) as conflict:
                self.tools().update_challenge_schedule(params.model_copy(update={"paused": True}))
            self.assertEqual(conflict.exception.code, "idempotency_conflict")
        original.refresh_from_db()
        self.assertEqual(original.snapshot, saved)
        self.assertEqual(ChallengeSchedule.objects.count(), 1)
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_schedule_pause_resume_and_bad_next_week_fields_do_not_award(self):
        original = self.weekly()
        ins = self.inputs()
        with override_user(self.parent):
            pause = self.tools().update_challenge_schedule(ins.UpdateChallengeScheduleIn(
                user_id=self.child.pk, goal_definition_id=original.goal_id,
                request_id=uuid4(), expected_revision=0, paused=True,
            ))
            self.assertTrue(pause["schedule"]["next_week"]["paused"])
            resume = self.tools().update_challenge_schedule(ins.UpdateChallengeScheduleIn(
                user_id=self.child.pk, goal_definition_id=original.goal_id,
                request_id=uuid4(), expected_revision=1, paused=False,
            ))
            self.assertFalse(resume["schedule"]["next_week"]["paused"])
            for fields in ({}, {"next_week": {"target": "0.5"}}, {"next_week": {"xp_reward": 10, "skill_tags": []}}):
                with self.subTest(fields=fields), self.assertRaises(MCPValidationError):
                    self.tools().update_challenge_schedule(ins.UpdateChallengeScheduleIn(
                        user_id=self.child.pk, goal_definition_id=original.goal_id,
                        request_id=uuid4(), expected_revision=2, **fields,
                    ))
        original.goal.refresh_from_db()
        self.assertEqual(original.goal.schedule_revision, 2)
        self.assertEqual(MCPMutationReceipt.objects.count(), 2)
        self.assertFalse(CoinLedger.objects.exists())
        with self.assertRaises(ValidationError):
            ins.FutureChallengeSetupIn(metric="distance")

    def test_schedule_preserves_an_already_accepted_future_occurrence(self):
        from apps.quests.controls import week_start
        from apps.quests.goals import _occurrence
        current = self.weekly()
        next_monday = week_start(current.goal, self.now) + timedelta(days=7)
        accepted_future = _occurrence(current.goal, next_monday + timedelta(hours=1))
        snapshots = deepcopy(current.snapshot), deepcopy(accepted_future.snapshot)
        with override_user(self.parent):
            self.tools().update_challenge_schedule(self.inputs().UpdateChallengeScheduleIn(
                user_id=self.child.pk, goal_definition_id=current.goal_id,
                expected_revision=0, request_id=uuid4(), next_week={"target": "9", "coin_reward": 11},
            ))
        current.refresh_from_db()
        accepted_future.refresh_from_db()
        self.assertEqual((current.snapshot, accepted_future.snapshot), snapshots)
        self.assertFalse(CoinLedger.objects.exists())

    def test_pure_pause_can_preserve_a_deleted_reward_skill_but_resume_validates(self):
        from apps.achievements.models import Skill, SkillCategory
        skill = Skill.objects.create(name="Saved schedule skill", category=SkillCategory.objects.create(name="Saved schedule"))
        current = create_goal(self.parent, self.child, {
            "name": "Legacy skill promise", "metric": "count", "target": Decimal(2), "unit": "actions",
            "trigger_type": "chore_complete", "period": "this_week", "repeat_weekly": True,
            "xp_reward": 5, "skill_tags": [{"skill_id": skill.pk, "xp_weight": 1}],
        })
        snapshot = deepcopy(current.snapshot)
        skill.delete()
        with override_user(self.parent):
            pause = self.tools().update_challenge_schedule(self.inputs().UpdateChallengeScheduleIn(
                user_id=self.child.pk, goal_definition_id=current.goal_id,
                expected_revision=0, request_id=uuid4(), paused=True,
            ))
            self.assertTrue(pause["schedule"]["next_week"]["paused"])
            with self.assertRaises(MCPValidationError):
                self.tools().update_challenge_schedule(self.inputs().UpdateChallengeScheduleIn(
                    user_id=self.child.pk, goal_definition_id=current.goal_id,
                    expected_revision=1, request_id=uuid4(), paused=False,
                ))
        current.refresh_from_db()
        self.assertEqual(current.snapshot, snapshot)
        self.assertEqual(MCPMutationReceipt.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_start_uuid_preserves_frozen_loot_and_claim_cannot_pay_twice(self):
        params = self.start(user_id=self.child.pk)
        with override_user(self.parent), patch("apps.pets.expeditions.ExpeditionService._roll_loot", wraps=ExpeditionService._roll_loot) as roll:
            first = self.tools().start_expedition(params)
            with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=2)):
                replay = self.tools().start_expedition(params)
            self.assertEqual(first, replay)
            self.assertEqual(roll.call_count, 1)
            with self.assertRaises(MCPValidationError) as conflict:
                self.tools().start_expedition(params.model_copy(update={"tier": "long"}))
            self.assertEqual(conflict.exception.code, "idempotency_conflict")
            claim = self.inputs().ClaimExpeditionIn(user_id=self.child.pk, expedition_id=first["id"])
            with self.assertRaises(MCPValidationError):
                self.tools().claim_expedition(claim)
        self.assertFalse(CoinLedger.objects.exists())
        trip = MountExpedition.objects.get(pk=first["id"])
        frozen = deepcopy(trip.loot)
        with override_user(self.parent), patch("django.utils.timezone.now", return_value=self.now + timedelta(hours=3)):
            result = self.tools().claim_expedition(claim)
            replay = self.tools().claim_expedition(claim)
        self.assertEqual(result["items"], replay["items"])
        self.assertTrue(result["freshly_claimed"])
        self.assertFalse(replay["freshly_claimed"])
        self.assertEqual(replay["coins_awarded"], 0)
        self.assertEqual(CoinLedger.objects.filter(reason="expedition").count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 1)
        trip.refresh_from_db()
        self.assertEqual(trip.loot, frozen)

    def test_launch_service_allowance_wrong_mount_and_deletion_tombstone(self):
        with override_user(self.parent):
            with self.assertRaises(MCPNotFoundError):
                self.tools().start_expedition(self.start(user_id=self.child.pk, mount_id=self.sibling_mount.pk))
            params = self.start(user_id=self.child.pk)
            result = self.tools().start_expedition(params)
            with self.assertRaises(MCPValidationError):
                self.tools().start_expedition(self.start(user_id=self.child.pk))
            MountExpedition.objects.filter(pk=result["id"]).delete()
            with self.assertRaises(MCPNotFoundError):
                self.tools().start_expedition(params)
        self.assertFalse(MountExpedition.objects.exists())
        self.assertIsNone(MCPMutationReceipt.objects.get(operation="start_expedition").response)

    def test_read_history_is_paginated_target_bound_and_never_claims_or_delivers(self):
        ready = self.make_trip()
        self.make_trip(user=self.sibling)
        pending = self.make_redemption()
        ins, tools = self.inputs(), self.tools()
        with override_user(self.parent), CaptureQueriesContext(connection) as queries:
            trips = tools.list_expeditions(ins.ListExpeditionsIn(user_id=self.child.pk, ready_only=True))
            trip = tools.get_expedition(ins.GetExpeditionIn(user_id=self.child.pk, expedition_id=ready.pk))
            rewards = tools.list_reward_redemptions(ins.ListRewardRedemptionsIn(user_id=self.child.pk))
            reward = tools.get_reward_redemption(ins.GetRewardRedemptionIn(user_id=self.child.pk, redemption_id=pending.pk))
        writes = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(writes, [])
        self.assertEqual(trips["expeditions"], [trip])
        self.assertEqual(trip["loot"], ready.loot)
        self.assertTrue(trip["is_ready"])
        self.assertEqual(rewards["redemptions"], [reward])
        self.assertEqual(reward["status"], "pending")
        self.assertEqual(CoinLedger.objects.filter(reason="expedition").count(), 0)
        self.assertFalse(UserInventory.objects.exists())

    def test_redemption_history_cursor_preserves_all_rows_and_rejects_target_switch(self):
        first = self.make_redemption()
        second = self.make_redemption()
        third = self.make_redemption()
        ins, tools = self.inputs(), self.tools()
        with override_user(self.parent):
            page = tools.list_reward_redemptions(ins.ListRewardRedemptionsIn(user_id=self.child.pk, limit=2))
            self.make_redemption()
            later = tools.list_reward_redemptions(ins.ListRewardRedemptionsIn(
                user_id=self.child.pk, limit=2, cursor=page["next_cursor"],
            ))
            with self.assertRaises(MCPValidationError):
                tools.list_reward_redemptions(ins.ListRewardRedemptionsIn(
                    user_id=self.sibling.pk, limit=2, cursor=page["next_cursor"],
                ))
        self.assertEqual([row["id"] for row in page["redemptions"] + later["redemptions"]], [third.pk, second.pk, first.pk])
        self.assertFalse(later["has_more"])
        self.assertEqual(later["total"], 3)

    def test_explicit_delivery_retains_accepted_both_promise_and_digital_grant_once(self):
        row = self.make_redemption(approved=True, kind="both")
        before_coins = list(CoinLedger.objects.values_list("pk", "amount"))
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 1)
        row.reward.cost_coins = 999
        row.reward.fulfillment_kind = "real_world"
        row.reward.save()
        params = self.inputs().DeliverRewardRedemptionIn(user_id=self.child.pk, redemption_id=row.pk)
        with override_user(self.parent):
            delivered = self.tools().deliver_reward_redemption(params)
            replay = self.tools().deliver_reward_redemption(params)
        self.assertEqual(delivered, replay)
        self.assertEqual(delivered["status"], "fulfilled")
        self.assertEqual(delivered["reward"]["fulfillment_kind"], "both")
        self.assertEqual(delivered["reward"]["cost_coins"], 10)
        self.assertIsNotNone(delivered["delivered_at"])
        self.assertEqual(delivered["delivered_by"], self.parent.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.food).quantity, 1)
        self.assertEqual(list(CoinLedger.objects.values_list("pk", "amount")), before_coins)

    def test_pending_delivery_and_wrong_selected_child_fail_without_mutation(self):
        row = self.make_redemption()
        ins, tools = self.inputs(), self.tools()
        with override_user(self.parent):
            with self.assertRaises(MCPValidationError):
                tools.deliver_reward_redemption(ins.DeliverRewardRedemptionIn(user_id=self.child.pk, redemption_id=row.pk))
            with self.assertRaises(MCPNotFoundError):
                tools.get_reward_redemption(ins.GetRewardRedemptionIn(user_id=self.sibling.pk, redemption_id=row.pk))
            with self.assertRaises(MCPNotFoundError):
                tools.deliver_reward_redemption(ins.DeliverRewardRedemptionIn(user_id=self.sibling.pk, redemption_id=row.pk))
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            tools.deliver_reward_redemption(ins.DeliverRewardRedemptionIn(redemption_id=row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, "pending")
        self.assertIsNone(row.delivered_at)

    def test_failed_launch_or_schedule_does_not_save_a_retry_receipt(self):
        params = self.start(user_id=self.child.pk)
        with override_user(self.parent), patch("apps.pets.expeditions.ExpeditionService._roll_loot", side_effect=RuntimeError("Synthetic roll failure")):
            with self.assertRaisesMessage(RuntimeError, "Synthetic roll failure"):
                self.tools().start_expedition(params)
        self.assertFalse(MountExpedition.objects.exists())
        self.assertFalse(MCPMutationReceipt.objects.exists())
        with override_user(self.parent):
            self.tools().start_expedition(params)
        self.assertEqual(MountExpedition.objects.count(), 1)
        self.assertEqual(MCPMutationReceipt.objects.count(), 1)

    def test_writes_recheck_current_actor_permissions_and_target_membership(self):
        original = self.catalog_attempt()
        weekly = self.weekly()
        trip = self.make_trip()
        reward = self.make_redemption(approved=True)
        ins, tools = self.inputs(), self.tools()
        calls = (
            lambda: tools.retry_challenge(ins.RetryChallengeIn(user_id=self.child.pk, challenge_id=f"goal:{original.pk}")),
            lambda: tools.update_challenge_schedule(ins.UpdateChallengeScheduleIn(
                user_id=self.child.pk, goal_definition_id=weekly.goal_id, expected_revision=0, request_id=uuid4(), paused=True,
            )),
            lambda: tools.start_expedition(self.start(user_id=self.child.pk)),
            lambda: tools.claim_expedition(ins.ClaimExpeditionIn(user_id=self.child.pk, expedition_id=trip.pk)),
            lambda: tools.deliver_reward_redemption(ins.DeliverRewardRedemptionIn(user_id=self.child.pk, redemption_id=reward.pk)),
        )
        before = list(CoinLedger.objects.values_list("pk", "amount"))
        # The authentication object was obtained before the permission change.
        type(self.parent).objects.filter(pk=self.parent.pk).update(is_staff=False)
        with override_user(self.parent):
            for call in calls:
                with self.assertRaises(MCPPermissionDenied):
                    call()
        type(self.parent).objects.filter(pk=self.parent.pk).update(is_staff=True)
        type(self.child).objects.filter(pk=self.child.pk).update(family_id=self.foreign_child.family_id)
        # Simulate a move while a request waits between initial resolution and
        # the shared household lock. Every native action revalidates under it.
        with override_user(self.parent), patch(
            "apps.mcp_server.tools.rpg_management._target", return_value=(self.parent, self.child),
        ):
            for call in calls:
                with self.assertRaises(MCPNotFoundError):
                    call()
        self.assertEqual(list(CoinLedger.objects.values_list("pk", "amount")), before)
        self.assertFalse(MCPMutationReceipt.objects.exists())
        self.assertFalse(ChallengeSchedule.objects.exists())
        trip.refresh_from_db()
        reward.refresh_from_db()
        self.assertEqual(trip.status, "active")
        self.assertEqual(reward.status, "approved")

    def test_invalid_management_inputs_are_bounded_and_do_not_accept_saved_state(self):
        ins = self.inputs()
        for invalid in ({"limit": 101}, {"user_id": True}, {"cursor": "x" * 2049}, {"user_id": 10**30}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                ins.ListExpeditionsIn(**invalid)
        with self.assertRaises(ValidationError):
            ins.StartExpeditionIn(mount_id=self.mount.pk, tier="short")
        with self.assertRaises(ValidationError):
            ins.StartExpeditionIn(mount_id=self.mount.pk, tier="short", request_id=uuid4(), loot={"coins": 999})
        with self.assertRaises(ValidationError):
            ins.UpdateChallengeScheduleIn(goal_definition_id=1, expected_revision=0, request_id=uuid4(), paused="true")
