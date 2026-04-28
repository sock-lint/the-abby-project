"""Reward + RewardRedemption family-scoping tests.

Family A's rewards must be invisible to Family B, and a parent cannot
redeem a reward owned by another family.
"""
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.rewards.models import Reward
from config.tests.factories import make_family


class RewardFamilyScopingTests(APITestCase):
    def setUp(self):
        self.a = make_family(
            "Family A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "Family B",
            parents=[{"username": "bp"}],
            children=[{"username": "bc"}],
        )
        # Each family authors one reward of the same name to confirm the
        # per-family unique constraint replaced the global one.
        self.a_reward = Reward.objects.create(
            name="Movie Night", cost_coins=20, family=self.a.family,
        )
        self.b_reward = Reward.objects.create(
            name="Movie Night", cost_coins=30, family=self.b.family,
        )
        self.a_parent_token = Token.objects.create(user=self.a.parents[0])
        self.b_parent_token = Token.objects.create(user=self.b.parents[0])
        self.a_child_token = Token.objects.create(user=self.a.children[0])

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_parent_sees_only_own_family_rewards(self):
        self._auth(self.a_parent_token)
        response = self.client.get("/api/rewards/")
        self.assertEqual(response.status_code, 200)
        ids = {r["id"] for r in response.json()["results"]}
        self.assertEqual(ids, {self.a_reward.id})

    def test_child_sees_only_own_family_active_rewards(self):
        self._auth(self.a_child_token)
        response = self.client.get("/api/rewards/")
        self.assertEqual(response.status_code, 200)
        ids = {r["id"] for r in response.json()["results"]}
        self.assertEqual(ids, {self.a_reward.id})

    def test_parent_cannot_view_other_family_reward(self):
        self._auth(self.a_parent_token)
        response = self.client.get(f"/api/rewards/{self.b_reward.id}/")
        self.assertEqual(response.status_code, 404)

    def test_create_inherits_family_from_caller(self):
        self._auth(self.a_parent_token)
        response = self.client.post(
            "/api/rewards/",
            {
                "name": "Pizza Friday",
                "cost_coins": 50,
                "rarity": "common",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        new_reward = Reward.objects.get(name="Pizza Friday")
        self.assertEqual(new_reward.family_id, self.a.family.id)

    def test_per_family_unique_name(self):
        # Both families having a "Movie Night" reward is allowed
        # (constraint is unique_together=(family, name)).
        self.assertEqual(
            Reward.objects.filter(name="Movie Night").count(),
            2,
        )


class CoinAdjustCrossFamilyTests(APITestCase):
    def setUp(self):
        self.a = make_family(
            "Family A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "Family B",
            children=[{"username": "bc"}],
        )
        self.a_parent_token = Token.objects.create(user=self.a.parents[0])

    def test_parent_cannot_adjust_other_family_child_coins(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.a_parent_token.key}")
        response = self.client.post(
            "/api/coins/adjust/",
            {
                "user_id": self.b.children[0].id,
                "amount": 50,
                "description": "hax",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
