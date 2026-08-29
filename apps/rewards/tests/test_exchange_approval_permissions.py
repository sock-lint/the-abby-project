"""A child must not be able to approve their own money->coins exchange.

Regression for a privilege escalation with real money behind it.
``ApprovalActionMixin.approve`` carries ``permission_classes=[IsParent]`` on
its ``@action`` decorator, but DRF only applies decorator kwargs through a
**router**'s ``initkwargs``. ``ExchangeRequestViewSet`` is wired by hand in
apps/rewards/urls.py (``as_view({"post": "approve"})``), so the decorator was
silently inert and the endpoint fell back to the ``IsAuthenticated`` default.

``POST /api/coins/exchange/<pk>/approve/`` returned **200** for the child who
opened the request: ``ExchangeService.approve`` debited PaymentLedger, credited
CoinLedger, and stamped ``decided_by`` as the child themselves.

The gate now lives in ``ApprovalActionMixin.get_permissions`` so it does not
depend on how the URL was wired; these assert the endpoint behaviour.
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from config.tests.factories import make_family

from apps.payments.models import PaymentLedger
from apps.rewards.models import CoinLedger, ExchangeRequest
from apps.rewards.services import ExchangeService


class ChildCannotApproveOwnExchangeTests(APITestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        PaymentLedger.objects.create(
            user=self.child, amount=Decimal("20.00"),
            entry_type=PaymentLedger.EntryType.ADJUSTMENT, description="seed",
        )
        self.request_row = ExchangeRequest.objects.create(
            user=self.child, dollar_amount=Decimal("5.00"), coin_amount=50,
            exchange_rate=10, status=ExchangeRequest.Status.PENDING,
        )

    def _url(self, verb):
        return f"/api/coins/exchange/{self.request_row.id}/{verb}/"

    def assertNothingMoved(self):
        self.request_row.refresh_from_db()
        self.assertEqual(self.request_row.status, ExchangeRequest.Status.PENDING)
        self.assertFalse(
            CoinLedger.objects.filter(user=self.child).exists(),
            "a refused approval must not have credited coins",
        )
        self.assertFalse(
            PaymentLedger.objects.filter(
                user=self.child,
                entry_type=PaymentLedger.EntryType.COIN_EXCHANGE,
            ).exists(),
            "a refused approval must not have debited money",
        )

    def test_a_child_cannot_approve_her_own_exchange(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(self._url("approve"), {}, format="json")
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertNothingMoved()

    def test_a_child_cannot_reject_her_own_exchange(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(self._url("reject"), {}, format="json")
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertNothingMoved()

    def test_a_child_can_still_list_her_own_exchanges(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/coins/exchange/list/")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_a_parent_can_still_approve(self):
        # The fix must not have broken the legitimate path.
        self.client.force_authenticate(self.parent)
        resp = self.client.post(self._url("approve"), {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.request_row.refresh_from_db()
        self.assertEqual(self.request_row.status, ExchangeRequest.Status.APPROVED)
        self.assertEqual(self.request_row.decided_by, self.parent)
        self.assertTrue(CoinLedger.objects.filter(user=self.child).exists())

    def test_a_parent_can_still_reject(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(self._url("reject"), {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.request_row.refresh_from_db()
        self.assertEqual(self.request_row.status, ExchangeRequest.Status.DENIED)


class ExchangeServiceRefusesNonParentTests(APITestCase):
    """Defence in depth: the service refuses even when the viewset is bypassed.

    ``ExchangeService.approve`` treats ``parent`` as attribution only, so the
    permission class was the single thing standing between a child and the
    ledger write. These call the service directly — no HTTP layer — so they
    still fail if someone adds a new caller that forgets to check the role.
    """

    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        PaymentLedger.objects.create(
            user=self.child, amount=Decimal("20.00"),
            entry_type=PaymentLedger.EntryType.ADJUSTMENT, description="seed",
        )
        self.request_row = ExchangeRequest.objects.create(
            user=self.child, dollar_amount=Decimal("5.00"), coin_amount=50,
            exchange_rate=10, status=ExchangeRequest.Status.PENDING,
        )

    def test_approve_refuses_a_child_caller(self):
        with self.assertRaises(PermissionDenied):
            ExchangeService.approve(self.request_row, self.child)
        self.request_row.refresh_from_db()
        self.assertEqual(self.request_row.status, ExchangeRequest.Status.PENDING)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(
            PaymentLedger.objects.filter(
                user=self.child,
                entry_type=PaymentLedger.EntryType.COIN_EXCHANGE,
            ).exists(),
        )

    def test_approve_refuses_a_missing_caller(self):
        with self.assertRaises(PermissionDenied):
            ExchangeService.approve(self.request_row, None)
        self.request_row.refresh_from_db()
        self.assertEqual(self.request_row.status, ExchangeRequest.Status.PENDING)

    def test_approve_still_accepts_a_parent(self):
        result = ExchangeService.approve(self.request_row, self.parent)
        self.assertEqual(result.status, ExchangeRequest.Status.APPROVED)
        self.assertTrue(CoinLedger.objects.filter(user=self.child).exists())
