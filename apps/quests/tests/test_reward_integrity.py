"""Legacy quest promises stay one-time and pay every co-op participant."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.notifications.models import Notification
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestRewardItem, QuestSkillTag
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


class QuestRewardIntegrityTests(TestCase):
    def setUp(self):
        self.family = make_family(
            "Quest household", parents=[{"username": "quest-parent"}],
            children=[{"username": "quest-first"}, {"username": "quest-second"}],
        )
        self.first, self.second = self.family.children
        self.other = make_family("Other household", children=[{"username": "quest-outsider"}]).children[0]
        self.definition = QuestDefinition.objects.create(
            name="Team effort", description="A saved legacy challenge",
            created_by=self.family.parents[0],
            quest_type="collection", target_value=2, coin_reward=13, xp_reward=24,
        )
        category = SkillCategory.objects.create(name="Quest reward skill")
        self.skill = Skill.objects.create(name="Teamwork", category=category)
        QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill)
        self.item = ItemDefinition.objects.create(
            slug="quest-reward-food", name="Quest reward food", item_type="food",
        )
        QuestRewardItem.objects.create(quest_definition=self.definition, item=self.item, quantity=2)
        self.client = APIClient()

    def _complete_single(self):
        quest = QuestService.start_quest(self.first, self.definition.pk)
        QuestService.record_progress(self.first, "chore_complete")
        QuestService.record_progress(self.first, "chore_complete")
        return quest

    def test_completed_nonrepeatable_quest_cannot_restart_via_child_api(self):
        self._complete_single()
        self.client.force_authenticate(self.first)
        response = self.client.post("/api/quests/start/", {"definition_id": self.definition.pk}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Quest.objects.filter(definition=self.definition).count(), 1)

    def test_parent_assignment_cannot_restart_completed_nonrepeatable_quest(self):
        self._complete_single()
        self.client.force_authenticate(self.family.parents[0])
        response = self.client.post(
            f"/api/quests/{self.definition.pk}/assign/", {"user_id": self.first.pk}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(QuestParticipant.objects.filter(user=self.first).count(), 1)

    def test_coop_rejects_completed_nonrepeatable_member_without_assigning_others(self):
        self._complete_single()
        self.client.force_authenticate(self.family.parents[0])
        response = self.client.post(
            f"/api/quests/{self.definition.pk}/co-op/",
            {"user_ids": [self.second.pk, self.first.pk]}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(QuestParticipant.objects.filter(user=self.second).exists())

    def test_failed_and_expired_attempts_remain_retryable(self):
        for status in (Quest.Status.FAILED, Quest.Status.EXPIRED):
            with self.subTest(status=status):
                quest = QuestService.start_quest(self.first, self.definition.pk)
                Quest.objects.filter(pk=quest.pk).update(status=status)
        quest = QuestService.start_co_op_quest(self.definition.pk, [self.second, self.first])
        self.assertEqual(quest.status, Quest.Status.ACTIVE)

    def test_repeatable_completion_can_start_again(self):
        self.definition.is_repeatable = True
        self.definition.save(update_fields=["is_repeatable"])
        self._complete_single()
        self.assertEqual(QuestService.start_quest(self.first, self.definition.pk).status, Quest.Status.ACTIVE)

    def _assert_full_rewards(self):
        for child in self.family.children:
            self.assertEqual(list(CoinLedger.objects.filter(user=child).values_list("amount", flat=True)), [13])
            self.assertEqual(SkillProgress.objects.get(user=child, skill=self.skill).xp_points, 24)
            self.assertEqual(UserInventory.objects.get(user=child, item=self.item).quantity, 2)
            self.assertEqual(ActivityEvent.objects.filter(subject=child, event_type="quest.complete").count(), 1)
            self.assertEqual(Notification.objects.filter(user=child, title="Challenge complete: Team effort!").count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.other).exists())
        self.assertFalse(SkillProgress.objects.filter(user=self.other).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.other).exists())
        self.assertFalse(Notification.objects.filter(user=self.other).exists())

    def test_coop_pays_full_reward_to_every_member_including_zero_contribution(self):
        quest = QuestService.start_co_op_quest(self.definition.pk, [self.second, self.first])
        QuestService.record_progress(self.second, "chore_complete")
        result = QuestService.record_progress(self.second, "chore_complete")
        self.assertTrue(result["completed"])
        self.assertEqual((result["rewards"]["coins"], result["rewards"]["xp"]), (13, 24))
        self._assert_full_rewards()
        self.assertEqual(QuestParticipant.objects.get(quest=quest, user=self.first).contribution, 0)
        self.assertIsNone(QuestService.record_progress(self.first, "chore_complete"))
        # A stale direct completion retry is also harmless.
        QuestService._complete_quest(quest, self.second)
        self._assert_full_rewards()

    def test_late_recipient_failure_rolls_back_entire_completion_and_retries_once(self):
        quest = QuestService.start_co_op_quest(self.definition.pk, [self.second, self.first])
        QuestService.record_progress(self.second, "chore_complete")
        from apps.notifications.services import notify

        def fail_late_recipient(user, *args, **kwargs):
            if user.pk == self.second.pk:
                raise RuntimeError("second participant notification failed")
            return notify(user, *args, **kwargs)

        with patch("apps.notifications.services.notify", side_effect=fail_late_recipient):
            with self.assertRaisesRegex(RuntimeError, "second participant"):
                QuestService.record_progress(self.second, "chore_complete")
        quest.refresh_from_db()
        self.assertEqual((quest.status, quest.current_progress), (Quest.Status.ACTIVE, 1))
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())
        self.assertFalse(UserInventory.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(ActivityEvent.objects.filter(event_type="quest.complete").exists())
        self.assertTrue(QuestService.record_progress(self.second, "chore_complete")["completed"])
        self._assert_full_rewards()

    def test_coop_uses_each_recipients_xp_boost_and_egg_salvage_eligibility(self):
        from apps.pets.models import PetSpecies, PotionType, UserMount
        from apps.rpg.models import CharacterProfile

        CharacterProfile.objects.filter(user=self.first).update(xp_boost_expires_at=timezone.now() + timedelta(hours=1))
        species = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        potion = PotionType.objects.create(slug="base", name="Base")
        UserMount.objects.create(user=self.first, species=species, potion=potion)
        egg = ItemDefinition.objects.create(
            slug="chick-egg", name="Chick egg", item_type="egg", pet_species=species, coin_value=3,
            metadata={"species": "chick"},
        )
        QuestRewardItem.objects.create(quest_definition=self.definition, item=egg, quantity=2)
        QuestService.start_co_op_quest(self.definition.pk, [self.second, self.first])
        QuestService.record_progress(self.second, "chore_complete")
        result = QuestService.record_progress(self.second, "chore_complete")

        self.assertEqual(SkillProgress.objects.get(user=self.first, skill=self.skill).xp_points, 48)
        self.assertEqual(SkillProgress.objects.get(user=self.second, skill=self.skill).xp_points, 24)
        self.assertEqual(sum(CoinLedger.objects.filter(user=self.first).values_list("amount", flat=True)), 19)
        self.assertEqual(sum(CoinLedger.objects.filter(user=self.second).values_list("amount", flat=True)), 13)
        self.assertFalse(UserInventory.objects.filter(user=self.first, item=egg).exists())
        self.assertEqual(UserInventory.objects.get(user=self.second, item=egg).quantity, 2)
        self.assertFalse(any("salvaged_to_coins" in reward for reward in result["rewards"]["items"]))
