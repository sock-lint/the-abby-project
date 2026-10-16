"""Synthetic Forge Coin quotes produced by the real authenticated endpoints."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.printing.models import PrintBudget, PrintBudgetLedger, PrintRequest
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared_fixtures


FIXED_NOW = datetime(2026, 10, 15, 19, tzinfo=timezone.utc)


@override_settings(
    ALLOWED_HOSTS=["testserver"], TIME_ZONE="America/Phoenix", USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "printing-api-contract-fixtures",
    }},
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class PrintingApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        # Model pages are outside this contract. The synthetic pending request
        # below needs no scraper, printer connection or production resource.
        network = patch("apps.printing.metadata.safe_get", side_effect=AssertionError("No model fetches in Coin contracts."))
        self.model_fetch = network.start()
        self.addCleanup(network.stop)
        household = make_family(
            "Printing Fixture Family", family_id=41,
            parents=[{"id": 6, "username": "printing-fixture-parent", "display_name": "Fixture Parent"}],
            children=[
                {"id": 7, "username": "printing-fixture-child", "display_name": "Fixture Child"},
                {"id": 8, "username": "printing-fixture-sibling"},
            ],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.outsider = make_family(
            "Other Printing Fixture Family", family_id=42,
            parents=[{"id": 99, "username": "printing-fixture-other-parent"}],
        ).parents[0]
        self.tokens = {
            user.pk: Token.objects.create(user=user, key=character * 40)
            for user, character in (
                (self.parent, "a"), (self.child, "b"),
                (self.sibling, "c"), (self.outsider, "d"),
            )
        }
        self.budget = PrintBudget.objects.create(id=21, user=self.child)
        self.print_request = PrintRequest.objects.create(
            id=31, user=self.child, title="Synthetic pumpkin teeth",
            source_kind=PrintRequest.SourceKind.MAKERWORLD,
            source_url="https://makerworld.com/en/models/1-synthetic-teeth",
            color="white", reason="To decorate our paper pumpkin",
            needed_by="2026-10-30",
        )
        CoinLedger.objects.create(
            id=51, user=self.child, amount=80, reason=CoinLedger.Reason.ADJUSTMENT,
            description="Synthetic starting Coins", created_by=self.parent,
        )

    def authenticate(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.tokens[user.pk].key}")

    def quote(self):
        self.authenticate(self.parent)
        self.assert_response_fixture(self.client.patch(
            "/api/print-budgets/21/", {
                "grams_per_month": "500.00", "minutes_per_month": 600,
                "minutes_per_coin": 1,
            }, format="json",
        ), "printing-budget-configured.json")
        quote = self.assert_response_fixture(self.client.post(
            "/api/print-requests/31/approve/", {
                "estimated_grams": "12.50", "estimated_minutes": 61,
                "notes": "Estimate checked in the slicer",
            }, format="json",
        ), "printing-request-quoted.json")
        self.assertEqual(quote["status"], "quoted")
        self.assertEqual(quote["coin_cost"], 61)
        self.assertEqual(quote["minutes_per_coin_snapshot"], 1)
        self.assertEqual(quote["coins_paid"], 0)
        self.assertEqual(quote["coins_refunded"], 0)
        self.assertEqual(CoinService.get_balance(self.child), 80)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
        return quote

    def test_frozen_quote_exchange_and_cancellation_have_exactly_once_coin_effects(self):
        quote = self.quote()
        # A later parent rate change must not change an already offered price.
        changed = self.client.patch(
            "/api/print-budgets/21/", {"minutes_per_coin": 2}, format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.authenticate(self.child)
        listed = self.assert_response_fixture(
            self.client.get("/api/print-requests/"), "printing-requests-quoted.json",
        )
        self.assertEqual(listed["results"], [quote])
        self.assertEqual(CoinService.get_balance(self.child), 80)

        paid = self.assert_response_fixture(self.client.post(
            "/api/print-requests/31/exchange/", {}, format="json",
        ), "printing-exchange-paid.json")
        self.assertEqual(paid["status"], "approved")
        self.assertEqual(paid["coin_cost"], 61)
        self.assertEqual(paid["minutes_per_coin_snapshot"], 1)
        self.assertEqual(paid["coins_paid"], 61)
        self.assertEqual(paid["coins_refunded"], 0)
        self.assertEqual(CoinService.get_balance(self.child), 19)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=-61).count(), 1)
        repeated = self.client.post("/api/print-requests/31/exchange/", {}, format="json")
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(repeated.json(), paid)
        self.assertEqual(CoinService.get_balance(self.child), 19)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 2)

        refunded = self.assert_response_fixture(self.client.post(
            "/api/print-requests/31/cancel/", {}, format="json",
        ), "printing-cancel-refunded.json")
        self.assertEqual(refunded["status"], "cancelled")
        self.assertEqual(refunded["coin_cost"], 61)
        self.assertEqual(refunded["coins_paid"], 61)
        self.assertEqual(refunded["coins_refunded"], 61)
        self.assertEqual(CoinService.get_balance(self.child), 80)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=61, reason=CoinLedger.Reason.REFUND).count(), 1)
        ledger_before = list(CoinLedger.objects.filter(user=self.child).values())
        self.client.post("/api/print-requests/31/cancel/", {}, format="json")
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values()), ledger_before)
        self.assertFalse(PrintBudgetLedger.objects.exists())
        self.model_fetch.assert_not_called()

    def test_exchange_rejections_preserve_the_quote_and_both_families_coins(self):
        self.quote()
        self.authenticate(self.child)
        self.assert_response_fixture(self.client.post(
            "/api/print-requests/31/exchange/", {"coin_cost": 1, "user_id": self.sibling.pk},
            format="json",
        ), "printing-exchange-invalid.json", status=400)
        for user in (self.sibling, self.outsider):
            self.authenticate(user)
            self.assert_response_fixture(self.client.post(
                "/api/print-requests/31/exchange/", {}, format="json",
            ), "printing-request-not-owned.json", status=404)
        self.print_request.refresh_from_db()
        self.assertEqual(self.print_request.status, "quoted")
        self.assertEqual(self.print_request.coins_paid, 0)
        self.assertEqual(CoinService.get_balance(self.child), 80)
        self.assertEqual(CoinService.get_balance(self.sibling), 0)
        self.assertEqual(CoinService.get_balance(self.outsider), 0)
        self.assertEqual(CoinLedger.objects.count(), 1)
        self.model_fetch.assert_not_called()
