from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import User
from apps.quests.models import QuestDefinition, Quest, QuestParticipant
from apps.quests.services import QuestService


class QuestServiceTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="questchild", password="test", role="child")
        self.boss_def = QuestDefinition.objects.create(
            name="Dragon Slayer", description="Defeat the dragon",
            quest_type="boss", target_value=100, duration_days=7,
            coin_reward=50, xp_reward=100, is_system=True,
        )
        self.collection_def = QuestDefinition.objects.create(
            name="Gather Feathers", description="Collect feathers",
            quest_type="collection", target_value=5, duration_days=3,
        )

    def test_start_quest(self):
        quest = QuestService.start_quest(self.child, self.boss_def.pk)
        self.assertEqual(quest.status, "active")
        self.assertEqual(quest.definition, self.boss_def)
        self.assertTrue(QuestParticipant.objects.filter(quest=quest, user=self.child).exists())

    def test_cannot_start_two_active_quests(self):
        QuestService.start_quest(self.child, self.boss_def.pk)
        with self.assertRaises(ValueError):
            QuestService.start_quest(self.child, self.collection_def.pk)

    def test_record_boss_progress(self):
        QuestService.start_quest(self.child, self.boss_def.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertIsNotNone(result)
        self.assertEqual(result["damage_dealt"], 15)
        self.assertFalse(result["completed"])

    def test_record_collection_progress(self):
        QuestService.start_quest(self.child, self.collection_def.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertEqual(result["damage_dealt"], 1)

    def test_quest_completes_when_target_reached(self):
        self.boss_def.target_value = 15
        self.boss_def.save()
        QuestService.start_quest(self.child, self.boss_def.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertTrue(result["completed"])
        self.assertIsNotNone(result["rewards"])

    def test_no_progress_without_active_quest(self):
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertIsNone(result)

    def test_trigger_filter_blocks_unmatched(self):
        filtered_def = QuestDefinition.objects.create(
            name="Chore Quest", description="Only chores",
            quest_type="collection", target_value=5,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestService.start_quest(self.child, filtered_def.pk)
        result = QuestService.record_progress(self.child, "clock_out")
        self.assertIsNone(result)  # clock_out not in allowed_triggers

    def test_expire_quests(self):
        quest = QuestService.start_quest(self.child, self.boss_def.pk)
        quest.end_date = timezone.now() - timedelta(hours=1)
        quest.save()
        expired_count = QuestService.expire_quests()
        self.assertEqual(expired_count, 1)
        quest.refresh_from_db()
        self.assertEqual(quest.status, "expired")

    def test_boss_rage(self):
        quest = QuestService.start_quest(self.child, self.boss_def.pk)
        # Simulate no progress today by backdating participant updated_at
        QuestParticipant.objects.filter(quest=quest).update(
            updated_at=timezone.now() - timedelta(days=1),
        )
        result = QuestService.apply_boss_rage()
        self.assertEqual(result["raged"], 1)
        self.assertEqual(result["decayed"], 0)
        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, 20)

    def test_get_active_quest(self):
        QuestService.start_quest(self.child, self.boss_def.pk)
        active = QuestService.get_active_quest(self.child)
        self.assertIsNotNone(active)
        self.assertEqual(active.definition.name, "Dragon Slayer")
