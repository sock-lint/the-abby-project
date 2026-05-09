"""Notification fan-out from the GameLoopService pipeline.

Pins the two new types added in migration 0008 that ride on the loop:

- ``DROP_RECEIVED`` — used to be mis-labeled as ``BADGE_EARNED`` (so a
  drop and a real badge looked indistinguishable in the bell). Now fired
  by ``_step_drops`` once a drop roll lands.
- ``QUEST_COMPLETED`` — used to live only as an in-memory entry in the
  loop result, never reached the user's notification feed. Now fired by
  ``_step_quest_progress`` when ``QuestService.record_progress`` reports
  a completion.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import Notification, NotificationType
from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.rpg.models import (
    CharacterProfile, DropTable, ItemDefinition,
)
from apps.rpg.services import GameLoopService


class DropReceivedNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dropkid", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)
        self.item = ItemDefinition.objects.create(
            name="Dragon Egg",
            icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            rarity=ItemDefinition.Rarity.COMMON,
        )
        DropTable.objects.create(
            trigger_type=DropTable.TriggerType.CLOCK_OUT,
            item=self.item,
            weight=10,
            min_level=0,
        )

    @patch("apps.rpg.services.random.choices")
    @patch("apps.rpg.services.random.random")
    def test_drop_emits_drop_received_not_badge_earned(self, mock_random, mock_choices):
        """The notification carries ``DROP_RECEIVED``, not the legacy
        ``BADGE_EARNED`` label that confused the bell before migration 0008."""
        mock_random.return_value = 0  # always pass drop-rate gate
        entry = DropTable.objects.get(item=self.item)
        mock_choices.return_value = [entry]

        GameLoopService.on_task_completed(self.user, "clock_out", {})

        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                notification_type=NotificationType.DROP_RECEIVED,
            ).exists(),
        )
        self.assertFalse(
            Notification.objects.filter(
                user=self.user,
                notification_type=NotificationType.BADGE_EARNED,
                title__icontains="Dragon Egg",
            ).exists(),
            "Drops must not still emit the legacy BADGE_EARNED label.",
        )


class QuestCompletedNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="questkid", password="pw", role="child",
        )
        CharacterProfile.objects.get_or_create(user=self.user)
        # Collection quest sized 1 so a single trigger completes it.
        self.definition = QuestDefinition.objects.create(
            name="One-Shot Quest",
            description="Trigger once to win",
            quest_type="collection",
            target_value=1,
            duration_days=7,
            coin_reward=10,
            xp_reward=10,
        )
        self.quest = Quest.objects.create(
            definition=self.definition,
            status=Quest.Status.ACTIVE,
            end_date=timezone.now() + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=self.quest, user=self.user)

    def test_completion_fires_quest_completed_notification(self):
        # Trigger a chore_complete which collection quests count as 1.
        GameLoopService.on_task_completed(
            self.user, "chore_complete", {},
        )

        self.quest.refresh_from_db()
        self.assertEqual(self.quest.status, Quest.Status.COMPLETED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                notification_type=NotificationType.QUEST_COMPLETED,
            ).exists(),
            "Expected a QUEST_COMPLETED notification once the quest finishes.",
        )
