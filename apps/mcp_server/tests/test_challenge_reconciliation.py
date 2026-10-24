"""Registered MCP dispatch uses native, private reconciliation receipts."""
import json
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync, sync_to_async
from django.db import connections
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp, mcp_capabilities
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.quests.tests.test_policy_reconciliation import make_policy_pair
from apps.rewards.models import CoinLedger
from apps.rpg.models import ContentPackPublication, UserInventory
from config.tests.factories import make_family


PREVIEW = "preview_challenge_reconciliation"
GET = "get_challenge_reconciliation"
PUBLISH = "publish_challenge_reconciliation"
TOOLS = {PREVIEW, GET, PUBLISH}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChallengeReconciliationToolTests(TransactionTestCase):
    def setUp(self):
        family = make_family(
            "Reconciliation MCP", parents=[
                {"username": "reconcile-author", "is_staff": True},
                {"username": "reconcile-coparent", "is_staff": True},
            ], children=[{"username": "reconcile-child"}],
        )
        self.actor = family.parents[0]
        self.coparent, self.child = family.parents[1], family.children[0]
        other = make_family("Other reconciliation family", parents=[{"username": "reconcile-foreign", "is_staff": True}])
        self.foreign = other.parents[0]

    def pair(self, *, accept=False, cooperative=False, name="Synthetic reconciliation", repeatable=False):
        values = {
            "name": name, "description": "Synthetic global challenge", "quest_type": "collection",
            "target_value": 3, "duration_days": 7, "trigger_filter": {"allowed_triggers": ["habit_log"]},
            "is_system": True, "is_repeatable": repeatable, "coin_reward": 5,
        }
        source = QuestDefinition.objects.create(**values, created_by=self.actor)
        if accept:
            list_goals(self.child)
        canonical = QuestDefinition.objects.create(**values, is_cooperative=cooperative)
        return source, canonical

    def preview(self, source, canonical, *, request_id=None):
        params = {
            "source_definition_id": source.pk, "canonical_definition_id": canonical.pk,
            "client_request_id": str(request_id or uuid4()),
        }
        return self.payload(self.call(PREVIEW, params)), params

    def publish(self, plan, **extra):
        return self.call(PUBLISH, {
            "preview_id": plan["preview_id"], "content_digest": plan["content_digest"], **extra,
        }, scopes=("mcp:publish",), confirmation=True)

    def call(self, name, params, *, actor=None, scopes=("mcp:author",), **arguments):
        async def run():
            with override_user(actor or self.actor, scopes=frozenset(scopes)):
                try:
                    return await mcp.call_tool(name, {"params": params, **arguments})
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def payload(self, result, *, error=None):
        if isinstance(result, tuple):
            content, payload = result
            failed = False
        else:
            content, payload, failed = result.content, result.structuredContent, bool(result.isError)
        blocks = [block.text for block in content if block.type == "text"]
        self.assertEqual(len(blocks), 1, result)
        self.assertEqual(json.loads(blocks[0]), payload)
        self.assertEqual(failed, error is not None, result)
        if error is not None:
            self.assertEqual(payload["error"]["code"], error, result)
        return payload

    def test_tools_are_discoverable_with_concrete_schemas_and_safe_annotations(self):
        registered = {entry.name: entry for entry in mcp._tool_manager.list_tools()}
        self.assertFalse(TOOLS - registered.keys(), f"Missing reconciliation tools: {TOOLS - registered.keys()}")
        for name in TOOLS:
            with self.subTest(tool=name):
                self.assertIsNotNone(registered[name].output_schema)
                self.assertTrue(registered[name].annotations.idempotentHint)
                self.assertFalse(registered[name].annotations.openWorldHint)
        self.assertTrue(registered[GET].annotations.readOnlyHint)
        self.assertFalse(registered[PREVIEW].annotations.readOnlyHint)
        self.assertTrue(registered[PUBLISH].annotations.destructiveHint)
        self.assertIn("confirmation", registered[PUBLISH].parameters["properties"])

    def test_registered_policy_acknowledgement_is_a_separate_strict_boolean(self):
        registered = {entry.name: entry for entry in mcp._tool_manager.list_tools()}
        parameters = registered[PUBLISH].parameters
        publish_input = parameters["$defs"]["PublishChallengeReconciliationIn"]["properties"]
        self.assertEqual(publish_input["acknowledge_policy_transition"]["type"], "boolean")
        self.assertIs(publish_input["acknowledge_policy_transition"]["default"], False)
        output = registered[PUBLISH].output_schema
        self.assertIn("requires_policy_acknowledgement", output["required"])
        self.assertIn("acknowledged_policy_transition", output["required"])
        for value in (1, "true", None):
            with self.subTest(acknowledgement=value):
                params = {"preview_id": str(uuid4()), "content_digest": "0" * 64,
                          "acknowledge_policy_transition": value}
                self.payload(self.call(PUBLISH, params, scopes=("mcp:publish",), confirmation=True),
                             error="invalid_input")
        self.assertEqual(ContentPackPublication.objects.count(), 0)

    def test_old_immutable_receipts_receive_false_policy_defaults_only_on_the_wire(self):
        source, canonical = self.pair()
        plan, _ = self.preview(source, canonical)
        published = self.payload(self.publish(plan))
        receipt = ContentPackPublication.objects.get(pk=plan["preview_id"])
        stats = deepcopy(receipt.stats)
        for key in ("preview_response", "published_response"):
            stats[key].pop("requires_policy_acknowledgement", None)
            stats[key].pop("acknowledged_policy_transition", None)
        ContentPackPublication.objects.filter(pk=receipt.pk).update(stats=stats)
        recovered = self.payload(self.call(GET, {"preview_id": plan["preview_id"]}))
        self.assertIs(recovered["requires_policy_acknowledgement"], False)
        self.assertIs(recovered["acknowledged_policy_transition"], False)
        self.assertEqual(recovered, published)
        self.assertEqual(self.payload(self.publish(plan)), recovered)
        receipt.refresh_from_db()
        self.assertEqual(receipt.stats, stats)

    def test_policy_acknowledgement_is_forwarded_independently_of_cooperation(self):
        source, canonical = self.pair()
        plan, _ = self.preview(source, canonical)
        with patch("apps.quests.reconciliation.publish_reconciliation", return_value=plan) as publish:
            self.assertEqual(self.payload(self.publish(plan, acknowledge_policy_transition=True)), plan)
        self.assertEqual(publish.call_args.kwargs, {
            "acknowledge_cooperative_transition": False, "acknowledge_policy_transition": True,
        })

    def test_policy_projection_keeps_differences_typed_and_global_only(self):
        source, canonical = self.pair()
        plan, _ = self.preview(source, canonical)
        plan["requires_policy_acknowledgement"] = True
        old_filter = {"allowed_triggers": ["habit_log"]}
        new_filter = {**old_filter, "distinct_active_days": True, "reward_policy_version": 2}
        plan["canonical_definition"]["trigger_filter"] = new_filter
        plan["differences"] = [
            {"field": "description", "source": "Three taps", "canonical": "Three different days"},
            {"field": "trigger_filter", "source": old_filter, "canonical": new_filter},
            {"field": "coin_reward", "source": 40, "canonical": 10},
            {"field": "reward_items", "source": [{"item_id": 73119, "quantity": 1}], "canonical": []},
        ]
        with patch("apps.quests.reconciliation.get_reconciliation", return_value=plan):
            self.assertEqual(self.payload(self.call(GET, {"preview_id": plan["preview_id"]})), plan)
        malformed = []
        for value in (True, "2", 2.0, 3):
            candidate = deepcopy(plan)
            candidate["canonical_definition"]["trigger_filter"]["reward_policy_version"] = value
            malformed.append(candidate)
        for key, value in (("distinct_active_days", 1), ("project_id", 73119)):
            candidate = deepcopy(plan)
            candidate["differences"][1]["canonical"][key] = value
            malformed.append(candidate)
        for difference in (
            {"field": "xp_reward", "source": 20, "canonical": 10},
            {"field": "coin_reward", "source": True, "canonical": 10},
            {"field": "reward_items", "source": [{"item_id": 73119, "quantity": 1, "user_id": 73119}],
             "canonical": []},
        ):
            candidate = deepcopy(plan)
            candidate["differences"] = [difference]
            malformed.append(candidate)
        for candidate in malformed:
            with self.subTest(candidate=candidate), patch(
                "apps.quests.reconciliation.get_reconciliation", return_value=candidate,
            ):
                result = self.call(GET, {"preview_id": plan["preview_id"]})
                self.payload(result, error="internal_error")
                self.assertNotIn("73119", json.dumps(result.structuredContent))

    def test_wrong_scope_does_not_reach_native_authoring(self):
        for name, params in (
            (PREVIEW, {"source_definition_id": 1, "canonical_definition_id": 2, "client_request_id": str(uuid4())}),
            (GET, {"preview_id": str(uuid4())}),
            (PUBLISH, {"preview_id": str(uuid4()), "content_digest": "0" * 64}),
        ):
            with self.subTest(tool=name):
                self.payload(self.call(name, params, scopes=("mcp:catalog",), confirmation=True), error="permission_denied")

    def test_publication_requires_independent_literal_confirmation(self):
        params = {"preview_id": str(uuid4()), "content_digest": "0" * 64}
        self.payload(self.call(PUBLISH, params, scopes=("mcp:publish",)), error="confirmation_required")
        self.payload(self.call(PUBLISH, params, scopes=("mcp:publish",), confirmation=False), error="confirmation_required")
        for confirmation in (1, "true"):
            with self.subTest(confirmation=confirmation):
                self.payload(self.call(PUBLISH, params, scopes=("mcp:publish",), confirmation=confirmation), error="invalid_input")

    def test_scope_discovery_and_capability_keep_authoring_and_publication_separate(self):
        async def discover(scope):
            with override_user(self.actor, scopes=frozenset({scope})):
                return {entry.name for entry in await mcp.list_tools()}
        self.assertEqual(async_to_sync(discover)("mcp:author") & TOOLS, {PREVIEW, GET})
        self.assertEqual(async_to_sync(discover)("mcp:publish") & TOOLS, {PUBLISH})
        for scopes, available in ((("mcp:author",), False), (("mcp:publish",), False), (("mcp:author", "mcp:publish"), True)):
            with override_user(self.actor, scopes=frozenset(scopes)):
                workflow = json.loads(mcp_capabilities())["workflows"]["challenge_reconciliation"]
            self.assertEqual(set(workflow["required_scopes"]), {"mcp:author", "mcp:publish"})
            self.assertEqual(workflow["available"], available)

    def test_native_preview_publish_and_replay_preserve_accepted_windows_and_creator(self):
        source, canonical = self.pair(accept=True, repeatable=True)
        goal = ChallengeGoal.objects.get(user=self.child, catalog_definition=source)
        before = list(ChallengeOccurrence.objects.filter(goal=goal).values())
        self.assertEqual(len(before), 1)
        rewards_before = (CoinLedger.objects.count(), UserInventory.objects.count())
        plan, params = self.preview(source, canonical)
        self.assertEqual(plan["preview_id"], params["client_request_id"])
        self.assertEqual(plan["source_definition"]["creator_provenance"], "same_family_parent")
        self.assertEqual(plan["canonical_definition"]["creator_provenance"], "creatorless_global")
        self.assertIsNone(plan["published_at"])
        self.assertEqual(self.payload(self.call(PREVIEW, params)), plan)
        self.assertEqual(self.payload(self.call(GET, {"preview_id": plan["preview_id"]})), plan)
        source.refresh_from_db()
        goal.refresh_from_db()
        self.assertIsNone(source.superseded_by_id)
        self.assertEqual(goal.catalog_definition_id, source.pk)
        published = self.payload(self.publish(plan))
        self.assertIsNotNone(published["published_at"])
        self.assertEqual(published["source_definition"]["superseded_by_id"], canonical.pk)
        source.refresh_from_db()
        goal.refresh_from_db()
        self.assertEqual((source.superseded_by_id, source.created_by_id), (canonical.pk, self.actor.pk))
        self.assertEqual(goal.catalog_definition_id, canonical.pk)
        self.assertEqual(list(ChallengeOccurrence.objects.filter(goal=goal).values()), before)
        self.assertEqual((CoinLedger.objects.count(), UserInventory.objects.count()), rewards_before)
        self.assertEqual(self.payload(self.publish(plan)), published)
        self.assertEqual(self.payload(self.call(GET, {"preview_id": plan["preview_id"]})), published)
        self.assertEqual(self.payload(self.call(PREVIEW, params)), plan)
        self.assertEqual(ContentPackPublication.objects.count(), 1)

    def test_cooperation_difference_is_reviewed_then_explicitly_acknowledged_at_publish(self):
        source, canonical = self.pair(cooperative=True)
        plan, _ = self.preview(source, canonical)
        self.assertTrue(plan["requires_cooperative_acknowledgement"])
        self.assertEqual(plan["differences"], [{"field": "is_cooperative", "source": False, "canonical": True}])
        self.payload(self.publish(plan), error="invalid_request")
        source.refresh_from_db()
        self.assertIsNone(source.superseded_by_id)
        for value in (1, "true"):
            with self.subTest(acknowledgement=value):
                self.payload(self.publish(plan, acknowledge_cooperative_transition=value), error="invalid_input")
        published = self.payload(self.publish(plan, acknowledge_cooperative_transition=True))
        self.assertTrue(published["acknowledged_cooperative_transition"])
        self.assertEqual(self.payload(self.publish(plan, acknowledge_cooperative_transition=True)), published)
        self.payload(self.publish(plan), error="invalid_request")

    def test_supported_policy_pairs_require_separate_acknowledgement_including_completed_replay(self):
        for name in ("Daily Rituals", "Comeback Kid"):
            with self.subTest(name=name):
                source, canonical = make_policy_pair(self.actor, name)
                before = (CoinLedger.objects.count(), UserInventory.objects.count(), ChallengeOccurrence.objects.count())
                plan, params = self.preview(source, canonical)
                self.assertTrue(plan["requires_policy_acknowledgement"])
                self.assertFalse(plan["requires_cooperative_acknowledgement"])
                self.assertFalse(plan["acknowledged_policy_transition"])
                self.assertEqual(plan["canonical_definition"]["trigger_filter"]["reward_policy_version"], 2)
                self.assertEqual(self.payload(self.call(GET, {"preview_id": plan["preview_id"]})), plan)
                self.assertEqual(self.payload(self.call(PREVIEW, params)), plan)
                self.payload(self.publish(plan), error="invalid_request")
                self.payload(self.publish(plan, acknowledge_cooperative_transition=True), error="invalid_request")
                source.refresh_from_db()
                self.assertIsNone(source.superseded_by_id)
                published = self.payload(self.publish(plan, acknowledge_policy_transition=True))
                self.assertTrue(published["acknowledged_policy_transition"])
                self.assertFalse(published["acknowledged_cooperative_transition"])
                source.refresh_from_db()
                self.assertEqual((source.superseded_by_id, source.created_by_id), (canonical.pk, self.actor.pk))
                self.payload(self.publish(plan), error="invalid_request")
                self.payload(self.publish(plan, acknowledge_cooperative_transition=True), error="invalid_request")
                self.assertEqual(self.payload(self.publish(plan, acknowledge_policy_transition=True)), published)
                self.assertEqual(self.payload(self.call(GET, {"preview_id": plan["preview_id"]})), published)
                self.assertEqual(self.payload(self.call(PREVIEW, params)), plan)
                self.assertEqual((CoinLedger.objects.count(), UserInventory.objects.count(),
                                  ChallengeOccurrence.objects.count()), before)

    def test_strict_arguments_fail_before_any_native_receipt_or_catalog_write(self):
        valid = {"source_definition_id": 1, "canonical_definition_id": 2, "client_request_id": str(uuid4())}
        invalid_previews = [
            {**valid, "source_definition_id": value} for value in (True, "1", 0, -1, 9223372036854775808)
        ] + [
            {**valid, "canonical_definition_id": True}, {**valid, "canonical_definition_id": 1},
            {**valid, "client_request_id": "invalid"}, {**valid, "client_request_id": 1},
            {**valid, "user_id": self.child.pk}, {**valid, "acknowledge_cooperative_transition": True},
            {**valid, "acknowledge_policy_transition": True},
        ]
        for params in invalid_previews:
            with self.subTest(params=params):
                self.payload(self.call(PREVIEW, params), error="invalid_input")
        for params in ({"preview_id": "invalid"}, {"preview_id": str(uuid4()), "family_id": self.actor.family_id}):
            with self.subTest(params=params):
                self.payload(self.call(GET, params), error="invalid_input")
        valid_publish = {"preview_id": str(uuid4()), "content_digest": "0" * 64}
        for params in (
            {**valid_publish, "content_digest": "A" * 64}, {**valid_publish, "content_digest": "0" * 63},
            {**valid_publish, "preview_id": False}, {**valid_publish, "acknowledge_cooperative_transition": "false"},
            {**valid_publish, "source_definition_id": 1},
        ):
            with self.subTest(params=params):
                self.payload(self.call(PUBLISH, params, scopes=("mcp:publish",), confirmation=True), error="invalid_input")
        self.assertEqual(ContentPackPublication.objects.count(), 0)
        self.assertEqual(QuestDefinition.objects.count(), 0)

    def test_private_receipt_ownership_and_operation_are_checked_on_wire(self):
        source, canonical = self.pair()
        plan, _ = self.preview(source, canonical)
        for actor in (self.coparent, self.foreign):
            with self.subTest(actor=actor.username):
                self.payload(self.call(GET, {"preview_id": plan["preview_id"]}, actor=actor), error="not_found")
                self.payload(self.call(PUBLISH, {
                    "preview_id": plan["preview_id"], "content_digest": plan["content_digest"],
                }, actor=actor, scopes=("mcp:publish",), confirmation=True), error="not_found")
        ordinary = ContentPackPublication.objects.create(
            pack="ordinary-pack", actor=self.actor, family=self.actor.family, content_digest="0" * 64,
            state_digest="0" * 64, expires_at=timezone.now() + timedelta(minutes=10), stats={},
        )
        for preview_id in (str(uuid4()), str(ordinary.pk)):
            with self.subTest(preview_id=preview_id):
                self.payload(self.call(GET, {"preview_id": preview_id}), error="not_found")
                self.payload(self.call(PUBLISH, {
                    "preview_id": preview_id, "content_digest": "0" * 64,
                }, scopes=("mcp:publish",), confirmation=True), error="not_found")
        source.refresh_from_db()
        self.assertIsNone(source.superseded_by_id)

    def test_stale_context_cannot_preview_read_publish_or_replay_after_authority_changes(self):
        source, canonical = self.pair()
        plan, params = self.preview(source, canonical)
        users = get_user_model().objects.filter(pk=self.actor.pk)
        original = {"role": "parent", "is_staff": True, "is_active": True, "family_id": self.actor.family_id}
        for change in ({"role": "child"}, {"is_staff": False}, {"is_active": False}, {"family_id": self.foreign.family_id}):
            users.update(**change)
            try:
                with self.subTest(change=change):
                    self.payload(self.call(PREVIEW, {**params, "client_request_id": str(uuid4())}), error="permission_denied")
                    self.payload(self.call(GET, {"preview_id": plan["preview_id"]}), error="permission_denied")
                    self.payload(self.publish(plan), error="permission_denied")
            finally:
                users.update(**original)
        self.payload(self.publish(plan))
        users.update(is_active=False)
        try:
            self.payload(self.publish(plan), error="permission_denied")
        finally:
            users.update(**original)

    def test_stale_expired_and_changed_uuid_payload_fail_without_reconciliation(self):
        source, canonical = self.pair()
        plan, params = self.preview(source, canonical)
        other_source, other_canonical = self.pair(name="Another synthetic pair")
        self.payload(self.call(PREVIEW, {
            **params, "source_definition_id": other_source.pk, "canonical_definition_id": other_canonical.pk,
        }), error="challenge_reconciliation_conflict")
        self.payload(self.call(PUBLISH, {
            "preview_id": plan["preview_id"], "content_digest": "0" * 64,
        }, scopes=("mcp:publish",), confirmation=True), error="challenge_reconciliation_conflict")
        # Keep the pair equivalent while changing its reviewed state, so the
        # native digest check is exercised after ordinary plan validation.
        QuestDefinition.objects.filter(pk__in=[source.pk, canonical.pk]).update(coin_reward=6)
        self.payload(self.publish(plan), error="challenge_reconciliation_conflict")
        source.refresh_from_db()
        self.assertIsNone(source.superseded_by_id)
        QuestDefinition.objects.filter(pk__in=[source.pk, canonical.pk]).update(coin_reward=5)
        ContentPackPublication.objects.filter(pk=plan["preview_id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.payload(self.publish(plan), error="challenge_reconciliation_conflict")
        self.assertEqual(ContentPackPublication.objects.count(), 1)

    def test_foreign_catalog_owner_and_household_bound_filters_are_rejected_without_private_data(self):
        source, canonical = self.pair()
        QuestDefinition.objects.filter(pk=source.pk).update(created_by=self.foreign)
        self.payload(self.call(PREVIEW, {
            "source_definition_id": source.pk, "canonical_definition_id": canonical.pk, "client_request_id": str(uuid4()),
        }), error="permission_denied")
        QuestDefinition.objects.filter(pk=source.pk).update(created_by=self.actor)
        for key, value in (("project_id", 771156), ("chore_ids", [771156]), ("savings_goal_id", 771156)):
            QuestDefinition.objects.filter(pk__in=[source.pk, canonical.pk]).update(
                trigger_filter={"allowed_triggers": ["habit_log"], key: value},
            )
            with self.subTest(filter=key):
                result = self.call(PREVIEW, {
                    "source_definition_id": source.pk, "canonical_definition_id": canonical.pk, "client_request_id": str(uuid4()),
                })
                self.payload(result, error="invalid_request")
                self.assertNotIn("771156", json.dumps(result.structuredContent))
        self.assertEqual(ContentPackPublication.objects.count(), 0)

    def test_malformed_saved_trigger_lists_fail_before_persisting_an_unreadable_receipt(self):
        source, canonical = self.pair()
        for triggers in (None, "habit_log", [None]):
            QuestDefinition.objects.filter(pk__in=[source.pk, canonical.pk]).update(
                trigger_filter={"allowed_triggers": triggers},
            )
            with self.subTest(triggers=triggers):
                self.payload(self.call(PREVIEW, {
                    "source_definition_id": source.pk, "canonical_definition_id": canonical.pk,
                    "client_request_id": str(uuid4()),
                }), error="invalid_request")
        self.assertEqual(ContentPackPublication.objects.count(), 0)

    def test_actual_projection_is_global_only_and_unexpected_producer_fields_fail_safely(self):
        source, canonical = self.pair(accept=True)
        plan, _ = self.preview(source, canonical)
        forbidden = {
            "actor_id", "family_id", "user_id", "created_by_id", "goal_id", "goals", "households",
            "affected_goals", "goal_mapping", "usage", "usage_count", "count",
        }

        def check(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & value.keys(), value)
                for nested in value.values():
                    check(nested)
            elif isinstance(value, list):
                for nested in value:
                    check(nested)
        check(plan)
        published = self.payload(self.publish(plan))
        check(published)
        secret = "synthetic-private-producer-value"
        bad_producer = deepcopy(published)
        bad_producer["family_id"] = secret
        with patch("apps.quests.reconciliation.get_reconciliation", return_value=bad_producer):
            result = self.call(GET, {"preview_id": plan["preview_id"]})
        self.payload(result, error="internal_error")
        self.assertNotIn(secret, json.dumps(result.structuredContent))
