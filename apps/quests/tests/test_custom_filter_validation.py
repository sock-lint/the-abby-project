"""Reject malformed new filters before saving private challenge promises."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import SkillCategory
from apps.mcp_server.context import override_user
from apps.mcp_server.models import MCPMutationReceipt
from apps.mcp_server.server import mcp
from apps.quests.goals import _amount
from apps.quests.models import (
    ChallengeActivity, ChallengeContribution, ChallengeGoal, ChallengeOccurrence,
    Quest, QuestDefinition, QuestParticipant,
)
from apps.quests.serializers import QuestWriteSerializer
from apps.quests.services import QuestService
from apps.quests.validators import validate_trigger_filter
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


def malformed_filters():
    """Exercise each installed filter's exact JSON value types and bounds."""
    for key in ("project_id", "skill_category_id", "savings_goal_id"):
        for value in ("7", 7.0, True, False, 0, -1, [], {}):
            yield key, value
    for value in (7, "7", {}, True, False, 0, "", ["7"], [7.0], [True], [0], [-1], [None], [{}], [[]]):
        yield "chore_ids", value
    for value in ("true", "false", 1, 0, [], {}):
        yield "on_time", value
    for value in ("chore_complete", {}, False, 0, [None], [True], [7], [{}], [[]]):
        yield "allowed_triggers", value


class CustomFilterStructureTests(SimpleTestCase):
    def test_common_validator_rejects_every_malformed_filter_value(self):
        for key, value in malformed_filters():
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValidationError) as caught:
                    validate_trigger_filter({key: value})
                self.assertIn(f"trigger_filter.{key}", str(caught.exception))

    def test_falsey_non_objects_are_rejected(self):
        for value in (False, 0, "", [], ["chore_complete"]):
            with self.subTest(value=value), self.assertRaisesMessage(ValidationError, "must be an object"):
                validate_trigger_filter(value)

    def test_optional_nulls_and_empty_filters_keep_their_existing_meaning(self):
        for value in (None, {}, {"allowed_triggers": None}, {"allowed_triggers": []}, {
            "project_id": None, "skill_category_id": None, "chore_ids": None,
            "savings_goal_id": None, "on_time": None,
        }, {"chore_ids": [], "on_time": False}):
            with self.subTest(value=value):
                validate_trigger_filter(value)

    def test_model_clean_uses_the_common_validation(self):
        for key, value in malformed_filters():
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                QuestDefinition(name="Synthetic private challenge", description="Synthetic",
                    quest_type="collection", target_value=3, trigger_filter={key: value}).clean()

    def test_catalog_policy_keys_stay_restricted_to_the_catalog(self):
        filters = {"allowed_triggers": ["habit_log"], "distinct_active_days": True, "reward_policy_version": 2}
        with self.assertRaises(ValidationError):
            validate_trigger_filter(filters)
        validate_trigger_filter(filters, allow_catalog_policy=True)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CustomFilterCreationTests(TestCase):
    def setUp(self):
        household = make_family("Custom filter validation", parents=[{
            "username": "custom-filter-parent", "is_staff": True,
        }], children=[{"username": "custom-filter-child"}])
        self.parent, self.child = household.parents[0], household.children[0]
        self.category = SkillCategory.objects.create(name="Custom filter category")
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def payload(self, filters):
        return {"name": f"Synthetic private challenge {uuid4()}", "description": "Synthetic",
                "quest_type": "collection", "target_value": 5, "trigger_filter": filters}

    def state(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            QuestDefinition, Quest, QuestParticipant, ChallengeGoal, ChallengeOccurrence,
            ChallengeActivity, ChallengeContribution, MCPMutationReceipt, CoinLedger,
        )}

    def wire(self, payload):
        with override_user(self.parent):
            result = async_to_sync(mcp.call_tool)("create_quest_definition", {"params": payload})
        if isinstance(result, tuple):
            return False, result[1]
        return bool(result.isError), result.structuredContent

    def filter_for(self, key, value):
        trigger = {"project_id": "clock_out", "savings_goal_id": "savings_goal_complete",
                   "on_time": "homework_complete"}.get(key, "chore_complete")
        return {"allowed_triggers": [trigger], key: value}

    def test_serializer_rejects_malformed_filters_with_field_errors(self):
        for key, value in malformed_filters():
            with self.subTest(key=key, value=value):
                serializer = QuestWriteSerializer(data=self.payload(self.filter_for(key, value)))
                self.assertFalse(serializer.is_valid())
                self.assertIn("trigger_filter", serializer.errors)
                self.assertIn(f"trigger_filter.{key}", str(serializer.errors["trigger_filter"]))

    def test_rest_rejects_malformed_filters_without_any_saved_state(self):
        for key, value in malformed_filters():
            with self.subTest(key=key, value=value), transaction.atomic():
                before = self.state()
                try:
                    payload = {**self.payload(self.filter_for(key, value)), "assigned_to": self.child.pk}
                    response = self.client.post("/api/quests/", payload, format="json")
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertIn("trigger_filter", response.data)
                    self.assertIn(f"trigger_filter.{key}", str(response.data["trigger_filter"]))
                    self.assertEqual(self.state(), before)
                finally:
                    transaction.set_rollback(True)

    def test_registered_mcp_rejects_malformed_filters_without_any_saved_state(self):
        for key, value in malformed_filters():
            with self.subTest(key=key, value=value), transaction.atomic():
                before = self.state()
                try:
                    payload = {**self.payload(self.filter_for(key, value)),
                               "request_id": str(uuid4()), "assigned_to_id": self.child.pk}
                    error, result = self.wire(payload)
                    self.assertTrue(error, result)
                    self.assertEqual(result["error"]["code"], "invalid_request")
                    self.assertFalse(result["error"]["retryable"])
                    self.assertIn(f"trigger_filter.{key}", result["error"]["message"])
                    self.assertEqual(self.state(), before)
                finally:
                    transaction.set_rollback(True)

    def test_rest_rejects_falsey_non_objects_without_any_saved_state(self):
        for value in (False, 0, "", [], ["chore_complete"]):
            with self.subTest(value=value), transaction.atomic():
                before = self.state()
                try:
                    response = self.client.post("/api/quests/", {
                        **self.payload(value), "assigned_to": self.child.pk,
                    }, format="json")
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertIn("trigger_filter", response.data)
                    self.assertEqual(self.state(), before)
                finally:
                    transaction.set_rollback(True)

    def test_valid_filters_are_saved_unchanged_and_match_typed_source_evidence(self):
        cases = (
            ({"project_id": 7}, "clock_out", {"project_id": 7, "hours": 1}),
            ({"savings_goal_id": 7}, "savings_goal_complete", {"savings_goal_id": 7}),
            ({"chore_ids": [7]}, "chore_complete", {"chore_id": 7}),
            ({"on_time": True}, "homework_complete", {"on_time": True}),
            ({"on_time": False}, "chore_complete", {}),
            ({"skill_category_id": self.category.pk}, "chore_complete", {
                "skill_category_id": self.category.pk,
            }),
        )
        for path in ("rest", "mcp"):
            for selectors, trigger, context in cases:
                with self.subTest(path=path, selectors=selectors), transaction.atomic():
                    try:
                        filters = {"allowed_triggers": [trigger], **selectors}
                        payload = self.payload(filters)
                        if path == "rest":
                            response = self.client.post("/api/quests/", {
                                **payload, "assigned_to": self.child.pk,
                            }, format="json")
                            self.assertEqual(response.status_code, 201, response.data)
                            definition = QuestDefinition.objects.get(pk=response.data["id"])
                        else:
                            error, result = self.wire({**payload, "request_id": str(uuid4()),
                                                       "assigned_to_id": self.child.pk})
                            self.assertFalse(error, result)
                            definition = QuestDefinition.objects.get(pk=result["definition"]["id"])
                        self.assertEqual(definition.trigger_filter, filters)
                        quest = Quest.objects.get(definition=definition)
                        QuestService.record_progress(self.child, trigger, context, category_context=context)
                        quest.refresh_from_db()
                        self.assertEqual(quest.current_progress, 1)
                        source = SimpleNamespace(trigger_type=trigger, context=context)
                        self.assertEqual(_amount({"metric": "count", "filter": filters}, source), Decimal(1))
                    finally:
                        transaction.set_rollback(True)

    def test_optional_filter_values_are_saved_without_coercion(self):
        for filters in ({}, {"allowed_triggers": None}, {"allowed_triggers": []}, {
            "allowed_triggers": ["chore_complete"], "project_id": None,
            "skill_category_id": None, "chore_ids": None, "savings_goal_id": None, "on_time": None,
        }, {"chore_ids": [], "on_time": False}):
            for path in ("rest", "mcp"):
                with self.subTest(path=path, filters=filters), transaction.atomic():
                    try:
                        payload = self.payload(deepcopy(filters))
                        if path == "rest":
                            response = self.client.post("/api/quests/", payload, format="json")
                            self.assertEqual(response.status_code, 201, response.data)
                            definition_id = response.data["id"]
                        else:
                            error, result = self.wire({**payload, "request_id": str(uuid4())})
                            self.assertFalse(error, result)
                            definition_id = result["definition"]["id"]
                        self.assertEqual(QuestDefinition.objects.get(pk=definition_id).trigger_filter, filters)
                    finally:
                        transaction.set_rollback(True)

    def test_exact_uuid_replay_preserves_previously_accepted_malformed_filters(self):
        for filters in ({"project_id": "7"}, {"savings_goal_id": "7"}, {"chore_ids": 7}):
            with self.subTest(filters=filters), transaction.atomic():
                try:
                    payload = {**self.payload(self.filter_for(*next(iter(filters.items())))),
                               "request_id": str(uuid4()), "assigned_to_id": self.child.pk}
                    # Model the old authoring boundary while retaining real creation,
                    # assignment, response serialization and persisted UUID receipt.
                    with patch("apps.mcp_server.tools.quests.validate_trigger_filter"):
                        error, first = self.wire(payload)
                    self.assertFalse(error, first)
                    before = self.state()
                    error, replay = self.wire(payload)
                    self.assertFalse(error, replay)
                    self.assertEqual(replay, first)
                    self.assertEqual(self.state(), before)
                    with self.assertRaises(ValidationError):
                        validate_trigger_filter(payload["trigger_filter"])
                finally:
                    transaction.set_rollback(True)
