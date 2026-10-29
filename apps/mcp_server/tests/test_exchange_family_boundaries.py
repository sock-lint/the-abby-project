"""Exchange decisions retain current household authority through settlement."""
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.exceptions import PermissionDenied

from apps.activity.models import ActivityEvent
from apps.chronicle.models import ChronicleEntry
from apps.mcp_server import legacy_household
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.notifications.models import Notification
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.rewards.models import CoinLedger, ExchangeRequest
from apps.rewards import services as reward_services
from apps.rewards.services import CoinService, ExchangeService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExchangeFamilyBoundaryTests(TestCase):
    def setUp(self):
        home = make_family(
            "Exchange decision household",
            parents=[{"username": "exchange-boundary-parent", "is_staff": True},
                     {"username": "exchange-boundary-coparent", "is_staff": True}],
            children=[{"username": "exchange-boundary-child"}],
        )
        other = make_family(
            "Other exchange household",
            parents=[{"username": "exchange-boundary-outsider", "is_staff": True}],
            children=[{"username": "exchange-boundary-foreign-child"}],
        )
        self.parent, self.coparent = home.parents
        self.child = home.children[0]
        self.other_family, self.foreign_child = other.family, other.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def exchange(self, user=None):
        user = user or self.child
        PaymentLedger.objects.create(user=user, amount=Decimal("5.00"), entry_type="adjustment")
        return ExchangeRequest.objects.create(
            user=user, dollar_amount=Decimal("2.00"), coin_amount=20, exchange_rate=10,
            parent_notes="Saved pending note",
        )

    def wire(self, operation, exchange_id, *, actor=None, notes="Reviewed exchange"):
        with override_user(actor or self.parent, scopes=frozenset({"mcp:read", "mcp:write"})):
            result = async_to_sync(mcp.call_tool)(operation, {
                "params": {"exchange_id": exchange_id, "notes": notes}, "confirmation": True,
            })
        return result.structuredContent if hasattr(result, "structuredContent") else result[1]

    def snapshot(self):
        # Include the settlement hooks, not just the request's status.
        return {
            model._meta.label_lower: list(model.objects.order_by("pk").values())
            for model in (ExchangeRequest, PaymentLedger, CoinLedger, ActivityEvent, Notification, ChronicleEntry)
        }

    def assert_error(self, result, code):
        self.assertEqual(result.get("error", {}).get("code"), code, result)
        self.assertNotIn("id", result)
        return result["error"]

    def test_foreign_decisions_match_missing_without_any_settlement(self):
        for operation in ("approve_exchange", "reject_exchange"):
            with self.subTest(operation=operation):
                foreign = self.exchange(self.foreign_child)
                route = "approve" if operation == "approve_exchange" else "reject"
                self.assertEqual(
                    self.client.post(f"/api/coins/exchange/{foreign.pk}/{route}/", {}, format="json").status_code,
                    404,
                )
                before = self.snapshot()
                missing = self.assert_error(self.wire(operation, 9223372036854775807), "not_found")
                result = self.wire(operation, foreign.pk)
                error = self.assert_error(result, "not_found")
                self.assertEqual(
                    {key: value for key, value in error.items() if key != "message"},
                    {key: value for key, value in missing.items() if key != "message"},
                )
                self.assertEqual(error["message"], f"ExchangeRequest {foreign.pk} not found.")
                self.assertEqual(self.snapshot(), before)

    def test_same_family_approval_replay_preserves_native_receipt(self):
        row = self.exchange()
        result = self.wire("approve_exchange", row.pk, notes="Agreed first note")
        self.assertEqual(result["status"], "approved", result)
        row.refresh_from_db()
        self.assertEqual(row.decided_by_id, self.parent.pk)
        self.assertEqual(row.parent_notes, "Agreed first note")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("3.00"))
        self.assertEqual(CoinService.get_balance(self.child), 20)
        before = self.snapshot()
        self.assertEqual(self.wire("approve_exchange", row.pk, notes="Later retry note"), result)
        self.assertEqual(self.snapshot(), before)

    def test_same_family_rejection_replay_keeps_ledgers_and_notes(self):
        row = self.exchange()
        result = self.wire("reject_exchange", row.pk, notes="Saved rejection note")
        self.assertEqual(result["status"], "denied", result)
        row.refresh_from_db()
        self.assertEqual(row.decided_by_id, self.parent.pk)
        self.assertEqual(row.parent_notes, "Saved rejection note")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("5.00"))
        self.assertEqual(CoinService.get_balance(self.child), 0)
        before = self.snapshot()
        self.assertEqual(self.wire("reject_exchange", row.pk, notes="Later retry note"), result)
        self.assertEqual(self.snapshot(), before)

    def test_inactive_same_family_history_keeps_native_decisions(self):
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)
        for operation, expected in (("approve_exchange", "approved"), ("reject_exchange", "denied")):
            with self.subTest(operation=operation):
                row = self.exchange()
                self.assertEqual(self.wire(operation, row.pk)["status"], expected)

    def test_saved_self_and_coparent_requests_keep_family_admission(self):
        # Native Family administration is not child-only for saved requests.
        for target in (self.parent, self.coparent):
            with self.subTest(target=target.pk):
                row = self.exchange(target)
                self.assertEqual(self.wire("reject_exchange", row.pk)["status"], "denied")

    def test_departed_subject_is_not_adopted_from_saved_exchange_id(self):
        for operation in ("approve_exchange", "reject_exchange"):
            with self.subTest(operation=operation):
                get_user_model().objects.filter(pk=self.child.pk).update(family_id=self.parent.family_id)
                row = self.exchange()
                get_user_model().objects.filter(pk=self.child.pk).update(family=self.other_family)
                before = self.snapshot()
                self.assert_error(self.wire(operation, row.pk), "not_found")
                self.assertEqual(self.snapshot(), before)

    def assert_stale_actor_denied(self, changes):
        for operation in ("approve_exchange", "reject_exchange"):
            with self.subTest(operation=operation):
                # Keep the queued actor snapshot while changing persisted authority.
                get_user_model().objects.filter(pk=self.parent.pk).update(
                    role="parent", is_staff=True, is_active=True, family_id=self.parent.family_id,
                )
                row = self.exchange()
                get_user_model().objects.filter(pk=self.parent.pk).update(**changes)
                before = self.snapshot()
                self.assert_error(self.wire(operation, row.pk), "permission_denied")
                self.assertEqual(self.snapshot(), before)

    def test_deactivated_actor_cannot_settle_from_queued_identity(self):
        self.assert_stale_actor_denied({"is_active": False})

    def test_demoted_actor_cannot_settle_from_queued_identity(self):
        self.assert_stale_actor_denied({"role": "child"})

    def test_removed_staff_actor_cannot_settle_from_queued_identity(self):
        self.assert_stale_actor_denied({"is_staff": False})

    def test_departed_actor_cannot_settle_from_queued_identity(self):
        self.assert_stale_actor_denied({"family": self.other_family})

    def test_post_lock_join_cannot_expand_the_authorized_member_cohort(self):
        original_context = legacy_household.household_context

        @contextmanager
        def join_after_lock(*args, **kwargs):
            with original_context(*args, **kwargs) as pair:
                # Simulate an out-of-band move after the retained cohort was read.
                get_user_model().objects.filter(pk=self.foreign_child.pk).update(family_id=self.parent.family_id)
                yield pair

        for operation in ("approve_exchange", "reject_exchange"):
            with self.subTest(operation=operation):
                get_user_model().objects.filter(pk=self.foreign_child.pk).update(family=self.other_family)
                row = self.exchange(self.foreign_child)
                before = self.snapshot()
                with patch.object(legacy_household, "household_context", side_effect=join_after_lock):
                    self.assert_error(self.wire(operation, row.pk), "not_found")
                self.assertEqual(self.snapshot(), before)

    def test_child_actor_cannot_decide_even_own_request(self):
        row = self.exchange()
        before = self.snapshot()
        for operation in ("approve_exchange", "reject_exchange"):
            with self.subTest(operation=operation):
                self.assert_error(self.wire(operation, row.pk, actor=self.child), "permission_denied")
        self.assertEqual(self.snapshot(), before)

    def test_native_stale_owner_snapshot_settles_the_current_locked_owner(self):
        for operation in (ExchangeService.approve, ExchangeService.reject):
            with self.subTest(operation=operation.__name__):
                row = self.exchange()
                stale = ExchangeRequest.objects.select_related("user").get(pk=row.pk)
                PaymentLedger.objects.create(user=self.coparent, amount=Decimal("5.00"), entry_type="adjustment")
                ExchangeRequest.objects.filter(pk=row.pk).update(user=self.coparent)
                child_before = PaymentService.get_balance(self.child)
                owner_money_before = PaymentService.get_balance(self.coparent)
                owner_coins_before = CoinService.get_balance(self.coparent)
                result = operation(stale, self.parent)
                self.assertEqual(result.user_id, self.coparent.pk)
                self.assertEqual(PaymentService.get_balance(self.child), child_before)
                self.assertEqual(PaymentService.get_balance(self.coparent), owner_money_before - (
                    Decimal("2.00") if operation == ExchangeService.approve else Decimal("0.00")))
                self.assertEqual(CoinService.get_balance(self.coparent), owner_coins_before + (
                    20 if operation == ExchangeService.approve else 0))

    def test_subject_change_during_wallet_lock_rolls_back_before_settlement(self):
        original_lock = reward_services._lock_decision

        def retarget_before_request_lock(instance):
            ExchangeRequest.objects.filter(pk=instance.pk).update(user=self.coparent)
            original_lock(instance)

        for operation in (ExchangeService.approve, ExchangeService.reject):
            with self.subTest(operation=operation.__name__):
                row = self.exchange()
                PaymentLedger.objects.create(user=self.coparent, amount=Decimal("5.00"), entry_type="adjustment")
                before = self.snapshot()
                with patch.object(reward_services, "_lock_decision", side_effect=retarget_before_request_lock):
                    with self.assertRaises(PermissionDenied):
                        operation(row, self.parent)
                self.assertEqual(self.snapshot(), before)
