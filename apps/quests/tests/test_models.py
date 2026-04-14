from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant


class QuestDefinitionModelTest(TestCase):
    def test_create_boss_quest(self):
        qd = QuestDefinition.objects.create(
            name="Dragon Slayer",
            description="Defeat the dragon",
            quest_type="boss",
            target_value=500,
            duration_days=7,
            coin_reward=50,
            xp_reward=100,
            is_system=True,
        )
        self.assertIn("Boss Fight", str(qd))

    def test_create_collection_quest(self):
        qd = QuestDefinition.objects.create(
            name="Gather Feathers",
            description="Collect feathers",
            quest_type="collection",
            target_value=30,
        )
        self.assertIn("Collection", str(qd))


class QuestModelTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="questchild", password="test", role="child"
        )
        self.definition = QuestDefinition.objects.create(
            name="Test Quest",
            description="Test",
            quest_type="boss",
            target_value=100,
        )

    def test_create_active_quest(self):
        quest = Quest.objects.create(
            definition=self.definition,
            end_date=timezone.now() + timedelta(days=7),
        )
        self.assertEqual(quest.status, "active")
        self.assertEqual(quest.current_progress, 0)

    def test_progress_percent(self):
        quest = Quest.objects.create(
            definition=self.definition,
            current_progress=50,
            end_date=timezone.now() + timedelta(days=7),
        )
        self.assertEqual(quest.progress_percent, 50)

    def test_effective_target_with_rage(self):
        quest = Quest.objects.create(
            definition=self.definition,
            rage_shield=20,
            end_date=timezone.now() + timedelta(days=7),
        )
        self.assertEqual(quest.effective_target, 120)

    def test_is_expired(self):
        quest = Quest.objects.create(
            definition=self.definition,
            end_date=timezone.now() - timedelta(hours=1),
        )
        self.assertTrue(quest.is_expired)

    def test_participant(self):
        quest = Quest.objects.create(
            definition=self.definition,
            end_date=timezone.now() + timedelta(days=7),
        )
        participant = QuestParticipant.objects.create(
            quest=quest,
            user=self.child,
            contribution=25,
        )
        self.assertEqual(participant.contribution, 25)
