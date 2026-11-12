"""Native exchange decisions and MCP retain one User-before-request order."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from decimal import Decimal
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.db import connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.rewards import services
from apps.rewards.models import CoinLedger, ExchangeRequest
from apps.rewards.services import CoinService
from config.tests.factories import make_family


_DECISION_CLIENT = ContextVar("exchange_decision_client", default=None)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExchangeDecisionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        home = make_family(
            "Concurrent exchange household",
            parents=[{"username": "concurrent-exchange-parent", "is_staff": True}],
            children=[{"username": "concurrent-exchange-child"}],
        )
        self.parent, self.child = home.parents[0], home.children[0]
        PaymentLedger.objects.create(user=self.child, amount=Decimal("5.00"), entry_type="adjustment")
        self.exchange = ExchangeRequest.objects.create(
            user=self.child, dollar_amount=Decimal("2.00"), coin_amount=20, exchange_rate=10,
        )

    def assert_decisions_settle_once(self, native_operation, mcp_operation):
        native_decision_locked, mcp_started, mcp_at_decision = Event(), Event(), Event()
        original_lock = services._lock_decision

        def pause_native_after_actual_decision_lock(instance):
            client = _DECISION_CLIENT.get()
            if client == "mcp":
                mcp_at_decision.set()
            original_lock(instance)
            if client == "native":
                # Instrument the real service lock: no external request prelock.
                # With User-first ordering MCP waits for its member locks and
                # cannot reach the request yet, so this wait must be bounded.
                native_decision_locked.set()
                if not mcp_started.wait(5):
                    raise RuntimeError("The MCP worker did not start")
                mcp_at_decision.wait(2)

        def native():
            connections.close_all()
            token = _DECISION_CLIENT.set("native")
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '6s'")
                        cursor.execute("SET LOCAL statement_timeout = '10s'")
                    client = APIClient()
                    client.force_authenticate(self.parent)
                    response = client.post(
                        f"/api/coins/exchange/{self.exchange.pk}/{native_operation}/",
                        {"notes": "Native first decision"}, format="json",
                    )
                    return {"http_status": response.status_code, "body": response.data}
            except Exception as error:
                return {"exception": type(error).__name__, "message": str(error)}
            finally:
                _DECISION_CLIENT.reset(token)
                connections.close_all()

        def assistant():
            connections.close_all()
            token = _DECISION_CLIENT.set("mcp")
            try:
                if not native_decision_locked.wait(5):
                    raise RuntimeError("Native never reached its actual decision lock")
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '6s'")
                        cursor.execute("SET LOCAL statement_timeout = '10s'")
                    mcp_started.set()
                    with override_user(self.parent, scopes=frozenset({"mcp:read", "mcp:write"})):
                        result = async_to_sync(mcp.call_tool)(mcp_operation, {
                            "params": {"exchange_id": self.exchange.pk, "notes": "MCP later decision"},
                            "confirmation": True,
                        })
                    return result.structuredContent if hasattr(result, "structuredContent") else result[1]
            except Exception as error:
                return {"exception": type(error).__name__, "message": str(error)}
            finally:
                _DECISION_CLIENT.reset(token)
                connections.close_all()

        with patch.object(services, "_lock_decision", side_effect=pause_native_after_actual_decision_lock):
            with ThreadPoolExecutor(max_workers=2) as workers:
                native_future = workers.submit(native)
                mcp_future = workers.submit(assistant)
                results = {"native": native_future.result(timeout=20), "mcp": mcp_future.result(timeout=20)}
        self.assertTrue(native_decision_locked.is_set())
        self.assertTrue(mcp_started.is_set())
        self.assertEqual(results["native"].get("http_status"), 200, results)
        self.assertNotIn("error", results["mcp"], results)
        self.assertNotIn("exception", results["mcp"], results)
        expected = "approved" if native_operation == "approve" else "denied"
        self.assertEqual(results["native"]["body"]["status"], expected)
        self.assertEqual(results["mcp"]["status"], expected)
        self.assertEqual(results["mcp"]["parent_notes"], "Native first decision")
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, expected)
        self.assertEqual(self.exchange.parent_notes, "Native first decision")
        self.assertEqual(PaymentService.get_balance(self.child), Decimal("3.00" if expected == "approved" else "5.00"))
        self.assertEqual(CoinService.get_balance(self.child), 20 if expected == "approved" else 0)
        self.assertEqual(PaymentLedger.objects.filter(user=self.child, entry_type="coin_exchange").count(),
                         1 if expected == "approved" else 0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="exchange").count(),
                         1 if expected == "approved" else 0)

    def test_native_approval_and_mcp_approval_return_one_saved_settlement(self):
        self.assert_decisions_settle_once("approve", "approve_exchange")

    def test_native_approval_and_mcp_rejection_preserve_first_settlement(self):
        self.assert_decisions_settle_once("approve", "reject_exchange")

    def test_native_rejection_and_mcp_approval_preserve_first_decision(self):
        self.assert_decisions_settle_once("reject", "approve_exchange")
