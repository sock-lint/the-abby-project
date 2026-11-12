from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParentPersonalRewardsTests(TestCase):
    def setUp(self):
        family = make_family("Personal rewards", parents=[{"username": "reward-parent"}], children=[{"username": "reward-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.reward = Reward.objects.create(family=family.family, name="Shared treat", cost_coins=10)
        Reward.objects.create(family=family.family, name="Unavailable treat", cost_coins=10, is_active=False)
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.client.credentials(HTTP_X_ABBY_SPACE="personal")

    def test_parent_personal_shop_shows_only_available_rewards(self):
        response = self.client.get("/api/rewards/")
        self.assertEqual([row["id"] for row in response.data["results"]], [self.reward.pk])
        self.client.credentials()
        self.assertEqual(len(self.client.get("/api/rewards/").data["results"]), 2)

    def test_parent_spends_own_coins_and_keeps_existing_approval_requirement(self):
        CoinLedger.objects.create(user=self.parent, amount=30, reason="adjustment")
        CoinLedger.objects.create(user=self.child, amount=70, reason="adjustment")
        response = self.client.post(f"/api/rewards/{self.reward.pk}/redeem/")
        self.assertEqual(response.status_code, 201, response.data)
        redemption = RewardRedemption.objects.get(pk=response.data["id"])
        self.assertEqual(redemption.user, self.parent)
        self.assertEqual(redemption.status, "pending")
        self.assertEqual(self.client.get("/api/coins/").data["balance"], 20)
