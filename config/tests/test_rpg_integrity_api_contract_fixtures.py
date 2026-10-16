"""Earned character progress and purchased promises through real endpoints."""
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory
from apps.achievements.services import SkillService
from apps.accounts.models import User
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests import test_avatar_api_contract_fixtures as avatar_fixtures


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
