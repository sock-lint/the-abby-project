"""Global temporary-credential admission serializes on real PostgreSQL locks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.google_integration.models import GoogleOAuthAdmission, GoogleOAuthTransaction
from apps.google_integration.services import GoogleAuthService
from apps.google_integration.tests.test_oauth_exchange import BASE, challenge, provider_authorization


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locking")
@override_settings(
    GOOGLE_CLIENT_ID="synthetic-client.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="synthetic-server-secret",
    GOOGLE_REDIRECT_URI="https://testserver/api/auth/google/callback/",
)
class GoogleOAuthAdmissionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        provider = patch.object(GoogleAuthService, "get_authorization_url", side_effect=provider_authorization)
        provider.start()
        self.addCleanup(provider.stop)

    @staticmethod
    def request(peer, barrier):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '8s'")
            client = APIClient()
            client.raise_request_exception = False
            barrier.wait(timeout=5)
            response = client.get(BASE + "login/", {
                "code_challenge": challenge(), "code_challenge_method": "S256",
            }, REMOTE_ADDR=peer)
            return response.status_code, response.json()
        finally:
            connections.close_all()

    def assert_one_admitted(self, results):
        self.assertEqual(sorted(status for status, _ in results), [200, 503], results)
        rejected = next(body for status, body in results if status == 503)
        self.assertEqual(rejected["code"], "authorization_busy")
        self.assertEqual(GoogleOAuthTransaction.objects.count(), 1)
        self.assertEqual(GoogleOAuthAdmission.objects.count(), 1)

    def test_concurrent_first_authorizations_share_single_global_admission_row(self):
        self.assertFalse(GoogleOAuthAdmission.objects.exists())
        barrier = Barrier(2)
        with patch("apps.google_integration.oauth_exchange.MAX_TRANSACTIONS", 1), ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(self.request, f"192.0.2.{index + 1}", barrier) for index in range(2)]
            self.assert_one_admitted([request.result(timeout=12) for request in requests])

    def test_global_admission_row_lock_fences_both_requests_before_the_capacity_check(self):
        admission = GoogleOAuthAdmission.objects.create(pk=1)
        barrier = Barrier(2)
        with patch("apps.google_integration.oauth_exchange.MAX_TRANSACTIONS", 1), ThreadPoolExecutor(max_workers=2) as pool:
            with transaction.atomic():
                GoogleOAuthAdmission.objects.select_for_update().get(pk=admission.pk)
                requests = [pool.submit(self.request, f"192.0.2.{index + 1}", barrier) for index in range(2)]
                deadline = monotonic() + 3
                blocked = 0
                while monotonic() < deadline and blocked < 2:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_stat_clear_snapshot()")
                        cursor.execute(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                            "AND wait_event_type = 'Lock' "
                            "AND query LIKE %s",
                            ["%google_integration_googleoauthadmission%"],
                        )
                        blocked = cursor.fetchone()[0]
                    if blocked < 2:
                        sleep(0.01)
                self.assertEqual(blocked, 2, "Both requests must wait for the global admission row before checking capacity")
            self.assert_one_admitted([request.result(timeout=12) for request in requests])
