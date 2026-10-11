"""Raw Greenlight workflow responses shared by React and Unity contract checks.

Only synthetic families and a disposable test database are used. Fixtures are
rendered by the real endpoints, including payout and statement reconciliation.
"""
import json
import os
from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.payments.models import (
    GreenlightBalanceSnapshot, GreenlightStatementTransfer, GreenlightTransfer,
    PaymentLedger,
)
from apps.timecards.models import Timecard
from config.tests.factories import make_family


FIXTURE_DIR = Path(settings.BASE_DIR) / "contracts" / "api" / "fixtures"
FIXED_NOW = datetime(2026, 10, 11, 19, 0, tzinfo=datetime_timezone.utc)
STATEMENT_CSV = (
    "date,amount,description,reference,type\n"
    "2026-10-11,12.50,Weekly project payout,fixture-week-1,transfer\n"
    "2026-10-11,7.50,Approved chore payout,fixture-chore-1,transfer\n"
    "2026-10-11,-3.00,Bookshop purchase,fixture-purchase-1,purchase\n"
)


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "greenlight-api-contract-fixtures",
    }},
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class GreenlightApiResponseFixtureTests(APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Greenlight Fixture Family", family_id=1,
            parents=[{"id": 6, "username": "greenlight-fixture-parent"}],
            children=[{"id": 7, "username": "greenlight-fixture-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.outsider = make_family(
            "Other Greenlight Fixture Family", family_id=2,
            children=[{"id": 99, "username": "greenlight-fixture-outsider"}],
        ).children[0]
        self.approved = Timecard.objects.create(
            id=11, user=self.child, week_start=date(2026, 9, 28),
            week_end=date(2026, 10, 4), status=Timecard.Status.APPROVED,
            total_hours=Decimal("2.50"), hourly_earnings=Decimal("12.50"),
            total_earnings=Decimal("12.50"), decided_by=self.parent,
            decided_at=FIXED_NOW,
        )
        pending = Timecard.objects.create(
            id=12, user=self.child, week_start=date(2026, 10, 5),
            week_end=date(2026, 10, 11), status=Timecard.Status.PENDING,
            total_hours=Decimal("1.00"), hourly_earnings=Decimal("5.00"),
            total_earnings=Decimal("5.00"),
        )
        for ledger_id, amount, entry_type, card in (
            (21, "12.50", PaymentLedger.EntryType.HOURLY, self.approved),
            (22, "5.00", PaymentLedger.EntryType.HOURLY, pending),
            (23, "7.50", PaymentLedger.EntryType.CHORE_REWARD, None),
        ):
            PaymentLedger.objects.create(
                id=ledger_id, user=self.child, amount=Decimal(amount),
                entry_type=entry_type, timecard=card, created_by=self.parent,
                description="Synthetic approved work" if card != pending else "Synthetic pending hours",
            )
        PaymentLedger.objects.create(
            id=24, user=self.outsider, amount=Decimal("999.00"),
            entry_type=PaymentLedger.EntryType.ADJUSTMENT,
            description="Other family must remain out of scope",
        )
        # PostgreSQL sequences persist across TestCase rollbacks. Pin endpoint-
        # created wire identities from the seeded rows, just as SQLite does.
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [
                PaymentLedger, GreenlightBalanceSnapshot, GreenlightTransfer,
                GreenlightStatementTransfer,
            ]):
                cursor.execute(sql)
        token = Token.objects.create(user=self.parent, key="1" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_response_fixture(self, response, name, status=200):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response["Content-Type"], "application/json")
        actual = response.json()
        path = FIXTURE_DIR / name
        if os.environ.get("UPDATE_API_CONTRACT_FIXTURES") == "1":
            self.assertFalse(os.environ.get("CI"), "Fixture regeneration is a local, reviewed operation.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        expected = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            json.dumps(actual, sort_keys=True, indent=2),
            json.dumps(expected, sort_keys=True, indent=2),
            f"API response drifted from {path.name}; review and regenerate deliberately.",
        )
        return actual

    def overview(self):
        return self.client.get("/api/payments/greenlight/overview/", {"user_id": self.child.pk})

    def test_manual_payout_and_statement_reconciliation_preserve_distinct_balances(self):
        missing = self.assert_response_fixture(self.overview(), "greenlight-overview-no-snapshot.json")
        self.assertEqual(missing["owed_balance"], "25.00")
        self.assertEqual(missing["approved_payable"], "20.00")
        self.assertEqual(missing["pending_hourly"], "5.00")
        self.assertIsNone(missing["balance_snapshot"])
        snapshot = self.assert_response_fixture(self.client.post(
            "/api/payments/greenlight/snapshot/", {
                "user_id": self.child.pk, "amount": "40.25",
                "as_of": "2026-10-11T18:00:00Z", "memo": "Checked in the Greenlight app",
            }, format="json",
        ), "greenlight-balance-snapshot.json", status=201)
        overview = self.assert_response_fixture(self.overview(), "greenlight-overview.json")
        self.assertEqual(overview["balance_snapshot"], snapshot)
        self.assertEqual(overview["owed_balance"], missing["owed_balance"])

        payout = self.assert_response_fixture(self.client.post(
            "/api/payments/greenlight/payout/", {
                "user_id": self.child.pk, "amount": "12.50", "transferred_on": "2026-10-11",
                "reference": "fixture-week-1", "memo": "Transferred after approval",
                "timecard_id": self.approved.pk,
                "idempotency_key": "11111111-1111-4111-8111-111111111111",
            }, format="json",
        ), "greenlight-payout.json", status=201)
        self.assertTrue(payout["created"])
        manual_id = payout["payout"]["id"]
        self.assertEqual(PaymentLedger.objects.get(pk=manual_id).amount, Decimal("-12.50"))
        self.approved.refresh_from_db()
        self.assertEqual(self.approved.status, Timecard.Status.PAID)

        preview = self.assert_response_fixture(self.client.post(
            "/api/payments/greenlight/preview/", {
                "user_id": self.child.pk, "csv_data": STATEMENT_CSV,
            }, format="json",
        ), "greenlight-preview.json")
        first, second, purchase = preview["rows"]
        self.assertTrue(first["eligible"])
        self.assertIn(manual_id, first["match_candidates"])
        self.assertTrue(second["eligible"])
        self.assertFalse(purchase["eligible"])
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 4)
        selections = [
            {"fingerprint": first["fingerprint"], "match_payment_id": manual_id},
            {"fingerprint": second["fingerprint"]},
        ]
        request = {"user_id": self.child.pk, "csv_data": STATEMENT_CSV, "selections": selections}
        reconciled = self.assert_response_fixture(self.client.post(
            "/api/payments/greenlight/reconcile/", request, format="json",
        ), "greenlight-reconcile.json")
        self.assertEqual(reconciled, {"recorded": 1, "matched": 1, "duplicates": 0})
        repeated = self.client.post("/api/payments/greenlight/reconcile/", request, format="json")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json(), {"recorded": 0, "matched": 0, "duplicates": 2})
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 5)

        final = self.assert_response_fixture(self.overview(), "greenlight-overview-reconciled.json")
        self.assertEqual(final["owed_balance"], "5.00")
        self.assertEqual(final["approved_payable"], "0.00")
        self.assertEqual(final["pending_hourly"], "5.00")
        self.assertEqual(final["balance_snapshot"], snapshot)
        self.assertEqual(len(final["payouts"]), 2)
        self.assertTrue(all(row["reconciled"] for row in final["payouts"]))
        self.assertEqual(GreenlightStatementTransfer.objects.filter(user=self.child).count(), 2)
        self.assertEqual(self.client.get(
            "/api/payments/greenlight/overview/", {"user_id": self.outsider.pk},
        ).status_code, 404)
