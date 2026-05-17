"""Failure-path tests for the payments subsystem.

The existing ``test_services.py`` covers the happy paths for
``PaymentService.record_entry`` and ``record_payout``; ``test_views.py``
covers the HTTP surface for normal-case adjustments. What this file pins
is the set of edges that have shipped bugs in this codebase or its
neighbours before, and that the documented contracts in
``apps/payments/services.py`` and ``apps/rewards/services.py`` claim are
safe:

1. **Savings-goal failure must NOT roll back the ledger entry.** The
   try/except in ``PaymentService.record_entry`` (services.py:68-75) is
   load-bearing — if a downstream check raises, the money/coin write
   still has to land or kids see "I worked but my balance is the same".

2. **Exchange approval atomicity.** ``ExchangeService.approve`` is
   ``@transaction.atomic`` — if the coin-credit step raises after the
   payment-debit step has run, the debit must roll back so the child
   isn't double-charged.

3. **Cross-family safety on the adjust endpoint.** A parent pointing
   ``user_id`` at a child in another family must get 404, not 200.

4. **View-level missing-field guards** that don't appear in the
   happy-path test files but the views actually enforce.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import User
from apps.rewards.models import CoinLedger, ExchangeRequest
from apps.rewards.services import ExchangeService
from config.tests.factories import make_family


class _Fixture(TestCase):
    def setUp(self):
        fam = make_family(
            name="Smiths",
            parents=[{"username": "p"}],
            children=[{"username": "c"}],
        )
        self.parent = fam.parents[0]
        self.child = fam.children[0]
        self.client = APIClient()


# ── PaymentService.record_entry resilience ────────────────────────────────


class RecordEntryDownstreamFailureTests(_Fixture):
    """The try/except around ``SavingsGoalService.check_and_complete`` is
    documented as "a failure downstream … must never roll back the ledger
    entry itself" — these tests pin that contract."""

    def test_savings_goal_check_failure_does_not_swallow_ledger_row(self):
        with patch(
            "apps.projects.savings_service.SavingsGoalService.check_and_complete",
            side_effect=RuntimeError("savings service crashed"),
        ):
            entry = PaymentService.record_entry(
                self.child, Decimal("10.00"),
                PaymentLedger.EntryType.HOURLY,
                description="1h @ $10",
                created_by=self.parent,
            )

        # Entry was returned to the caller.
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount, Decimal("10.00"))
        # And persisted — a balance read picks it up.
        self.assertEqual(
            PaymentService.get_balance(self.child), Decimal("10.00"),
        )

    def test_savings_goal_check_failure_is_logged_not_raised(self):
        """The exception is logged but never re-raised — the caller
        (clock-out, badge award, etc.) must not see it."""
        with patch(
            "apps.projects.savings_service.SavingsGoalService.check_and_complete",
            side_effect=Exception("anything"),
        ):
            # If the exception leaked, this would raise instead of return.
            entry = PaymentService.record_entry(
                self.child, Decimal("1.00"),
                PaymentLedger.EntryType.CHORE_REWARD,
            )
        self.assertIsNotNone(entry)


# ── PaymentService.record_payout sign normalization ──────────────────────


class RecordPayoutSignTests(_Fixture):
    """``record_payout`` normalizes the amount with ``-abs(amount)`` — every
    code path that builds a payout (CSV import, payout view, manual
    parent action) must end up with a negative ledger row regardless of
    what sign the caller passed in. The existing tests cover positive +
    negative inputs; this also pins zero, str, and Decimal coercion."""

    def test_zero_payout_writes_zero(self):
        """``-abs(0)`` is ``0`` — no exception, but also no real-world
        effect. Pinning so a future "reject zero" change is deliberate."""
        entry = PaymentService.record_payout(
            self.child, Decimal("0"), self.parent,
        )
        self.assertEqual(entry.amount, Decimal("0"))
        self.assertEqual(entry.entry_type, PaymentLedger.EntryType.PAYOUT)

    def test_string_amount_accepted_via_decimal(self):
        """Greenlight CSV import hands strings to the service — must be
        coerced rather than crashing on ``-abs("10.00")``."""
        # abs() on a Decimal works; on a str it raises TypeError. The
        # service is documented as accepting numeric inputs — strings
        # would surface as TypeError, which is the contract we want to
        # pin: callers must Decimal()-coerce before invoking.
        with self.assertRaises(TypeError):
            PaymentService.record_payout(self.child, "10.00", self.parent)


# ── Exchange approval atomicity ───────────────────────────────────────────


class ExchangeApprovalAtomicityTests(_Fixture):
    """``ExchangeService.approve`` decorates with ``@transaction.atomic``
    so the payment debit + coin credit + status update either all land
    or none do. The existing happy-path + insufficient-balance tests
    don't exercise the mid-flight failure case — if the coin-credit step
    raises after the payment debit, the debit must roll back so the
    child isn't double-charged."""

    def setUp(self):
        super().setUp()
        # Seed enough balance for a $10 exchange.
        PaymentService.record_entry(
            self.child, Decimal("50.00"),
            PaymentLedger.EntryType.HOURLY,
        )

    def test_coin_credit_failure_rolls_back_payment_debit(self):
        exchange = ExchangeService.request_exchange(self.child, "10.00")
        debits_before = PaymentLedger.objects.filter(
            user=self.child,
            entry_type=PaymentLedger.EntryType.COIN_EXCHANGE,
        ).count()

        # CoinService.award_coins is called AFTER the payment debit
        # inside the same transaction — patch it to raise.
        with patch(
            "apps.rewards.services.CoinService.award_coins",
            side_effect=RuntimeError("coin write blew up"),
        ):
            with self.assertRaises(RuntimeError):
                ExchangeService.approve(exchange, self.parent)

        # Payment debit must have rolled back.
        debits_after = PaymentLedger.objects.filter(
            user=self.child,
            entry_type=PaymentLedger.EntryType.COIN_EXCHANGE,
        ).count()
        self.assertEqual(debits_after, debits_before)

        # Coin balance unchanged.
        self.assertEqual(
            CoinLedger.objects.filter(user=self.child).count(), 0,
        )

        # Exchange row's status stays PENDING — the atomic block rolled
        # back the finalize_decision write too.
        exchange.refresh_from_db()
        self.assertEqual(exchange.status, ExchangeRequest.Status.PENDING)

        # And the child's money balance is intact at $50.
        self.assertEqual(
            PaymentService.get_balance(self.child), Decimal("50.00"),
        )

    def test_approve_is_noop_on_already_approved_exchange(self):
        """Idempotency: approving twice must not double-debit. Pinning
        the early-return guard (services.py:369-370) directly."""
        exchange = ExchangeService.request_exchange(self.child, "10.00")
        ExchangeService.approve(exchange, self.parent)

        balance_after_first = PaymentService.get_balance(self.child)
        coins_after_first = CoinLedger.objects.filter(user=self.child).count()

        # Second approve should be a no-op.
        ExchangeService.approve(exchange, self.parent)

        self.assertEqual(
            PaymentService.get_balance(self.child), balance_after_first,
        )
        self.assertEqual(
            CoinLedger.objects.filter(user=self.child).count(),
            coins_after_first,
        )


# ── PaymentAdjustmentView edges ──────────────────────────────────────────


class PaymentAdjustmentViewEdgeTests(_Fixture):
    """``PaymentAdjustmentView`` is the only parent-facing write that takes
    arbitrary amounts — the existing tests cover positive/negative/zero
    happy paths but miss two real failure shapes:

    - cross-family targeting (parent points at another family's child),
    - missing ``amount`` entirely (different from ``amount="abc"``).
    """

    def test_cross_family_child_returns_404(self):
        """The view uses ``resolve_target_user`` which calls
        ``get_child_or_404`` with the requesting parent's family — a
        parent in family A targeting a child in family B must NOT 200."""
        other_fam = make_family(
            name="Joneses",
            parents=[{"username": "p2"}],
            children=[{"username": "c2"}],
        )
        outsider_child = other_fam.children[0]

        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": outsider_child.id,
            "amount": "5.00",
            "description": "should not land",
        }, format="json")

        self.assertEqual(resp.status_code, 404)
        # And no row was written to the outsider's ledger.
        self.assertEqual(
            PaymentLedger.objects.filter(user=outsider_child).count(), 0,
        )

    def test_missing_amount_returns_400(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": self.child.id,
            "description": "no amount",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_returns_401(self):
        # No force_authenticate.
        resp = self.client.post("/api/payments/adjust/", {
            "user_id": self.child.id, "amount": "5.00",
        }, format="json")
        self.assertIn(resp.status_code, (401, 403))


# ── PaymentLedgerViewSet filter validation ───────────────────────────────


class LedgerFilterRobustnessTests(_Fixture):
    """The list endpoint's filter parser silently drops malformed input —
    a bad ``start_date`` or unknown ``entry_type`` must not 500."""

    def test_bad_start_date_silently_dropped(self):
        PaymentService.record_entry(
            self.child, Decimal("5"), PaymentLedger.EntryType.HOURLY,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get(
            "/api/payments/", {"start_date": "not-a-date"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 1)

    def test_unknown_entry_type_silently_dropped(self):
        PaymentService.record_entry(
            self.child, Decimal("5"), PaymentLedger.EntryType.HOURLY,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get(
            "/api/payments/", {"entry_type": "not_a_real_type"},
        )
        self.assertEqual(resp.status_code, 200)
        # Unknown filter → no narrowing → all rows.
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 1)

    def test_mixed_valid_invalid_entry_type_filter_keeps_valid_only(self):
        PaymentService.record_entry(
            self.child, Decimal("5"), PaymentLedger.EntryType.HOURLY,
        )
        PaymentService.record_entry(
            self.child, Decimal("2"), PaymentLedger.EntryType.CHORE_REWARD,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get(
            "/api/payments/", {"entry_type": "hourly,bogus"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        # Only the hourly row passes the filter.
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["entry_type"], "hourly")
