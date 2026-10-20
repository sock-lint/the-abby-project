"""Retry identities prevent repeated MCP rewards and accounting writes."""
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from pydantic import ValidationError

from apps.accounts.models import User
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.models import MCPMutationReceipt
from apps.mcp_server.schemas import (
    AdjustPaymentIn, CreateProjectIn, LogMovementSessionIn, RequestRedemptionIn,
)
from apps.mcp_server.tools import movement, payments, projects, rewards
from apps.movement.models import MovementDailyCounter, MovementSession, MovementType
from apps.payments.models import PaymentLedger
from apps.projects.models import Project
from apps.rewards.models import CoinLedger, Reward, RewardRedemption
from apps.rewards.services import CoinService
from config.tests.factories import make_family


class _MutationFixtures:
    def setUp(self):
        family = make_family(
            "MCP retries", parents=[{"username": "retry-parent", "is_staff": True}],
            children=[{"username": "retry-child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.movement_type = MovementType.objects.create(name="Retry walk", slug="retry-walk")
        self.reward = Reward.objects.create(
            family=family.family, name="Retry reward", cost_coins=10, stock=5,
        )
        CoinService.award_coins(self.child, 100, CoinLedger.Reason.ADJUSTMENT)

    def operations(self):
        return [
            ("adjust_payment", self.parent, payments.adjust_payment, AdjustPaymentIn(
                request_id=uuid4(), user_id=self.child.pk, amount="4.50", description="Private adjustment",
            ), PaymentLedger, "description", "Changed adjustment"),
            ("create_project", self.parent, projects.create_project, CreateProjectIn(
                request_id=uuid4(), title="Private project", assigned_to_id=self.child.pk,
            ), Project, "title", "Changed project"),
            ("request_redemption", self.child, rewards.request_redemption, RequestRedemptionIn(
                request_id=uuid4(), reward_id=self.reward.pk,
            ), RewardRedemption, "reward_id", self.reward.pk + 100000),
            ("log_movement_session", self.parent, movement.log_movement_session, LogMovementSessionIn(
                client_request_id=uuid4(), movement_type_id=self.movement_type.pk,
                duration_minutes=20, user_id=self.child.pk, notes="Private movement",
                distance="1.25", distance_unit="mi",
            ), MovementSession, "duration_minutes", 30),
        ]


class MutationRetryTests(_MutationFixtures, TestCase):
    def test_identical_adjustment_retry_appends_one_ledger_entry(self):
        params = AdjustPaymentIn(
            request_id=uuid4(), user_id=self.child.pk, amount=Decimal("4.50"), description="Reviewed adjustment",
        )
        with override_user(self.parent):
            first = payments.adjust_payment(params)
            retry = payments.adjust_payment(params)
        self.assertEqual(retry, first)
        self.assertEqual(PaymentLedger.objects.filter(user=self.child).count(), 1)

    def test_identical_project_retry_creates_one_project(self):
        params = CreateProjectIn(
            request_id=uuid4(), title="One project", assigned_to_id=self.child.pk,
        )
        with override_user(self.parent):
            first = projects.create_project(params)
            retry = projects.create_project(params)
        self.assertEqual(retry, first)
        self.assertEqual(Project.objects.filter(assigned_to=self.child).count(), 1)

    def test_numeric_formatting_changes_do_not_change_retry_identity(self):
        params = AdjustPaymentIn(request_id=uuid4(), user_id=self.child.pk, amount="4.50", description="Adjustment")
        with override_user(self.parent):
            first = payments.adjust_payment(params)
            equivalent = AdjustPaymentIn(**{**params.model_dump(), "amount": "4.5"})
            self.assertEqual(payments.adjust_payment(equivalent), first)
        self.assertEqual(PaymentLedger.objects.count(), 1)

    def test_replay_returns_original_project_receipt_after_an_authorized_edit(self):
        params = CreateProjectIn(request_id=uuid4(), title="Original plan", assigned_to_id=self.child.pk)
        with override_user(self.parent):
            first = projects.create_project(params)
            Project.objects.filter(pk=first["id"]).update(title="Current edited plan")
            self.assertEqual(projects.create_project(params), first)
        self.assertEqual(Project.objects.get().title, "Current edited plan")

    def test_identical_redemption_retry_spends_once_and_reserves_one_item(self):
        params = RequestRedemptionIn(request_id=uuid4(), reward_id=self.reward.pk)
        with override_user(self.child):
            first = rewards.request_redemption(params)
            retry = rewards.request_redemption(params)
        self.assertEqual(retry, first)
        self.assertEqual(RewardRedemption.objects.filter(user=self.child).count(), 1)
        self.assertEqual(CoinService.get_balance(self.child), 90)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 4)

    def test_identical_movement_retry_preserves_counter_and_award(self):
        params = LogMovementSessionIn(
            client_request_id=uuid4(), movement_type_id=self.movement_type.pk, duration_minutes=20, user_id=self.child.pk,
            distance=Decimal("1.25"), distance_unit="mi",
        )
        with override_user(self.parent):
            first = movement.log_movement_session(params)
            retry = movement.log_movement_session(params)
        self.assertEqual(retry, first)
        self.assertEqual(MovementSession.objects.filter(user=self.child).count(), 1)
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 1)
        self.assertEqual(MovementSession.objects.get(user=self.child).distance_meters, Decimal("2011.680"))

    def test_movement_uuid_is_shared_by_authorized_callers_before_and_after_delete(self):
        params = LogMovementSessionIn(
            client_request_id=uuid4(), movement_type_id=self.movement_type.pk, duration_minutes=20,
        )
        with override_user(self.child):
            first = movement.log_movement_session(params)
        parent_params = params.model_copy(update={"user_id": self.child.pk})
        with override_user(self.parent):
            self.assertEqual(movement.log_movement_session(parent_params), first)
            with self.assertRaises(MCPValidationError) as error:
                movement.log_movement_session(parent_params.model_copy(update={"duration_minutes": 30}))
            self.assertEqual(error.exception.code, "idempotency_conflict")
        self.assertEqual(MCPMutationReceipt.objects.filter(operation="log_movement_session").count(), 1)
        MovementSession.objects.get(pk=first["id"]).delete()
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            movement.log_movement_session(parent_params)
        self.assertFalse(MovementSession.objects.exists())
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 1)

    def test_movement_tombstone_survives_original_parent_account_deletion(self):
        params = LogMovementSessionIn(
            client_request_id=uuid4(), user_id=self.child.pk,
            movement_type_id=self.movement_type.pk, duration_minutes=20,
        )
        other_parent = User.objects.create_user(username="surviving-parent", role="parent", family=self.parent.family)
        with override_user(self.parent):
            result = movement.log_movement_session(params)
        MovementSession.objects.get(pk=result["id"]).delete()
        self.parent.delete()
        receipt = MCPMutationReceipt.objects.get(operation="log_movement_session")
        self.assertIsNone(receipt.actor_id)
        self.assertIsNone(receipt.response)
        with override_user(other_parent), self.assertRaises(MCPNotFoundError):
            movement.log_movement_session(params)
        self.assertFalse(MovementSession.objects.exists())
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 1)

    def test_all_four_schemas_require_stable_uuid(self):
        for name, actor, invoke, params, model, field, changed in self.operations():
            with self.subTest(operation=name):
                uuid_field = "client_request_id" if name == "log_movement_session" else "request_id"
                missing = params.model_dump(exclude={uuid_field})
                with self.assertRaises(ValidationError):
                    type(params)(**missing)
                with self.assertRaises(ValidationError):
                    type(params)(**missing, **{uuid_field: "not-a-uuid"})

    def test_changed_request_details_conflict_without_another_operation(self):
        # The replacement reward must exist so the handler reaches the saved
        # UUID comparison rather than stopping at its ordinary lookup.
        other_reward = Reward.objects.create(family=self.parent.family, name="Other reward", cost_coins=10)
        for name, actor, invoke, params, model, field, changed in self.operations():
            if name == "request_redemption":
                changed = other_reward.pk
            with self.subTest(operation=name), override_user(actor):
                invoke(params)
                with self.assertRaises(MCPValidationError) as error:
                    invoke(params.model_copy(update={field: changed}))
                self.assertEqual(error.exception.code, "idempotency_conflict")
                self.assertEqual(model.objects.count(), 1)

    def test_source_deletion_scrubs_snapshot_and_uuid_cannot_recreate_it(self):
        for name, actor, invoke, params, model, field, changed in self.operations():
            with self.subTest(operation=name), override_user(actor):
                result = invoke(params)
                model.objects.get(pk=result["id"]).delete()
                receipt = MCPMutationReceipt.objects.get(operation=name)
                self.assertIsNone(receipt.response)
                with self.assertRaises(MCPNotFoundError):
                    invoke(params)
                self.assertFalse(model.objects.exists())
        self.assertEqual(CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.REDEMPTION).amount, -10)
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 1)

    def test_replay_rechecks_source_owner_after_project_reassignment(self):
        params = CreateProjectIn(request_id=uuid4(), title="Reassigned plan", assigned_to_id=self.child.pk)
        other = User.objects.create_user(username="other-child", role="child", family=self.parent.family)
        with override_user(self.parent):
            result = projects.create_project(params)
            Project.objects.filter(pk=result["id"]).update(assigned_to=other)
            with self.assertRaises(MCPNotFoundError):
                projects.create_project(params)
        self.assertEqual(Project.objects.count(), 1)

    def test_replay_rechecks_actor_role_and_active_state(self):
        params = AdjustPaymentIn(request_id=uuid4(), user_id=self.child.pk, amount="1.00", description="Adjustment")
        with override_user(self.parent):
            payments.adjust_payment(params)
            for changes in ({"is_active": False}, {"role": "child"}, {"is_staff": False}):
                with self.subTest(changes=changes):
                    User.objects.filter(pk=self.parent.pk).update(**changes)
                    with self.assertRaises(MCPPermissionDenied):
                        payments.adjust_payment(params)
                    User.objects.filter(pk=self.parent.pk).update(is_active=True, role="parent", is_staff=True)
        self.assertEqual(PaymentLedger.objects.count(), 1)

    def test_replay_rechecks_target_membership(self):
        params = AdjustPaymentIn(request_id=uuid4(), user_id=self.child.pk, amount="1.00", description="Adjustment")
        with override_user(self.parent):
            payments.adjust_payment(params)
            foreign = make_family("Other household").family
            User.objects.filter(pk=self.child.pk).update(family=foreign)
            with self.assertRaises(MCPNotFoundError):
                payments.adjust_payment(params)
        self.assertEqual(PaymentLedger.objects.count(), 1)

    def test_cached_shared_responses_are_scrubbed_when_any_member_is_deleted(self):
        params = CreateProjectIn(request_id=uuid4(), title="Shared plan", assigned_to_id=self.child.pk)
        with override_user(self.parent):
            projects.create_project(params)
        departing = User.objects.create_user(username="departing-parent", role="parent", family=self.parent.family)
        departing.delete()
        self.assertIsNone(MCPMutationReceipt.objects.get().response)
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            projects.create_project(params)
        self.assertEqual(Project.objects.count(), 1)

    def test_target_account_deletion_removes_private_receipts(self):
        for name, actor, invoke, params, model, field, changed in self.operations():
            with override_user(actor):
                invoke(params)
        self.child.delete()
        self.assertFalse(MCPMutationReceipt.objects.exists())

    def test_receipt_failure_rolls_back_ledger_stock_counter_and_project(self):
        for name, actor, invoke, params, model, field, changed in self.operations():
            with self.subTest(operation=name), override_user(actor), patch.object(
                MCPMutationReceipt.objects, "create", side_effect=RuntimeError("Receipt storage failed"),
            ):
                with self.assertRaisesMessage(RuntimeError, "Receipt storage failed"):
                    invoke(params)
                self.assertFalse(model.objects.exists())
        self.assertEqual(CoinService.get_balance(self.child), 100)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 5)
        self.assertFalse(MovementDailyCounter.objects.exists())
        self.assertFalse(MCPMutationReceipt.objects.exists())

    def test_oversized_response_rolls_back_instead_of_losing_retry_protection(self):
        params = AdjustPaymentIn(request_id=uuid4(), user_id=self.child.pk, amount="1.00", description="Adjustment")
        with override_user(self.parent), patch("apps.mcp_server.retries.MAX_RESPONSE_BYTES", 1):
            with self.assertRaises(MCPValidationError):
                payments.adjust_payment(params)
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertFalse(MCPMutationReceipt.objects.exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class MutationConcurrencyTests(_MutationFixtures, TransactionTestCase):
    def test_movement_uuid_race_across_authorized_parent_and_child(self):
        ready = Barrier(2)
        request_id = uuid4()

        def call(actor_id):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '20s'")
                actor = User.objects.get(pk=actor_id)
                params = LogMovementSessionIn(
                    client_request_id=request_id, movement_type_id=self.movement_type.pk,
                    duration_minutes=20, user_id=self.child.pk if actor.role == "parent" else None,
                )
                ready.wait(timeout=5)
                with override_user(actor):
                    return movement.log_movement_session(params)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(call, actor.pk) for actor in (self.parent, self.child)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(MovementSession.objects.count(), 1)
        self.assertEqual(MCPMutationReceipt.objects.count(), 1)
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 1)

    def test_same_uuid_races_return_one_result_per_operation(self):
        for name, actor, invoke, params, model, field, changed in self.operations():
            with self.subTest(operation=name):
                ready = Barrier(2)

                def call():
                    close_old_connections()
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute("SET lock_timeout = '10s'")
                            cursor.execute("SET statement_timeout = '20s'")
                        current_actor = User.objects.get(pk=actor.pk)
                        ready.wait(timeout=5)
                        with override_user(current_actor):
                            return invoke(params)
                    finally:
                        connection.close()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(call) for _ in range(2)]
                    results = [future.result(timeout=30) for future in futures]
                self.assertEqual(results[0], results[1])
                self.assertEqual(model.objects.count(), 1)
                self.assertEqual(MCPMutationReceipt.objects.filter(operation=name).count(), 1)
        self.assertEqual(CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.REDEMPTION).amount, -10)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.stock, 4)
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 1)
