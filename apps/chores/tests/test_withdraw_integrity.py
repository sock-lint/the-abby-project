"""A withdrawal may delete pending work, but never an approved reward receipt."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreNotAvailableError, ChoreService
from apps.chores.views import ChoreCompletionViewSet
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from config.tests.factories import make_family


class ChoreWithdrawalIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "parent"}], children=[{"username": "child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.chore = Chore.objects.create(
            family=family.family, created_by=self.parent, title="Clean counter",
            reward_amount=Decimal("5"), coin_reward=2, xp_reward=0,
        )
        self.completion = ChoreService.submit_completion(self.child, self.chore)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def test_approval_between_withdraw_lookup_and_lock_cannot_be_deleted(self):
        original_get_object = ChoreCompletionViewSet.get_object

        def approve_after_read(view):
            stale = original_get_object(view)
            ChoreService.approve_completion(ChoreCompletion.objects.get(pk=stale.pk), self.parent)
            return stale

        with patch.object(ChoreCompletionViewSet, "get_object", approve_after_read):
            response = self.client.post(f"/api/chore-completions/{self.completion.pk}/withdraw/")
        self.assertEqual(response.status_code, 400)
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, "approved")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("5"))
        self.assertEqual(PaymentLedger.objects.filter(user=self.child, entry_type="chore_reward").count(), 1)
        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.child, self.chore)

    def test_rejection_after_stale_lookup_preserves_decision_record(self):
        stale = ChoreCompletion.objects.get(pk=self.completion.pk)
        ChoreService.reject_completion(self.completion, self.parent)
        with patch.object(ChoreCompletionViewSet, "get_object", return_value=stale):
            response = self.client.post(f"/api/chore-completions/{self.completion.pk}/withdraw/")
        self.assertEqual(response.status_code, 400)
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, "rejected")
        self.assertEqual(self.completion.decided_by, self.parent)

    def test_deleted_after_lookup_returns_not_found(self):
        stale = ChoreCompletion.objects.get(pk=self.completion.pk)
        pk = self.completion.pk
        self.completion.delete()
        with patch.object(ChoreCompletionViewSet, "get_object", return_value=stale):
            response = self.client.post(f"/api/chore-completions/{pk}/withdraw/")
        self.assertEqual(response.status_code, 404)

    def test_withdrawal_winning_after_approval_lookup_returns_not_found(self):
        original_get_object = ChoreCompletionViewSet.get_object

        def withdraw_after_read(view):
            stale = original_get_object(view)
            ChoreCompletion.objects.filter(pk=stale.pk).delete()
            return stale

        self.client.force_authenticate(self.parent)
        with patch.object(ChoreCompletionViewSet, "get_object", withdraw_after_read):
            response = self.client.post(f"/api/chore-completions/{self.completion.pk}/approve/")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(PaymentLedger.objects.filter(user=self.child, entry_type="chore_reward").exists())
