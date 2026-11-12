"""Manual assignment accepts only campaigns ordinary saved work can advance."""
import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import SkillCategory, SkillProgress
from apps.habits.models import Habit
from apps.mcp_server.auth import _resolve_access
from apps.mcp_server.context import override_user
from apps.mcp_server.models import MCPMutationReceipt
from apps.mcp_server.server import mcp
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family, make_oauth_token


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    MCP_RESOURCE_URL="http://synthetic.invalid/mcp",
    RPG_ASSET_SUPPORT_POLICY=None,
)
class ReachableManualAdmissionTests(TestCase):
    def test_native_fence_cannot_adopt_a_category_that_was_never_admitted(self):
        from unittest.mock import patch
        from apps.quests.reference_locks import admit_definition_identity

        definition = self.definition(["habit_log"])
        retired = SkillCategory.objects.create(name="Retired concurrent category", is_retired=True)

        def change_rules(selected):
            admit_definition_identity(selected)
            QuestDefinition.objects.filter(pk=selected.pk).update(trigger_filter={
                "allowed_triggers": ["habit_log"], "skill_category_id": retired.pk,
            })

        with patch("apps.quests.reference_locks.admit_definition_identity", side_effect=change_rules):
            with self.assertRaises(ValueError):
                QuestService.start_quest(self.child, definition.pk)
        self.assertFalse(Quest.objects.exists())

    def test_automatic_fence_cannot_adopt_a_category_that_was_never_admitted(self):
        from unittest.mock import patch
        from apps.quests.goals import list_goals
        from apps.quests.models import ChallengeGoal
        from apps.quests.reference_locks import admit_definition_identity

        definition = self.definition(["habit_log"])
        retired = SkillCategory.objects.create(name="Retired automatic category", is_retired=True)

        def change_rules(selected):
            admit_definition_identity(selected)
            QuestDefinition.objects.filter(pk=selected.pk).update(trigger_filter={
                "allowed_triggers": ["habit_log"], "skill_category_id": retired.pk,
            })

        with patch("apps.quests.reference_locks.admit_definition_identity", side_effect=change_rules):
            list_goals(self.child)
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=definition).exists())

    def setUp(self):
        household = make_family(
            "Manual challenge admission",
            parents=[{"username": "manual-admission-parent", "is_staff": True}],
            children=[{"username": "manual-admission-child"}, {"username": "manual-admission-sibling"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        token, _ = make_oauth_token(self.parent, scope="mcp:read mcp:write")
        self.actor, self.scopes = _resolve_access(token.token)
        self.client = APIClient()

    def definition(self, triggers, **values):
        return QuestDefinition.objects.create(
            name=f"Manual campaign {uuid4()}", description="Synthetic saved-work campaign",
            duration_days=14, is_system=True,
            **{"target_value": 3, "quest_type": "collection", "trigger_filter": {"allowed_triggers": triggers}, **values},
        )

    def payload(self, triggers, **values):
        return {
            "name": f"Private campaign {uuid4()}", "description": "Synthetic family challenge",
            "quest_type": "collection", "target_value": 3,
            "trigger_filter": {"allowed_triggers": triggers}, **values,
        }

    def wire(self, name, params):
        async def invoke():
            with override_user(self.actor, scopes=self.scopes):
                return await mcp.call_tool(name, {"params": params, "confirmation": True})

        result = async_to_sync(invoke)()
        if isinstance(result, tuple):
            blocks, payload = result
            error = False
        else:
            blocks, payload, error = result.content, result.structuredContent, bool(result.isError)
        self.assertEqual(json.loads(next(block.text for block in blocks if block.type == "text")), payload)
        return error, payload

    def saved_state(self):
        return {
            model._meta.label_lower: list(model.objects.order_by("pk").values())
            for model in (QuestDefinition, Quest, QuestParticipant, MCPMutationReceipt,
                          CoinLedger, SkillProgress, UserInventory)
        }

    def assert_native_denied(self, triggers, **values):
        definition = self.definition(triggers, **values)
        before = self.saved_state()
        with self.assertRaises(ValueError):
            QuestService.start_quest(self.child, definition.pk)
        self.assertEqual(self.saved_state(), before)

    def assert_wire_denied(self, name, params):
        before = self.saved_state()
        error, payload = self.wire(name, params)
        self.assertTrue(error, payload)
        self.assertEqual(payload["error"]["code"], "invalid_request", payload)
        self.assertEqual(self.saved_state(), before)

    def log_habit(self, quest, expected_progress=1):
        habit = Habit.objects.create(
            name="Actual qualifying habit", user=self.child, created_by=self.parent, xp_reward=0,
        )
        self.client.force_authenticate(self.child)
        response = self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        quest.refresh_from_db()
        self.assertEqual(quest.current_progress, expected_progress)

    def test_native_solo_rejects_perfect_day_only(self):
        self.assert_native_denied(["perfect_day"])

    def test_native_solo_rejects_badge_only(self):
        self.assert_native_denied(["badge_earned"])

    def test_native_solo_rejects_quest_completion_only(self):
        self.assert_native_denied(["quest_complete"])

    def test_native_coop_rejects_reward_only_without_assigning_either_child(self):
        definition = self.definition(["badge_earned"])
        before = self.saved_state()
        with self.assertRaises(ValueError):
            QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])
        self.assertEqual(self.saved_state(), before)

    def test_native_solo_rechecks_rules_changed_while_definition_admission_waited(self):
        from apps.quests.reference_locks import admit_definition_identity

        definition = self.definition(["habit_log"])

        def admit_after_author_changed_rules(stale_definition):
            QuestDefinition.objects.filter(pk=definition.pk).update(
                trigger_filter={"allowed_triggers": ["badge_earned"]},
            )
            admit_definition_identity(stale_definition)

        with patch("apps.quests.reference_locks.admit_definition_identity", admit_after_author_changed_rules):
            with self.assertRaises(ValueError):
                QuestService.start_quest(self.child, definition.pk)
        self.assertFalse(Quest.objects.exists())
        self.assertFalse(QuestParticipant.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_native_coop_rechecks_rules_changed_while_definition_admission_waited(self):
        from apps.quests.reference_locks import admit_definition_identity

        definition = self.definition(["habit_log"])

        def admit_after_author_changed_rules(stale_definition):
            QuestDefinition.objects.filter(pk=definition.pk).update(
                trigger_filter={"allowed_triggers": ["badge_earned"]},
            )
            admit_definition_identity(stale_definition)

        with patch("apps.quests.reference_locks.admit_definition_identity", admit_after_author_changed_rules):
            with self.assertRaises(ValueError):
                QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])
        self.assertFalse(Quest.objects.exists())
        self.assertFalse(QuestParticipant.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_native_scroll_rejection_preserves_inventory(self):
        definition = self.definition(["perfect_day"])
        scroll = ItemDefinition.objects.create(
            slug="unreachable-manual-scroll", name="Quest scroll", item_type="quest_scroll",
        )
        UserInventory.objects.create(user=self.child, item=scroll, quantity=2)
        before = self.saved_state()
        with self.assertRaises(ValueError):
            QuestService.start_quest(self.child, definition.pk, use_scroll_item_id=scroll.pk)
        self.assertEqual(self.saved_state(), before)

    def test_rest_start_rejects_reward_only_without_consuming_scroll(self):
        definition = self.definition(["perfect_day"])
        scroll = ItemDefinition.objects.create(
            slug="unreachable-rest-scroll", name="Quest scroll", item_type="quest_scroll",
        )
        UserInventory.objects.create(user=self.child, item=scroll, quantity=2)
        self.client.force_authenticate(self.child)
        before = self.saved_state()
        response = self.client.post("/api/quests/start/", {
            "definition_id": definition.pk, "scroll_item_id": scroll.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.saved_state(), before)

    def test_rest_parent_assignment_rejects_reward_only(self):
        definition = self.definition(["badge_earned"])
        self.client.force_authenticate(self.parent)
        before = self.saved_state()
        response = self.client.post(f"/api/quests/{definition.pk}/assign/", {
            "user_id": self.child.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.saved_state(), before)

    def test_rest_coop_assignment_rejects_reward_only(self):
        definition = self.definition(["badge_earned"])
        self.client.force_authenticate(self.parent)
        before = self.saved_state()
        response = self.client.post(f"/api/quests/{definition.pk}/co-op/", {
            "user_ids": [self.child.pk, self.sibling.pk],
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.saved_state(), before)

    def test_rest_private_creation_without_assignment_rejects_reward_only_atomically(self):
        self.client.force_authenticate(self.parent)
        before = self.saved_state()
        response = self.client.post("/api/quests/", self.payload(["perfect_day"]), format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.saved_state(), before)

    def test_rest_private_autoassignment_rejects_reward_only_atomically(self):
        self.client.force_authenticate(self.parent)
        before = self.saved_state()
        response = self.client.post("/api/quests/", self.payload(
            ["badge_earned"], assigned_to=self.child.pk,
        ), format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.saved_state(), before)

    def test_rest_private_coop_creation_rejects_reward_only_atomically(self):
        self.client.force_authenticate(self.parent)
        before = self.saved_state()
        response = self.client.post("/api/quests/", self.payload(
            ["badge_earned"], coop_user_ids=[self.child.pk, self.sibling.pk],
        ), format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.saved_state(), before)

    def test_registered_mcp_private_creation_without_assignment_has_no_receipt_on_denial(self):
        self.assert_wire_denied("create_quest_definition", self.payload(
            ["perfect_day"], request_id=str(uuid4()),
        ))

    def test_registered_mcp_private_autoassignment_rolls_back_definition_and_receipt(self):
        self.assert_wire_denied("create_quest_definition", self.payload(
            ["badge_earned"], request_id=str(uuid4()), assigned_to_id=self.child.pk,
        ))

    def test_registered_mcp_solo_assignment_rejects_reward_only(self):
        definition = self.definition(["badge_earned"])
        self.assert_wire_denied("assign_quest", {
            "definition_id": definition.pk, "user_id": self.child.pk,
        })

    def test_registered_mcp_coop_assignment_rejects_reward_only(self):
        definition = self.definition(["badge_earned"])
        self.assert_wire_denied("assign_co_op_quest", {
            "definition_id": definition.pk, "user_ids": [self.child.pk, self.sibling.pk],
        })

    def test_new_catalog_choices_do_not_offer_reward_only_as_available(self):
        definition = self.definition(["badge_earned"])
        self.client.force_authenticate(self.parent)
        rest = self.client.get("/api/quests/catalog/")
        self.assertEqual(rest.status_code, 200, rest.data)
        error, payload = self.wire("list_quest_catalog", {})
        self.assertFalse(error, payload)
        for rows in (rest.data, payload["quest_definitions"]):
            with self.subTest(rows=rows):
                self.assertFalse(any(row["catalog_available"] for row in rows if row["id"] == definition.pk))

    def test_native_boss_rejects_only_supported_activity_with_zero_damage(self):
        self.assert_native_denied(["creation_logged"], quest_type="boss")

    def test_automatic_catalog_skips_boss_with_only_zero_damage_activity(self):
        from apps.quests.goals import list_goals
        from apps.quests.models import ChallengeGoal, ChallengeOccurrence

        self.definition(["creation_logged"], quest_type="boss")
        self.assertEqual(list_goals(self.child)["results"], [])
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_automatic_catalog_rechecks_rules_changed_while_definition_admission_waited(self):
        from apps.quests.goals import list_goals
        from apps.quests.models import ChallengeGoal, ChallengeOccurrence
        from apps.quests.reference_locks import admit_definition_identity

        definition = self.definition(["habit_log"])

        def admit_after_author_changed_rules(stale_definition):
            QuestDefinition.objects.filter(pk=definition.pk).update(
                trigger_filter={"allowed_triggers": ["badge_earned"]},
            )
            admit_definition_identity(stale_definition)

        with patch("apps.quests.reference_locks.admit_definition_identity", admit_after_author_changed_rules):
            rows = list_goals(self.child)["results"]
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertEqual(rows, [])
        self.assertFalse(CoinLedger.objects.exists())

    def test_rest_private_boss_without_assignment_rejects_zero_damage_activity(self):
        self.client.force_authenticate(self.parent)
        before = self.saved_state()
        response = self.client.post("/api/quests/", self.payload(
            ["creation_logged"], quest_type="boss",
        ), format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.saved_state(), before)

    def test_registered_mcp_boss_creation_rejects_zero_damage_activity(self):
        self.assert_wire_denied("create_quest_definition", self.payload(
            ["creation_logged"], quest_type="boss", request_id=str(uuid4()),
        ))

    def test_mixed_reward_and_real_work_assignment_advances_from_actual_habit(self):
        error, result = self.wire("create_quest_definition", self.payload(
            ["badge_earned", "habit_log", "perfect_day"], assigned_to_id=self.child.pk,
        ))
        self.assertFalse(error, result)
        self.log_habit(Quest.objects.get(pk=result["quest"]["id"]))

    def test_missing_empty_and_null_allowlists_preserve_native_unfiltered_behavior(self):
        for filters in ({}, {"allowed_triggers": []}, {"allowed_triggers": None}):
            with self.subTest(filters=filters):
                definition = self.definition([], trigger_filter=filters)
                quest = QuestService.start_quest(self.child, definition.pk)
                self.log_habit(quest)
                quest.status = Quest.Status.FAILED
                quest.save(update_fields=["status", "updated_at"])

    def test_mixed_boss_activity_keeps_positive_damage_source(self):
        definition = self.definition(["creation_logged", "habit_log"], quest_type="boss", target_value=20)
        quest = QuestService.start_quest(self.child, definition.pk)
        self.log_habit(quest, expected_progress=5)

    def test_saved_reward_only_campaign_and_history_remain_readable_without_changes(self):
        definition = self.definition(["badge_earned"])
        quest = Quest.objects.create(
            definition=definition, end_date=timezone.now() + timedelta(days=7),
            status=Quest.Status.FAILED, current_progress=2, reward_items_snapshot=[],
        )
        QuestParticipant.objects.create(quest=quest, user=self.child, contribution=2)
        before = self.saved_state()
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/quests/history/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["id"] for row in response.data], [quest.pk])
        error, result = self.wire("get_quest", {"quest_id": quest.pk})
        self.assertFalse(error, result)
        self.assertEqual((result["id"], result["current_progress"]), (quest.pk, 2))
        self.assertFalse(result["definition"]["catalog_available"])
        self.assertEqual(self.saved_state(), before)

    def test_existing_create_uuid_replay_recovers_original_campaign_after_rule_changes(self):
        params = self.payload(["habit_log"], request_id=str(uuid4()), assigned_to_id=self.child.pk)
        error, first = self.wire("create_quest_definition", params)
        self.assertFalse(error, first)
        QuestDefinition.objects.filter(pk=first["definition"]["id"]).update(
            trigger_filter={"allowed_triggers": ["badge_earned"]},
        )
        before = self.saved_state()
        error, retry = self.wire("create_quest_definition", params)
        self.assertFalse(error, retry)
        self.assertEqual(retry, first)
        self.assertEqual(self.saved_state(), before)
