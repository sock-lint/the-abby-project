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
    def _make_idle_quest(self, rage_shield=0):
        quest = Quest.objects.create(
            definition=self.definition, status="active",
            end_date=timezone.now() + timezone.timedelta(days=5),
            rage_shield=rage_shield,
        )
        participant = QuestParticipant.objects.create(
            quest=quest, user=self.child, contribution=0,
        )
        # Backdate participant so it looks idle today.
        yesterday = timezone.now() - timezone.timedelta(days=1)
        QuestParticipant.objects.filter(pk=participant.pk).update(updated_at=yesterday)
        return quest

    def test_adds_rage_shield_to_idle_boss_quest(self):
        quest = self._make_idle_quest()
        apply_boss_rage_task()
        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, 20)

    def test_rage_shield_caps_at_100(self):
        """Rage climbs 20/day until it hits the cap, then plateaus."""
        from apps.quests.services import QuestService, RAGE_SHIELD_CAP

        quest = self._make_idle_quest(rage_shield=0)
        # Run the task 10× — should saturate at the cap, not keep climbing.
        for _ in range(10):
            QuestService.apply_boss_rage()
        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, RAGE_SHIELD_CAP)

    def test_rage_shield_decays_when_progress_resumes(self):
        """Once the user returns and makes progress, rage bleeds off."""
        from apps.quests.services import QuestService

        quest = self._make_idle_quest(rage_shield=60)
        # Touch the participant as if they made progress today.
        QuestParticipant.objects.filter(quest=quest).update(updated_at=timezone.now())

        result = QuestService.apply_boss_rage()
        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, 40)
        self.assertEqual(result["decayed"], 1)
        self.assertEqual(result["raged"], 0)

    def test_rage_shield_decay_floor_is_zero(self):
        """Decay can't drive rage below zero even if the step would overshoot."""
        from apps.quests.services import QuestService

        quest = self._make_idle_quest(rage_shield=10)
        QuestParticipant.objects.filter(quest=quest).update(updated_at=timezone.now())

        QuestService.apply_boss_rage()
        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, 0)
