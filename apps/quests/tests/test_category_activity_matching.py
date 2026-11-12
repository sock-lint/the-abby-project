"""Category restrictions use the accepted source's frozen skill identities."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.habits.models import Habit, HabitLog, HabitSkillTag
from apps.habits.services import HabitService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.activity import record_activity, retry_pending_activity
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeActivity, ChallengeOccurrence, Quest, QuestDefinition
from apps.quests.services import QuestService
from apps.rpg.services import GameLoopService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CategoryActivityMatchingTests(TestCase):
    def setUp(self):
        household = make_family(
            "Category matching", parents=[{"username": "category-parent", "is_staff": True}],
            children=[{"username": "category-child"}, {"username": "category-sibling"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.category = SkillCategory.objects.create(name="Accepted category")
        self.other_category = SkillCategory.objects.create(name="Other category")
        self.skill = Skill.objects.create(category=self.category, name="Practice")
        self.other_skill = Skill.objects.create(category=self.other_category, name="Other practice")
        self.habit = Habit.objects.create(
            user=self.child, created_by=self.parent, name="A tagged habit", xp_reward=0,
        )
        HabitSkillTag.objects.create(habit=self.habit, skill=self.skill)
        self.client = APIClient()

    def payload(self, **values):
        return {
            "name": "Category practice", "description": "Three accepted actions", "quest_type": "collection",
            "target_value": 3,
            "trigger_filter": {"allowed_triggers": ["habit_log"], "skill_category_id": self.category.pk},
            **values,
        }

    def wire(self, tool, params, *, actor=None):
        with override_user(actor or self.parent):
            result = async_to_sync(mcp.call_tool)(tool, {"params": params, "confirmation": True})
        payload = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", payload, payload)
        return payload

    def private_quest(self, *, mcp_author=False):
        if mcp_author:
            result = self.wire("create_quest_definition", self.payload(
                request_id=str(uuid4()), assigned_to_id=self.child.pk,
            ))
            return Quest.objects.get(pk=result["quest"]["id"])
        self.client.force_authenticate(self.parent)
        response = self.client.post("/api/quests/", self.payload(assigned_to=self.child.pk), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Quest.objects.get(definition_id=response.data["id"])

    def log_rest(self):
        self.client.force_authenticate(self.child)
        response = self.client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {"direction", "xp_reward", "new_strength", "game_event"})
        return response.data

    def log_mcp(self):
        response = self.wire("log_habit", {"habit_id": self.habit.pk, "amount": 1}, actor=self.child)
        self.assertEqual(set(response), {"direction", "xp_reward", "new_strength", "game_event"})
        return response

    def assert_progress(self, quest, expected=1):
        quest.refresh_from_db()
        self.assertEqual(quest.current_progress, expected)

    def test_rest_private_campaign_counts_actual_matching_tagged_habit(self):
        quest = self.private_quest()
        self.log_rest()
        self.assert_progress(quest)

    def test_registered_mcp_authoring_and_habit_tool_count_matching_category(self):
        quest = self.private_quest(mcp_author=True)
        self.log_mcp()
        self.assert_progress(quest)

    def test_automatic_catalog_collection_counts_same_real_source_once(self):
        definition = QuestDefinition.objects.create(**self.payload(is_system=True))
        self.log_rest()
        self.assertTrue(ChallengeOccurrence.objects.filter(goal__catalog_definition=definition).exists())
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.progress, 1)
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type="habit_log")
        record_activity(self.child, "habit_log", {"habit_log_id": fact.source_id})
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 1)
        self.assertEqual(occurrence.contributions.count(), 1)

    def test_nonmatching_category_stays_excluded(self):
        quest = self.private_quest()
        HabitSkillTag.objects.filter(habit=self.habit).delete()
        HabitSkillTag.objects.create(habit=self.habit, skill=self.other_skill)
        self.log_rest()
        self.assert_progress(quest, 0)

    def test_one_of_multiple_source_categories_matches_without_multiple_credit(self):
        quest = self.private_quest()
        HabitSkillTag.objects.create(habit=self.habit, skill=self.other_skill)
        self.log_rest()
        self.assert_progress(quest)

    def test_source_fact_freezes_category_without_changing_native_habit_result(self):
        result = HabitService.log_tap(self.child, self.habit, 1)
        self.assertEqual(result, {"direction": 1, "xp_reward": 0, "new_strength": 1})
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type="habit_log")
        self.assertEqual(fact.context["skill_tags"], [{
            "skill_id": self.skill.pk, "category_id": self.category.pk, "xp_weight": 1,
        }])

    def test_trusted_source_overrides_an_incoming_category_claim(self):
        quest = self.private_quest()
        HabitSkillTag.objects.filter(habit=self.habit).delete()
        HabitSkillTag.objects.create(habit=self.habit, skill=self.other_skill)
        log = HabitLog.objects.create(user=self.child, habit=self.habit, direction=1)
        QuestService.record_progress(self.child, "habit_log", {
            "habit_log_id": log.pk, "skill_category_id": self.category.pk,
            "skill_tags": [{"skill_id": self.skill.pk, "category_id": self.category.pk}],
        })
        self.assert_progress(quest, 0)

    def test_foreign_source_cannot_attest_category(self):
        quest = self.private_quest()
        log = HabitLog.objects.create(user=self.sibling, habit=self.habit, direction=1)
        QuestService.record_progress(self.child, "habit_log", {
            "habit_log_id": log.pk, "skill_category_id": self.category.pk,
        })
        self.assert_progress(quest, 0)

    def test_accepted_fact_keeps_category_after_skill_reparent_and_habit_retagging(self):
        quest = self.private_quest()
        HabitService.log_tap(self.child, self.habit, 1)
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type="habit_log")
        before = deepcopy(fact.context)
        Skill.objects.filter(pk=self.skill.pk).update(category=self.other_category)
        HabitSkillTag.objects.filter(habit=self.habit).delete()
        HabitSkillTag.objects.create(habit=self.habit, skill=self.other_skill)
        QuestService.record_progress(self.child, "habit_log", {"habit_log_id": fact.source_id})
        self.assert_progress(quest)
        record_activity(self.child, "habit_log", {"habit_log_id": fact.source_id})
        fact.refresh_from_db()
        self.assertEqual(fact.context, before)

    def test_old_fact_without_category_evidence_is_not_reinterpreted_from_current_taxonomy(self):
        quest = self.private_quest()
        log = HabitLog.objects.create(user=self.child, habit=self.habit, direction=1)
        fact = ChallengeActivity.objects.create(
            user=self.child, source_type="habit_log", source_id=str(log.pk), trigger_type="habit_log",
            occurred_at=log.created_at, occurred_on=timezone.localdate(),
            context={"habit_id": self.habit.pk, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]},
        )
        before = deepcopy(fact.context)
        QuestService.record_progress(self.child, "habit_log", {"habit_log_id": log.pk})
        self.assert_progress(quest, 0)
        fact.refresh_from_db()
        self.assertEqual(fact.context, before)

    def test_legacy_internal_scalar_category_context_still_matches(self):
        quest = self.private_quest()
        QuestService.record_progress(self.child, "habit_log", {"skill_category_id": self.category.pk})
        self.assert_progress(quest)

    def test_pending_automatic_fact_keeps_category_on_repair_after_taxonomy_change(self):
        definition = QuestDefinition.objects.create(**self.payload(is_system=True))
        list_goals(self.child)
        with patch("apps.quests.goals._process", side_effect=ValueError("Synthetic pending evaluation")):
            HabitService.log_tap(self.child, self.habit, 1)
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type="habit_log")
        self.assertIsNone(fact.processed_at)
        before = deepcopy(fact.context)
        Skill.objects.filter(pk=self.skill.pk).update(category=self.other_category)
        self.assertEqual(retry_pending_activity(self.child), 1)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.progress, 1)
        self.assertEqual(occurrence.contributions.count(), 1)
        retry_pending_activity(self.child)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 1)
        fact.refresh_from_db()
        self.assertEqual(fact.context["skill_tags"], before["skill_tags"])

    def test_pending_tagged_fact_anchors_new_catalog_window_at_accepted_time(self):
        definition = QuestDefinition.objects.create(**self.payload(is_system=True))
        accepted_at = timezone.now()
        with patch("django.utils.timezone.now", return_value=accepted_at):
            with patch("apps.quests.goals._process", side_effect=ValueError("Synthetic pending evaluation")):
                HabitService.log_tap(self.child, self.habit, 1)
        with patch("django.utils.timezone.now", return_value=accepted_at + timedelta(hours=1)):
            list_goals(self.child)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.starts_at, accepted_at)

    def test_deferred_coop_keeps_evidence_captured_before_source_tags_change(self):
        definition = QuestDefinition.objects.create(**self.payload(created_by=self.parent))
        quest = QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])
        log = HabitLog.objects.create(user=self.child, habit=self.habit, direction=1)
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                with patch.object(GameLoopService, "record_challenge_activity", side_effect=ValueError("Synthetic fact delay")):
                    GameLoopService.on_task_completed(self.child, "habit_log", {"habit_log_id": log.pk})
                # The callback must use the accepted evidence, even if the
                # optional automatic-fact step fails before persisting it.
                Skill.objects.filter(pk=self.skill.pk).update(category=self.other_category)
        self.assert_progress(quest)
