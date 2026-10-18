"""Earned character progress and purchased promises through real endpoints."""
from unittest.mock import patch

from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APITransactionTestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.achievements.services import SkillService
from apps.accounts.models import User
from apps.habits.models import Habit
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestRewardItem, QuestSkillTag
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests import test_avatar_api_contract_fixtures as avatar_fixtures
from config.tests.factories import make_family


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class RpgIntegrityApiFixtureTests(APITestCase):
    setUp = avatar_fixtures.AvatarApiResponseFixtureTests.setUp
    assert_response_fixture = avatar_fixtures.AvatarApiResponseFixtureTests.assert_response_fixture

    def test_earned_character_progress_and_terminal_level(self):
        category = SkillCategory.objects.create(name="Fixture practice")
        reading = Skill.objects.create(name="Fixture reading", category=category)
        making = Skill.objects.create(name="Fixture making", category=category)
        SkillService.award_xp(self.child, reading, 125)
        SkillService.award_xp(self.child, making, 250)
        response = self.client.get("/api/character/")
        self.assertEqual(response.json()["level"], 2)
        self.assertEqual(response.json()["total_xp"], 375)
        self.assertEqual(response.json()["xp_in_level"], 75)
        self.assertEqual(response.json()["xp_needed_for_level"], 300)
        self.assert_response_fixture(response, "character-progression-earned.json")

        SkillService.award_xp(self.child, reading, 2125)
        response = self.client.get("/api/character/")
        self.assertEqual(response.json()["level"], 6)
        self.assertEqual(response.json()["total_xp"], 2500)
        self.assertEqual(response.json()["xp_needed_for_level"], 0)
        self.assert_response_fixture(response, "character-progression-max.json")

    def test_redemption_keeps_original_item_kind_and_cost_after_offer_edit(self):
        parent = User.objects.create_user(
            id=8, username="fixture-rpg-parent", role="parent", family=self.child.family,
        )
        frame = ItemDefinition.objects.create(
            id=601, name="Fixture promised frame", item_type="cosmetic_frame", icon="frame",
        )
        reward = Reward.objects.create(
            id=701, family=self.child.family, name="Fixture frame request", cost_coins=100,
            fulfillment_kind="digital_item", item_definition=frame,
        )
        CoinService.award_coins(self.child, 500, CoinLedger.Reason.ADJUSTMENT)
        with connection.cursor() as cursor:
            for statement in connection.ops.sequence_reset_sql(no_style(), [RewardRedemption]):
                cursor.execute(statement)
        requested = self.client.post(f"/api/rewards/{reward.pk}/redeem/", {}, format="json")
        self.assertEqual(requested.status_code, 201)
        redemption_id = requested.json()["id"]

        self.client.force_authenticate(user=parent)
        edited = self.client.patch(f"/api/rewards/{reward.pk}/", {
            "cost_coins": 200, "fulfillment_kind": "real_world", "item_definition": None,
        }, format="json")
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["fulfillment_kind"], "real_world")

        self.client.force_authenticate(user=self.child)
        pending = self.client.get(f"/api/redemptions/{redemption_id}/")
        self.assertEqual(pending.json()["reward"]["fulfillment_kind"], "digital_item")
        self.assertEqual(pending.json()["reward"]["item_definition"], frame.pk)
        self.assertEqual(pending.json()["reward"]["cost_coins"], 100)
        self.assert_response_fixture(pending, "redemption-frozen-promise-pending.json")

        self.client.force_authenticate(user=parent)
        fulfilled = self.client.post(f"/api/redemptions/{redemption_id}/approve/", {}, format="json")
        self.assertEqual(fulfilled.status_code, 200)
        self.assertEqual(fulfilled.json()["status"], "fulfilled")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=frame).quantity, 1)
        self.assertEqual(CoinService.get_balance(self.child), 400)
        self.assert_response_fixture(fulfilled, "redemption-frozen-promise-fulfilled.json")
        self.client.post(f"/api/redemptions/{redemption_id}/approve/", {}, format="json")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=frame).quantity, 1)
        self.assertEqual(CoinService.get_balance(self.child), 400)


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class RpgRewardFollowupApiFixtureTests(APITransactionTestCase):
    """Source transactions finish before synchronous co-op progress begins."""

    reset_sequences = True
    setUp = avatar_fixtures.AvatarApiResponseFixtureTests.setUp
    assert_response_fixture = avatar_fixtures.AvatarApiResponseFixtureTests.assert_response_fixture

    def test_real_habit_completes_full_coop_rewards_and_rejects_nonrepeatable_restart(self):
        parent = User.objects.create_user(
            id=6, username="fixture-quest-parent", role="parent", family=self.child.family,
        )
        sibling = User.objects.create_user(
            id=8, username="fixture-quest-sibling", role="child", family=self.child.family,
        )
        outsider = make_family(
            "Other quest fixture family", family_id=14,
            children=[{"id": 99, "username": "fixture-quest-outsider"}],
        ).children[0]
        category = SkillCategory.objects.create(id=501, name="Fixture cooperation")
        skill = Skill.objects.create(id=502, name="Fixture teamwork", category=category)
        food = ItemDefinition.objects.create(
            id=601, name="Fixture team food", item_type="food", icon="food",
        )
        definition = QuestDefinition.objects.create(
            id=701, name="Fixture team effort", description="One saved habit for the team",
            quest_type="collection", target_value=1, coin_reward=13, xp_reward=24,
            trigger_filter={"allowed_triggers": ["habit_log"]}, created_by=parent,
        )
        QuestSkillTag.objects.create(quest_definition=definition, skill=skill)
        QuestRewardItem.objects.create(quest_definition=definition, item=food, quantity=2)
        habit = Habit.objects.create(
            id=9, name="Fixture team habit", user=self.child, created_by=parent,
            xp_reward=0, max_taps_per_day=2,
        )
        # This child already checked in today. Keep the only payout in this
        # scenario the quest promise, without replacing any reward service.
        CharacterProfile.objects.filter(user=self.child).update(
            last_active_date=timezone.localdate(), login_streak=1,
        )
        with connection.cursor() as cursor:
            for statement in connection.ops.sequence_reset_sql(no_style(), [Quest]):
                cursor.execute(statement)
        self.client.force_authenticate(user=parent)
        started = self.client.post(
            f"/api/quests/{definition.pk}/co-op/",
            {"user_ids": [sibling.pk, self.child.pk]}, format="json",
        )
        self.assertEqual(started.status_code, 201, started.data)
        quest = Quest.objects.get(pk=started.json()["id"])
        self.client.force_authenticate(user=self.child)
        with patch("apps.rpg.services.random.random", return_value=1):
            completed = self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json")
        body = self.assert_response_fixture(completed, "habit-coop-completed.json")
        rewards = body["game_event"]["quest"]["rewards"]
        self.assertEqual((rewards["coins"], rewards["xp"]), (13, 24))
        self.assertEqual(len(rewards["items"]), 1)
        self.assertEqual({key: rewards["items"][0][key] for key in (
            "item_id", "item_name", "item_icon", "quantity", "item_catalog_icon", "item_rarity", "item_type", "item_catalog_available",
        )}, {"item_id": food.pk, "item_name": food.name, "item_icon": "food", "quantity": 2, "item_catalog_icon": None,
             "item_rarity": "common", "item_type": "food", "item_catalog_available": True})
        self.assertIn("Adds 5 growth", rewards["items"][0]["item_effect_summary"])
        self.assertTrue(body["game_event"]["quest"]["completed"])
        quest.refresh_from_db()
        self.assertEqual(quest.status, Quest.Status.COMPLETED)
        self.assertEqual(QuestParticipant.objects.get(quest=quest, user=sibling).contribution, 0)

        def assert_saved_rewards():
            for participant in (self.child, sibling):
                self.assertEqual(list(CoinLedger.objects.filter(user=participant).values_list("amount", flat=True)), [13])
                self.assertEqual(SkillProgress.objects.get(user=participant, skill=skill).xp_points, 24)
                self.assertEqual(UserInventory.objects.get(user=participant, item=food).quantity, 2)
            for uninvolved in (parent, outsider):
                self.assertFalse(CoinLedger.objects.filter(user=uninvolved).exists())
                self.assertFalse(SkillProgress.objects.filter(user=uninvolved).exists())
                self.assertFalse(UserInventory.objects.filter(user=uninvolved).exists())

        assert_saved_rewards()
        # A later valid activity and a stale internal retry cannot repay the
        # completed campaign; the API still reports the new habit honestly.
        with patch("apps.rpg.services.random.random", return_value=1):
            repeated_activity = self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json")
        self.assertEqual(repeated_activity.status_code, 200)
        self.assertIsNone(repeated_activity.json()["game_event"]["quest"])
        QuestService._complete_quest(quest, self.child)
        rejected = self.client.post(
            "/api/quests/start/", {"definition_id": definition.pk, "scroll_item_id": None}, format="json",
        )
        self.assert_response_fixture(rejected, "quest-nonrepeatable-restart.json", status=400)
        self.assertEqual(Quest.objects.filter(definition=definition).count(), 1)
        assert_saved_rewards()
