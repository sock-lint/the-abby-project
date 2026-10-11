"""Complete, family-scoped approval queues stay separate from paginated history."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.families.models import Family
from apps.rewards.models import ExchangeRequest, Reward, RewardRedemption


class PendingApprovalFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family = Family.objects.create(name="Queue family", slug="queue-family")
        cls.other_family = Family.objects.create(name="Other family", slug="other-queue-family")
        cls.parent = User.objects.create_user(username="queue-parent", role="parent", family=cls.family)
        cls.child = User.objects.create_user(username="queue-child", role="child", family=cls.family)
        cls.sibling = User.objects.create_user(username="queue-sibling", role="child", family=cls.family)
        cls.outsider = User.objects.create_user(username="queue-outsider", role="child", family=cls.other_family)
        cls.reward = Reward.objects.create(name="Queue prize", family=cls.family, cost_coins=30, stock=0)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def create_requests(self, model, count, *, user=None, status="pending"):
        fields = {"user": user or self.child, "status": status}
        if model is RewardRedemption:
            fields.update(reward=self.reward, coin_cost_snapshot=30)
        else:
            fields.update(dollar_amount=Decimal("3.00"), coin_amount=30, exchange_rate=10)
        return model.objects.bulk_create([model(**fields) for _ in range(count)])

    def endpoints(self):
        return (
            (RewardRedemption, "/api/redemptions/", "fulfilled"),
            (ExchangeRequest, "/api/coins/exchange/list/", "approved"),
        )

    def test_pending_filter_finds_older_request_beyond_first_history_page(self):
        for model, url, decided_status in self.endpoints():
            with self.subTest(model=model.__name__):
                old_pending = self.create_requests(model, 1)[0]
                self.create_requests(model, 20, status=decided_status)
                history = self.client.get(url).json()
                self.assertEqual(history["count"], 21)
                self.assertEqual(len(history["results"]), 20)
                self.assertNotIn(old_pending.pk, [row["id"] for row in history["results"]])
                pending = self.client.get(url, {"status": "pending"}).json()
                self.assertEqual(pending["count"], 1)
                self.assertEqual(pending["results"][0]["id"], old_pending.pk)

    def test_pending_queue_paginates_more_than_twenty_actions_without_history_or_other_family(self):
        for model, url, decided_status in self.endpoints():
            with self.subTest(model=model.__name__):
                expected = self.create_requests(model, 25)
                self.create_requests(model, 20, status=decided_status)
                self.create_requests(model, 2, user=self.outsider)
                first = self.client.get(url, {"status": "pending"}).json()
                self.assertEqual(first["count"], 25)
                self.assertEqual(len(first["results"]), 20)
                self.assertIn("status=pending", first["next"])
                second = self.client.get(first["next"]).json()
                self.assertEqual(len(second["results"]), 5)
                self.assertIsNone(second["next"])
                rows = first["results"] + second["results"]
                self.assertEqual({row["id"] for row in rows}, {row.pk for row in expected})
                self.assertTrue(all(row["status"] == "pending" for row in rows))

    def test_role_and_family_scope_apply_to_status_filter(self):
        for model, url, decided_status in self.endpoints():
            with self.subTest(model=model.__name__):
                self.client.force_authenticate(self.parent)
                own = self.create_requests(model, 1)[0]
                sibling = self.create_requests(model, 1, user=self.sibling)[0]
                self.create_requests(model, 1, user=self.outsider)
                decided = self.create_requests(model, 1, status=decided_status)[0]
                parent_rows = self.client.get(url, {"status": "pending"}).json()["results"]
                self.assertEqual({row["id"] for row in parent_rows}, {own.pk, sibling.pk})
                selected = self.client.get(url, {"status": decided_status}).json()["results"]
                self.assertEqual([row["id"] for row in selected], [decided.pk])
                self.client.force_authenticate(self.child)
                child_rows = self.client.get(url, {"status": "pending"}).json()["results"]
                self.assertEqual([row["id"] for row in child_rows], [own.pk])
                invalid = self.client.get(url, {"status": "unknown"}).json()
                self.assertEqual(invalid["count"], 0)

    def test_parent_can_clear_finite_stock_with_empty_multipart_field(self):
        for stock in (0, 7):
            with self.subTest(stock=stock):
                self.reward.stock = stock
                self.reward.save(update_fields=["stock"])
                response = self.client.patch(f"/api/rewards/{self.reward.pk}/", {"stock": ""}, format="multipart")
                self.assertEqual(response.status_code, 200, response.data)
                self.reward.refresh_from_db()
                self.assertIsNone(self.reward.stock)
