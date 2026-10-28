"""New offers need one real source satisfying all saved rule restrictions."""
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.habits.models import Habit, HabitSkillTag
from apps.mcp_server.context import override_user
from apps.mcp_server.models import MCPMutationReceipt
from apps.mcp_server.server import mcp
from apps.quests.goals import list_goals
from apps.quests.models import (
    ChallengeActivity, ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant,
)
from apps.quests.progress_sources import has_progress_source
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.workbench import create_draft, describe_workbench, save_draft
from apps.rpg.content.workbench_validation import challenge_trigger_status
from apps.rpg.models import UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FilteredProgressAdmissionTests(TestCase):
    def setUp(self):
        household = make_family(
            "Filtered challenge admission",
            parents=[{"username": "filtered-parent", "is_staff": True}],
            children=[{"username": "filtered-child"}, {"username": "filtered-sibling"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.category = SkillCategory.objects.create(name="Selected skill category")
        self.skill = Skill.objects.create(name="Selected practice", category=self.category)
        self.client = APIClient()

    def filters(self, triggers=None, **selectors):
        return {"allowed_triggers": ["creation_logged"] if triggers is None else triggers,
                "skill_category_id": self.category.pk, **selectors}

    def payload(self, **values):
        return {"name": f"Filtered campaign {uuid4()}", "description": "Synthetic saved-work campaign",
                "quest_type": "collection", "target_value": 3, "trigger_filter": self.filters(), **values}

    def definition(self, **values):
        return QuestDefinition.objects.create(**self.payload(is_system=True, **values))

    def state(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            QuestDefinition, Quest, QuestParticipant, ChallengeGoal, ChallengeOccurrence,
            ChallengeActivity, MCPMutationReceipt, CoinLedger, SkillProgress, UserInventory,
        )}

    def wire(self, name, params):
        with override_user(self.parent):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        if isinstance(result, tuple):
            return False, result[1]
        return bool(result.isError), result.structuredContent

    def test_rest_private_autoassignment_rejects_category_without_source_evidence(self):
        self.client.force_authenticate(self.parent)
        before = self.state()
        response = self.client.post("/api/quests/", self.payload(assigned_to=self.child.pk), format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.state(), before)

    def test_registered_mcp_private_creation_rejects_without_definition_or_receipt(self):
        before = self.state()
        error, result = self.wire("create_quest_definition", self.payload(
            request_id=str(uuid4()), assigned_to_id=self.child.pk,
        ))
        self.assertTrue(error, result)
        self.assertEqual(result["error"]["code"], "invalid_request")
        self.assertEqual(self.state(), before)

    def test_native_solo_rejects_without_accepting_a_campaign(self):
        definition = self.definition()
        before = self.state()
        with self.assertRaises(ValueError):
            QuestService.start_quest(self.child, definition.pk)
        self.assertEqual(self.state(), before)

    def test_native_coop_rejects_without_accepting_either_participant(self):
        definition = self.definition()
        before = self.state()
        with self.assertRaises(ValueError):
            QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])
        self.assertEqual(self.state(), before)

    def test_rest_start_cannot_consume_scroll_for_a_category_without_evidence(self):
        from apps.rpg.models import ItemDefinition

        definition = self.definition()
        scroll = ItemDefinition.objects.create(slug="filtered-scroll", name="Scroll", item_type="quest_scroll")
        UserInventory.objects.create(user=self.child, item=scroll, quantity=2)
        self.client.force_authenticate(self.child)
        before = self.state()
        response = self.client.post("/api/quests/start/", {
            "definition_id": definition.pk, "scroll_item_id": scroll.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.state(), before)

    def test_automatic_catalog_does_not_accept_an_impossible_category_window(self):
        definition = self.definition()
        list_goals(self.child)
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=definition).exists())
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_rest_and_registered_mcp_catalog_report_the_offer_unavailable(self):
        definition = self.definition()
        self.client.force_authenticate(self.parent)
        response = self.client.get("/api/quests/catalog/")
        self.assertEqual(response.status_code, 200, response.data)
        error, result = self.wire("list_quest_catalog", {})
        self.assertFalse(error, result)
        row = next(row for row in response.data if row["id"] == definition.pk)
        self.assertFalse(row["catalog_available"])
        # MCP's authored-choice list omits unavailable rows altogether.
        self.assertFalse(any(row["id"] == definition.pk for row in result["quest_definitions"]))

    def test_workbench_projection_does_not_advertise_an_impossible_offer(self):
        for filters in (self.filters(), {"allowed_triggers": ["chore_complete"], "on_time": True}):
            with self.subTest(filters=filters):
                definition = self.definition(trigger_filter=filters)
                metadata = describe_workbench(self.parent)
                row = next(row for row in metadata["catalog"]["quests"] if row["id"] == definition.pk)
                self.assertFalse(row["automatic_tracking_available"])
                self.assertFalse(row["available_for_new_user"])
                # The activity is supported; explain why its selected filters
                # cannot all match without calling the activity unsupported.
                self.assertEqual(row["unsupported_triggers"], [])
                warnings = [finding for finding in metadata["audits"]["findings"]
                            if finding["section"] == "quests" and finding["id"] == definition.pk]
                self.assertEqual(len(warnings), 1)
                self.assertEqual(warnings[0]["code"], "unreachable_challenge_filters")
                self.assertEqual(warnings[0]["severity"], "warning")
                self.assertIn("Every selected filter must match the same saved-work activity", warnings[0]["detail"])

    def test_workbench_save_rejects_impossible_filter_without_saving_changes(self):
        from apps.rpg.models import RPGContentDraft

        for filters in (self.filters(), {"allowed_triggers": ["chore_complete"], "on_time": True}):
            with self.subTest(filters=filters):
                draft = create_draft(self.parent, "Unreachable activity filters")
                before = list(RPGContentDraft.objects.values())
                with self.assertRaises(ContentPackError) as raised:
                    save_draft(self.parent, draft["id"], draft["revision"], [{
                        "section": "quests", "object_id": None, "key": "filtered-rule",
                        "values": self.payload(trigger_filter=filters),
                    }])
                self.assertEqual(list(RPGContentDraft.objects.values()), before)
                self.assertFalse(QuestDefinition.objects.exists())
                self.assertIn("Choose compatible activities and filters", str(raised.exception))
                self.assertIn("Every selected filter must match the same saved-work activity", str(raised.exception))

    def test_one_candidate_must_supply_every_active_selector(self):
        cases = [
            # Each trigger can satisfy one restriction, but no source has both.
            (["project_complete", "homework_complete"], {"project_id": 1, "on_time": True}, False),
            (["chore_complete", "homework_complete"], {"chore_ids": [1], "on_time": True}, False),
            (["savings_goal_complete", "habit_log"], {"savings_goal_id": 1, "skill_category_id": self.category.pk}, False),
            (["reading_logged"], {"skill_category_id": self.category.pk}, False),
            (["homework_created"], {"skill_category_id": self.category.pk}, False),
            (["journal_entry"], {"skill_category_id": self.category.pk}, False),
            (["expedition_returned"], {"skill_category_id": self.category.pk}, False),
            (["chore_complete"], {"on_time": True}, False),
            (["homework_complete"], {"project_id": 1}, False),
            (["creation_logged", "habit_log"], {"skill_category_id": self.category.pk}, True),
            (["homework_created", "homework_complete"], {"skill_category_id": self.category.pk, "on_time": True}, True),
            (["project_complete"], {"project_id": 1, "skill_category_id": self.category.pk}, True),
            (["clock_out"], {"project_id": 1, "skill_category_id": self.category.pk}, True),
            (["milestone_complete"], {"project_id": 1, "skill_category_id": self.category.pk}, True),
            (["chore_complete"], {"chore_ids": [1], "skill_category_id": self.category.pk}, True),
            (["movement_session"], {"skill_category_id": self.category.pk}, True),
            (["savings_goal_complete"], {"savings_goal_id": 1}, True),
        ]
        for triggers, selectors, expected in cases:
            filters = {"allowed_triggers": triggers, **selectors}
            with self.subTest(filters=filters):
                self.assertIs(has_progress_source("collection", filters), expected)
                self.assertIs(challenge_trigger_status("collection", filters)["available"], expected)

    def test_boss_damage_and_false_or_empty_selectors_keep_their_contract(self):
        for quest_type in ("collection", "boss"):
            for filters in (None, {}, {"allowed_triggers": None}, {"allowed_triggers": []}, {
                "allowed_triggers": ["habit_log"], "on_time": False, "chore_ids": [],
                "project_id": None, "skill_category_id": None, "savings_goal_id": None,
            }):
                with self.subTest(quest_type=quest_type, filters=filters):
                    self.assertTrue(has_progress_source(quest_type, filters))
        self.assertTrue(has_progress_source("collection", {"allowed_triggers": ["creation_logged"]}))
        self.assertFalse(has_progress_source("boss", {"allowed_triggers": ["creation_logged"]}))
        self.assertTrue(has_progress_source("boss", self.filters(["creation_logged", "habit_log"])))
        self.assertEqual(challenge_trigger_status("collection", {
            "allowed_triggers": ["perfect_day", "habit_log"], "skill_category_id": self.category.pk,
        }), {"available": True, "unsupported": ["perfect_day"]})

    def test_mixed_category_rule_advances_from_actual_tagged_habit(self):
        self.client.force_authenticate(self.parent)
        response = self.client.post("/api/quests/", self.payload(
            trigger_filter=self.filters(["creation_logged", "habit_log"]), assigned_to=self.child.pk,
        ), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        quest = Quest.objects.get(definition_id=response.data["id"])
        habit = Habit.objects.create(user=self.child, created_by=self.parent, name="Real tagged habit", xp_reward=0)
        HabitSkillTag.objects.create(habit=habit, skill=self.skill)
        self.client.force_authenticate(self.child)
        result = self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        quest.refresh_from_db()
        self.assertEqual(quest.current_progress, 1)
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type="habit_log")
        self.assertEqual(fact.context["skill_tags"][0]["category_id"], self.category.pk)

    def test_previously_accepted_category_goal_keeps_its_saved_window(self):
        definition = self.definition()
        # Simulate the old admission predicate for this already accepted offer.
        with patch("apps.quests.progress_sources.has_progress_source", return_value=True):
            list_goals(self.child)
        saved = deepcopy(list(ChallengeOccurrence.objects.values()))
        goal_id = ChallengeGoal.objects.get(catalog_definition=definition).pk
        list_goals(self.child)
        self.assertEqual(list(ChallengeOccurrence.objects.values()), saved)
        self.assertTrue(ChallengeGoal.objects.filter(pk=goal_id, catalog_definition=definition).exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_saved_creation_uuid_replays_before_new_offer_admission(self):
        params = self.payload(request_id=str(uuid4()), assigned_to_id=self.child.pk)
        with patch("apps.quests.progress_sources.has_progress_source", return_value=True):
            error, first = self.wire("create_quest_definition", params)
        self.assertFalse(error, first)
        before = self.state()
        with patch("apps.quests.progress_sources.require_progress_source", side_effect=AssertionError("Replay must not re-admit")):
            error, replay = self.wire("create_quest_definition", params)
        self.assertFalse(error, replay)
        self.assertEqual(replay, first)
        self.assertEqual(self.state(), before)
