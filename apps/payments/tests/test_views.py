"""Tests for payments viewsets and custom endpoints."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.other_child = User.objects.create_user(username="c2", password="pw", role="child")
        self.client = APIClient()


class PaymentLedgerViewSetTests(_Fixture):
    def test_child_sees_only_own_ledger(self):
        PaymentService.record_entry(self.child, Decimal("5"), PaymentLedger.EntryType.HOURLY)
        PaymentService.record_entry(self.other_child, Decimal("7"), PaymentLedger.EntryType.HOURLY)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/payments/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 1)

    def test_parent_sees_all_ledger(self):
        PaymentService.record_entry(self.child, Decimal("5"), PaymentLedger.EntryType.HOURLY)
        PaymentService.record_entry(self.other_child, Decimal("7"), PaymentLedger.EntryType.HOURLY)
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/payments/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 2)

    def test_unauthenticated_rejected(self):
        resp = self.client.get("/api/payments/")
        self.assertEqual(resp.status_code, 401)


class PaymentLedgerFilterTests(_Fixture):
    def setUp(self):
        super().setUp()
        PaymentService.record_entry(self.child, Decimal("5"), PaymentLedger.EntryType.HOURLY)
        PaymentService.record_entry(self.child, Decimal("3"), PaymentLedger.EntryType.CHORE_REWARD)
        PaymentService.record_entry(self.other_child, Decimal("7"), PaymentLedger.EntryType.HOURLY)

    def test_entry_type_filter_narrows_results(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/payments/?entry_type=chore_reward")
        items = resp.json().get("results", resp.json())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["entry_type"], "chore_reward")

    def test_entry_type_supports_multiple_csv(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/payments/?entry_type=hourly,chore_reward")
        items = resp.json().get("results", resp.json())
        self.assertEqual(len(items), 3)

    def test_unknown_entry_type_silently_ignored(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/payments/?entry_type=fake_type")
        # No matches — but the response is still 200 (not 400) so the
        # filter UI doesn't break on a typo.
        items = resp.json().get("results", resp.json())
        self.assertEqual(len(items), 3)

    def test_user_id_filter_narrows_to_one_child(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/payments/?user_id={self.child.id}")
        items = resp.json().get("results", resp.json())
        self.assertEqual(len(items), 2)
        self.assertTrue(all(it["user"] == self.child.id for it in items))

    def test_child_user_id_param_is_ignored(self):
        """A child passing user_id=<sibling> sees only their own rows.

        The user_id narrowing only applies for parent callers; for
        children the role filter has already scoped the queryset to
        self, and the param is silently ignored. Cross-family widening
        was never on the table.
        """
        self.client.force_authenticate(self.child)
        resp = self.client.get(f"/api/payments/?user_id={self.other_child.id}")
        items = resp.json().get("results", resp.json())
        self.assertEqual(len(items), 2)
        self.assertTrue(all(it["user"] == self.child.id for it in items))

    def test_csv_export_returns_streamable_csv_for_parent(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/payments/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("payment-ledger.csv", resp["Content-Disposition"])
        body = resp.content.decode("utf-8").splitlines()
        # Header + 3 data rows.
        self.assertEqual(len(body), 4)
        self.assertEqual(
            body[0],
            "created_at,user,entry_type,amount,description,id",
        )

    def test_csv_export_honors_filters(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/payments/export/?entry_type=hourly")
        body = resp.content.decode("utf-8").splitlines()
        # Header + 2 hourly rows.
        self.assertEqual(len(body), 3)

    def test_csv_export_child_forbidden(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/payments/export/")
        self.assertEqual(resp.status_code, 403)


class BalanceViewTests(_Fixture):
    def test_balance_for_self(self):
        PaymentService.record_entry(self.child, Decimal("10"), PaymentLedger.EntryType.HOURLY)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/balance/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["balance"], 10.0)

    def test_parent_can_query_child_balance(self):
        PaymentService.record_entry(self.child, Decimal("4"), PaymentLedger.EntryType.HOURLY)
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/balance/?user_id={self.child.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["balance"], 4.0)


class PayoutViewTests(_Fixture):
    def test_parent_records_payout(self):
        # Note: the product's PaymentService.record_payout does abs(amount) without
        # coercing strings, so JSON clients must send numeric. Mirrors production usage.
        PaymentService.record_entry(self.child, Decimal("20"), PaymentLedger.EntryType.HOURLY)
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/payout/", {
            "user_id": self.child.id, "amount": 10,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("10"))

    def test_child_cannot_record_payout(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/payments/payout/", {
            "user_id": self.child.id, "amount": "5",
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_missing_amount_400(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/payout/", {
            "user_id": self.child.id,
        }, format="json")
        self.assertEqual(resp.status_code, 400)


class PaymentAdjustmentViewTests(_Fixture):
    def test_parent_adds_positive_adjustment(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": self.child.id, "amount": "2.50",
            "description": "Found cash on floor",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("2.50"))

    def test_parent_adds_negative_adjustment(self):
        PaymentService.record_entry(self.child, Decimal("10"), PaymentLedger.EntryType.HOURLY)
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": self.child.id, "amount": "-3.00",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("7"))

    def test_zero_rejected(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": self.child.id, "amount": "0",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_invalid_amount_rejected(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": self.child.id, "amount": "abc",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_child_forbidden(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": self.child.id, "amount": "5",
        }, format="json")
        self.assertEqual(resp.status_code, 403)


class PaymentSummaryByDayTests(_Fixture):
    URL = "/api/payments/summary-by-day/"

    def _entry(self, user, amount, days_ago=0):
        from datetime import timedelta
        from django.utils import timezone

        row = PaymentService.record_entry(
            user, Decimal(amount), PaymentLedger.EntryType.HOURLY,
        )
        if days_ago:
            PaymentLedger.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago),
            )
        return row

    def test_series_is_zero_filled_and_ends_today(self):
        from django.utils import timezone

        self._entry(self.child, "5")
        self._entry(self.child, "3", days_ago=2)
        self.client.force_authenticate(self.child)

        data = self.client.get(self.URL).json()

        self.assertEqual(data["days"], 30)
        self.assertEqual(len(data["series"]), 30)
        self.assertEqual(
            data["series"][-1],
            {"date": timezone.localdate().isoformat(), "earned": 5.0},
        )
        self.assertEqual(data["series"][-3]["earned"], 3.0)
        # Every other day present at zero.
        zeros = [p for p in data["series"] if p["earned"] == 0.0]
        self.assertEqual(len(zeros), 28)

    def test_spends_are_excluded(self):
        self._entry(self.child, "10")
        self._entry(self.child, "-4")
        self.client.force_authenticate(self.child)

        data = self.client.get(self.URL).json()
        self.assertEqual(data["series"][-1]["earned"], 10.0)

    def test_days_param_clamped(self):
        self.client.force_authenticate(self.child)
        self.assertEqual(len(self.client.get(self.URL + "?days=7").json()["series"]), 7)
        self.assertEqual(self.client.get(self.URL + "?days=500").json()["days"], 90)
        self.assertEqual(self.client.get(self.URL + "?days=abc").json()["days"], 30)

    def test_child_series_excludes_siblings(self):
        self._entry(self.other_child, "9")
        self.client.force_authenticate(self.child)

        data = self.client.get(self.URL).json()
        self.assertEqual(data["series"][-1]["earned"], 0.0)

    def test_parent_user_id_narrows(self):
        self._entry(self.child, "5")
        self._entry(self.other_child, "9")
        self.client.force_authenticate(self.parent)

        data = self.client.get(f"{self.URL}?user_id={self.child.pk}").json()
        self.assertEqual(data["series"][-1]["earned"], 5.0)
