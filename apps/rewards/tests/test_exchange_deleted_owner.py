"""A native child deletion must turn queued exchange decisions into not found."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from decimal import Decimal
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import lifecycle
from apps.accounts.models import User
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.rewards.models import CoinLedger, ExchangeRequest
from apps.rewards.services import CoinService
from config.tests.factories import make_family


_CLIENT = ContextVar("exchange_deleted_owner_client", default=None)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExchangeDeletedOwnerConcurrencyTests(TransactionTestCase):
    def setUp(self):
        home = make_family(
            "Exchange deletion household",
            parents=[{"username": "exchange-delete-parent"}, {"username": "exchange-delete-coparent"}],
            children=[{"username": "exchange-delete-child"}, {"username": "exchange-delete-sibling"}],
        )
        self.parent, self.coparent = home.parents
        self.child, self.sibling = home.children
        self.child_id = self.child.pk
        for owner in (self.child, self.sibling):
            PaymentLedger.objects.create(user=owner, amount=Decimal("5.00"), entry_type="adjustment")
        self.exchange = ExchangeRequest.objects.create(
            user=self.child, dollar_amount=Decimal("2.00"), coin_amount=20, exchange_rate=10,
        )

    def assert_deleted_owner_is_not_found(self, operation):
        deletion_retained, owner_lock_requested, release_delete = Event(), Event(), Event()
        original_collect, original_get = lifecycle.collect_safe_deletion, QuerySet.get
        owner_backend = []

        def pause_actual_deletion(*args, **kwargs):
            result = original_collect(*args, **kwargs)
            if _CLIENT.get() == "delete":
                deletion_retained.set()
                if not release_delete.wait(8):
                    raise RuntimeError("Deletion was not released")
            return result

        def observe_actual_owner_lock(queryset, *args, **kwargs):
            if (_CLIENT.get() == "decision" and queryset.model is User
                    and queryset.query.select_for_update and kwargs.get("pk") == self.child_id):
                # This runs after the real helper read the persisted owner ID.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    owner_backend.append(cursor.fetchone()[0])
                owner_lock_requested.set()
            return original_get(queryset, *args, **kwargs)

        def worker(kind):
            connections.close_all()
            token = _CLIENT.set(kind)
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '6s'")
                        cursor.execute("SET LOCAL statement_timeout = '10s'")
                    client = APIClient(raise_request_exception=False)
                    client.force_authenticate(self.coparent if kind == "delete" else self.parent)
                    if kind == "delete":
                        response = client.delete(f"/api/children/{self.child_id}/")
                    else:
                        if not deletion_retained.wait(5):
                            raise RuntimeError("Native child deletion never retained its locks")
                        response = client.post(
                            f"/api/coins/exchange/{self.exchange.pk}/{operation}/",
                            {"notes": "Queued decision after deletion"}, format="json",
                        )
                    return {"http_status": response.status_code, "body": getattr(response, "data", None)}
            except Exception as error:
                return {"exception": type(error).__name__, "message": str(error)}
            finally:
                _CLIENT.reset(token)
                connections.close_all()

        with patch.object(lifecycle, "collect_safe_deletion", side_effect=pause_actual_deletion), patch.object(
            QuerySet, "get", new=observe_actual_owner_lock,
        ), patch.object(PaymentService, "record_entry", wraps=PaymentService.record_entry) as payment_write, patch.object(
            CoinService, "award_coins", wraps=CoinService.award_coins,
        ) as coin_write:
            with ThreadPoolExecutor(max_workers=2) as workers:
                deletion = workers.submit(worker, "delete")
                decision = workers.submit(worker, "decision")
                try:
                    self.assertTrue(deletion_retained.wait(5))
                    self.assertTrue(owner_lock_requested.wait(5))
                    deadline, waiting = monotonic() + 4, False
                    while monotonic() < deadline:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [owner_backend[0]])
                            observed = cursor.fetchone()
                        if observed and observed[0] == "Lock":
                            waiting = True
                            break
                        Event().wait(0.01)
                    self.assertTrue(waiting, "The real owner row lock must wait behind native child deletion")
                finally:
                    release_delete.set()
                results = {"delete": deletion.result(timeout=15), "decision": decision.result(timeout=15)}
            self.assertEqual(payment_write.call_count, 0)
            self.assertEqual(coin_write.call_count, 0)
        self.assertEqual(results["delete"].get("http_status"), 204, results)
        self.assertEqual(results["decision"].get("http_status"), 404, results)
        self.assertEqual(str(results["decision"]["body"]["detail"]), "This request no longer exists.")
        self.assertFalse(User.objects.filter(pk=self.child_id).exists())
        self.assertFalse(ExchangeRequest.objects.filter(pk=self.exchange.pk).exists())
        self.assertFalse(PaymentLedger.objects.filter(entry_type="coin_exchange").exists())
        self.assertFalse(CoinLedger.objects.filter(reason="exchange").exists())
        self.assertEqual(PaymentService.get_balance(self.sibling), Decimal("5.00"))
        self.assertEqual(CoinService.get_balance(self.sibling), 0)

    def test_actual_child_delete_while_rest_approval_waits_returns_not_found(self):
        self.assert_deleted_owner_is_not_found("approve")

    def test_actual_child_delete_while_rest_rejection_waits_returns_not_found(self):
        self.assert_deleted_owner_is_not_found("reject")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExchangeMissingRequestTests(TestCase):
    def test_already_missing_request_keeps_native_not_found(self):
        home = make_family("Missing exchange household", parents=[{"username": "missing-exchange-parent"}])
        client = APIClient()
        client.force_authenticate(home.parents[0])
        for operation in ("approve", "reject"):
            with self.subTest(operation=operation):
                response = client.post(f"/api/coins/exchange/9223372036854775807/{operation}/", {}, format="json")
                self.assertEqual(response.status_code, 404)
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(PaymentLedger.objects.exists())
