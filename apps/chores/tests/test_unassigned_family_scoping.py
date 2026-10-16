"""Unassigned duties are shared within one family, never across households."""

from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.activity.models import ActivityEvent
from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreNotAvailableError, ChoreService
from apps.notifications.models import Notification
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class UnassignedChoreFamilyScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alpha = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_child"}, {"username": "alpha_sibling"}],
        )
        cls.bravo = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_child"}],
        )
        cls.child = cls.alpha.children[0]
        cls.assigned = cls.make_chore("My daily duty", assigned_to=cls.child)
        cls.unassigned = cls.make_chore("Shared Alpha duty")
        cls.sibling_duty = cls.make_chore(
            "Sibling duty", assigned_to=cls.alpha.children[1],
        )
        cls.foreign = cls.make_chore("Private Bravo duty", household=cls.bravo)

    @classmethod
    def make_chore(cls, title, *, household=None, **kwargs):
        household = household or cls.alpha
        return Chore.objects.create(
            title=title,
            family=household.family,
            created_by=household.parents[0],
            **kwargs,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def assert_child_duties(self, rows):
        self.assertEqual(
            {row["id"] for row in rows},
            {self.assigned.pk, self.unassigned.pk},
        )

    def test_service_scopes_unassigned_and_assigned_chores_to_family(self):
        # Even an inconsistent assignment must not override the chore's family.
        self.make_chore(
            "Foreign duty assigned to Alpha", household=self.bravo,
            assigned_to=self.child,
        )
        available = ChoreService.get_available_chores(self.child)

        self.assertEqual(
            {chore.pk for chore in available},
            {self.assigned.pk, self.unassigned.pk},
        )

    def test_child_rest_list_excludes_foreign_unassigned_chores(self):
        response = self.client.get("/api/chores/")

        self.assertEqual(response.status_code, 200)
        self.assert_child_duties(response.json())
        self.assertNotContains(response, self.foreign.title)

    def test_child_dashboard_excludes_foreign_unassigned_chores(self):
        response = self.client.get("/api/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assert_child_duties(response.json()["chores_today"])
        self.assertNotContains(response, self.foreign.title)

    def test_child_mcp_list_excludes_foreign_unassigned_chores(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.schemas import ListChoresIn
        from apps.mcp_server.tools.chores import list_chores

        with override_user(self.child):
            result = list_chores(ListChoresIn())

        self.assert_child_duties(result["chores"])

    def test_foreign_unassigned_chore_cannot_be_submitted_directly(self):
        notification_count = Notification.objects.count()
        activity_count = ActivityEvent.objects.count()

        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.child, self.foreign)

        self.assertFalse(ChoreCompletion.objects.exists())
        self.assertEqual(Notification.objects.count(), notification_count)
        self.assertEqual(ActivityEvent.objects.count(), activity_count)

    def test_foreign_unassigned_chore_complete_endpoint_returns_not_found(self):
        response = self.client.post(f"/api/chores/{self.foreign.pk}/complete/")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ChoreCompletion.objects.exists())

    def test_own_unassigned_chore_still_submits_with_completion_status(self):
        response = self.client.post(f"/api/chores/{self.unassigned.pk}/complete/")

        self.assertEqual(response.status_code, 201)
        completion = ChoreCompletion.objects.get(pk=response.json()["id"])
        self.assertEqual(completion.user, self.child)
        self.assertEqual(completion.status, ChoreCompletion.Status.PENDING)
        available = {
            chore.pk: chore for chore in ChoreService.get_available_chores(self.child)
        }
        self.assertTrue(available[self.unassigned.pk].is_done_today)
        self.assertEqual(
            available[self.unassigned.pk].today_completion_status,
            ChoreCompletion.Status.PENDING,
        )
        self.assertEqual(
            available[self.unassigned.pk].today_completion_id, completion.pk,
        )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 10, 16))
    def test_foreign_unfinished_duty_does_not_block_own_perfect_day(self, _date):
        from apps.rpg.tasks import evaluate_perfect_day_task

        today = timezone.localdate()
        profile = self.child.character_profile
        profile.last_active_date = today
        profile.save(update_fields=["last_active_date"])
        for chore in (self.assigned, self.unassigned):
            ChoreCompletion.objects.create(
                chore=chore,
                user=self.child,
                completed_date=today,
                status=ChoreCompletion.Status.APPROVED,
                reward_amount_snapshot=chore.reward_amount,
                coin_reward_snapshot=chore.coin_reward,
            )

        evaluate_perfect_day_task()

        profile.refresh_from_db()
        self.assertEqual(profile.perfect_days_count, 1)
        self.assertEqual(
            list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)),
            [15],
        )
        self.assertFalse(CoinLedger.objects.filter(user__family=self.bravo.family).exists())
