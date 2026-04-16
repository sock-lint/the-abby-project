"""Tests for quest Celery tasks — expire_quests_task, apply_boss_rage_task."""
from django.test import TestCase
from django.utils import timezone

from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.quests.tasks import apply_boss_rage_task, expire_quests_task


class _Fixture(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.definition = QuestDefinition.objects.create(
            name="Boss", description="Beat it",
            quest_type="boss", target_value=100,
            duration_days=7, coin_reward=10, xp_reward=20,
        )


class ExpireQuestsTaskTests(_Fixture):
    def test_expires_past_due_quests(self):
        quest = Quest.objects.create(
            definition=self.definition, status="active",
            end_date=timezone.now() - timezone.timedelta(hours=1),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        expire_quests_task()
        quest.refresh_from_db()
        self.assertEqual(quest.status, "expired")

    def test_does_not_expire_future_quests(self):
        quest = Quest.objects.create(
            definition=self.definition, status="active",
            end_date=timezone.now() + timezone.timedelta(days=5),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        expire_quests_task()
        quest.refresh_from_db()
        self.assertEqual(quest.status, "active")


class ApplyBossRageTaskTests(_Fixture):
    def test_adds_rage_shield_to_idle_boss_quest(self):
        quest = Quest.objects.create(
            definition=self.definition, status="active",
            end_date=timezone.now() + timezone.timedelta(days=5),
            rage_shield=0,
        )
        participant = QuestParticipant.objects.create(
            quest=quest, user=self.child, contribution=0,
        )
        # Backdate the participant so it looks idle (no activity today).
        yesterday = timezone.now() - timezone.timedelta(days=1)
        QuestParticipant.objects.filter(pk=participant.pk).update(updated_at=yesterday)
        apply_boss_rage_task()
        quest.refresh_from_db()
        self.assertGreater(quest.rage_shield, 0)
