"""Quest completion loot follows its one-time payout, never the full game loop."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.movement.models import MovementType
from apps.movement.services import MovementSessionService
from apps.quests.goals import create_goal, ingest_activity, list_goals, set_pin
from apps.quests.models import (
    ChallengeActivity, ChallengeOccurrence, DailyBonus,
    Quest, QuestDefinition, QuestParticipant, QuestRewardItem, QuestSkillTag,
)
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


class QuestAccomplishmentLootTests(TestCase):
    def setUp(self):
        family = make_family(
            "Accomplishment household", parents=[{"username": "loot-parent"}],
            children=[{"username": "loot-child"}, {"username": "loot-sibling"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        category = SkillCategory.objects.create(name="Accomplishment skills")
        self.skill = Skill.objects.create(name="Effort", category=category)
        self.food = ItemDefinition.objects.create(
            slug="quest-loot-food", name="Quest discovery", item_type="food",
        )
        DropTable.objects.create(trigger_type=TriggerType.QUEST_COMPLETE, item=self.food)
        self.authored = ItemDefinition.objects.create(
            slug="quest-authored-food", name="Promised snack", item_type="food",
        )
        self.movement = MovementType.objects.create(name="Walk", slug="quest-loot-walk")

    def definition(self, name="One effort", *, system=False, repeatable=False):
        definition = QuestDefinition.objects.create(
            name=name, description="One qualifying activity", quest_type="collection",
            target_value=1, duration_days=7, coin_reward=7, xp_reward=11,
            trigger_filter={"allowed_triggers": ["movement_session"]},
            is_system=system, is_repeatable=repeatable,
            created_by=None if system else self.parent,
        )
        QuestSkillTag.objects.create(quest_definition=definition, skill=self.skill)
        QuestRewardItem.objects.create(quest_definition=definition, item=self.authored, quantity=2)
        return definition

    def fact(self, identity, *, at=None):
        return ingest_activity(
            self.child, "movement_session", identity, "movement_session",
            occurred_at=at or timezone.now(),
            context={"movement_type_id": self.movement.pk, "duration_minutes": 2},
        )

    def assert_loot(self, user, count):
        self.assertEqual(DropLog.objects.filter(
            user=user, trigger_type=TriggerType.QUEST_COMPLETE, item=self.food,
        ).count(), count)
        self.assertEqual(UserInventory.objects.get(user=user, item=self.food).quantity, count)

    def test_legacy_completion_adds_one_drop_and_preserves_authored_rewards(self):
        definition = self.definition()
        quest = QuestService.start_quest(self.child, definition.pk)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game_loop:
            result = QuestService.record_progress(self.child, "movement_session")
            self.assertIsNone(QuestService.record_progress(self.child, "movement_session"))
            QuestService._complete_quest(quest, self.child)
        game_loop.assert_not_called()
        self.assertTrue(result["completed"])
        self.assertEqual((result["rewards"]["coins"], result["rewards"]["xp"]), (7, 11))
        self.assertEqual([row["item_id"] for row in result["rewards"]["items"]], [self.authored.pk])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.authored).quantity, 2)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 11)
        self.assert_loot(self.child, 1)
        self.assertFalse(DropLog.objects.filter(user=self.sibling).exists())
        self.assertFalse(DailyBonus.objects.exists())
        self.assertIsNone(CharacterProfile.objects.get(user=self.child).last_active_date)

    def test_coop_completion_gives_each_recipient_one_drop_including_noncontributor(self):
        definition = self.definition()
        quest = QuestService.start_co_op_quest(definition.pk, [self.sibling, self.child])
        result = QuestService.record_progress(self.child, "movement_session")
        self.assertTrue(result["completed"])
        self.assertEqual(QuestParticipant.objects.get(quest=quest, user=self.sibling).contribution, 0)
        QuestService._complete_quest(quest, self.sibling)
        for user in (self.child, self.sibling):
            self.assert_loot(user, 1)
            self.assertEqual(UserInventory.objects.get(user=user, item=self.authored).quantity, 2)

    def test_saved_movement_completes_parallel_catalog_and_parent_goals_with_one_drop_each(self):
        self.definition("First catalog", system=True)
        self.definition("Second catalog", system=True)
        parent_goal = create_goal(self.parent, self.child, {
            "name": "Household walk", "metric": "count", "target": Decimal(1),
            "unit": "actions", "trigger_type": "movement_session", "period": "from_today",
        })
        session = MovementSessionService.log_session(
            self.child, movement_type=self.movement, duration_minutes=2,
        )
        self.assertEqual(ChallengeOccurrence.objects.filter(status="completed").count(), 3)
        self.assert_loot(self.child, 3)
        self.fact(session.pk, at=session.created_at)
        set_pin(self.child, f"goal:{parent_goal.pk}")
        list_goals(self.child)
        self.assert_loot(self.child, 3)
        self.assertEqual(ChallengeActivity.objects.count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.authored).quantity, 4)
        self.assertFalse(DropLog.objects.filter(user=self.sibling).exists())

    def test_automatic_completion_does_not_reenter_loop_or_create_reward_event_facts(self):
        definition = self.definition(system=True)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as game_loop:
            result = self.fact("first")
        game_loop.assert_not_called()
        self.assertTrue(result["goals"][0]["completed"])
        self.assert_loot(self.child, 1)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.reward_receipt["coins"], 7)
        self.assertEqual([row["item_id"] for row in occurrence.reward_receipt["items"]], [self.authored.pk])
        self.assertEqual(list(ChallengeActivity.objects.values_list("trigger_type", flat=True)), ["movement_session"])
        self.assertFalse(DailyBonus.objects.exists())
        self.assertIsNone(CharacterProfile.objects.get(user=self.child).last_active_date)

    def test_each_repeat_window_gets_one_drop_without_replaying_previous_completion(self):
        self.definition(system=True, repeatable=True)
        now = timezone.now()
        with patch("django.utils.timezone.now", return_value=now):
            self.fact("first-window", at=now)
        later = now + timedelta(days=8)
        with patch("django.utils.timezone.now", return_value=later):
            self.fact("next-window", at=later)
            self.fact("next-window", at=later)
        self.assertEqual(ChallengeOccurrence.objects.filter(status="completed").count(), 2)
        self.assert_loot(self.child, 2)

    def test_legacy_drop_failure_rolls_back_completion_and_allows_one_retry(self):
        definition = self.definition()
        quest = QuestService.start_quest(self.child, definition.pk)
        with patch.object(DropLog.objects, "create", side_effect=RuntimeError("loot receipt failed")):
            with self.assertRaisesRegex(RuntimeError, "loot receipt failed"):
                QuestService.record_progress(self.child, "movement_session")
        quest.refresh_from_db()
        self.assertEqual((quest.status, quest.current_progress), ("active", 0))
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        QuestService.record_progress(self.child, "movement_session")
        self.assert_loot(self.child, 1)

    def test_automatic_drop_failure_keeps_fact_retryable_without_partial_rewards(self):
        self.definition(system=True)
        with patch.object(DropLog.objects, "create", side_effect=RuntimeError("loot receipt failed")):
            with self.assertRaisesRegex(RuntimeError, "loot receipt failed"):
                self.fact("retry-source")
        self.assertIsNone(ChallengeActivity.objects.get().processed_at)
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.fact("retry-source")
        self.fact("retry-source")
        self.assert_loot(self.child, 1)

    def test_completed_historical_markers_do_not_backfill_loot_on_reads_or_new_work(self):
        definition = self.definition()
        quest = QuestService.start_quest(self.child, definition.pk)
        Quest.objects.filter(pk=quest.pk).update(status="completed", current_progress=1)
        automatic = self.definition("Historical catalog", system=True)
        list_goals(self.child)
        now = timezone.now()
        ChallengeOccurrence.objects.filter(goal__catalog_definition=automatic).update(
            status="completed", progress=1, completed_at=now, awarded_at=now,
            reward_receipt={"coins": 7, "xp": 11, "items": []},
        )
        list_goals(self.child)
        self.fact("new-after-historical")
        QuestService._complete_quest(quest, self.child)
        self.assertFalse(DropLog.objects.exists())
        self.assertFalse(UserInventory.objects.exists())
