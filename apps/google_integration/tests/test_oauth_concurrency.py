"""PostgreSQL transactions exercise replay and real account-deletion races."""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, local
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from django.core.cache import cache
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.google_integration import oauth_exchange
from apps.google_integration.models import CalendarEventMapping, GoogleAccount
from apps.google_integration.services import GoogleAuthService
from config.tests.factories import make_family


BASE = "/api/auth/google/"
PROOF = "synthetic-concurrent-browser-proof-" + "a" * 32
GOOGLE_ID = "synthetic-concurrent-google-subject"
_worker = local()


@skipUnlessDBFeature("has_select_for_update_nowait")
@override_settings(
    GOOGLE_CLIENT_ID="synthetic-concurrency-client.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="synthetic-concurrency-client-secret",
    GOOGLE_REDIRECT_URI="https://testserver/api/auth/google/callback/",
)
class GoogleOAuthConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        family = make_family(
            "Google concurrency family",
            parents=[{"username": "oauth-departing"}, {"username": "oauth-remaining"}],
            children=[{"username": "oauth-child"}],
        )
        self.parent = family.parents[0]
        self.child = family.children[0]
        self.token = Token.objects.create(user=self.parent)

        def authorization(*, state):
            return (
                "https://accounts.google.com/o/oauth2/auth?" + urlencode({"state": state}),
                state, "synthetic-concurrent-provider-pkce",
            )

        start = patch.object(GoogleAuthService, "get_authorization_url", side_effect=authorization)
        start.start()
        self.addCleanup(start.stop)
        callback = patch.object(GoogleAuthService, "exchange_code", return_value=(
            GOOGLE_ID, "synthetic-concurrency@example.invalid", {"token": "synthetic-concurrent-provider-token"},
        ))
        callback.start()
        self.addCleanup(callback.stop)

    def _ticket(self, *, link=False):
        client = APIClient()
        if link:
            client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(PROOF.encode()).digest()).decode().rstrip("=")
        query = {"code_challenge": challenge, "code_challenge_method": "S256"}
        if link:
            query["for_user"] = self.child.pk
        started = client.get(BASE + ("" if link else "login/"), query)
        self.assertEqual(started.status_code, 200, started.data)
        response = APIClient().get(BASE + "callback/", {
            "state": started.data["state"], "code": "synthetic-concurrent-provider-code",
        })
        self.assertEqual(response.status_code, 302)
        fragment = parse_qs(urlsplit(response.url).fragment)
        self.assertIn("google_exchange", fragment)
        return fragment["google_exchange"][0]

    @staticmethod
    def _thread_connection(label):
        close_old_connections()
        _worker.label = label
        _worker.opened = False
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '10s'")

    def _redeem(self, ticket, *, label="exchange", authenticated=False):
        self._thread_connection(label)
        try:
            client = APIClient()
            if authenticated:
                client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
            response = client.post(BASE + "exchange/", {
                "exchange_code": ticket, "code_verifier": PROOF,
            }, format="json")
            return response.status_code, response.data
        finally:
            connection.close()
            _worker.label = None

    def test_two_proof_redemptions_from_the_same_ready_snapshot_issue_one_response(self):
        GoogleAccount.objects.create(
            user=self.parent, google_id=GOOGLE_ID, google_email="synthetic-concurrency@example.invalid",
            encrypted_credentials=GoogleAuthService.encrypt_credentials({"token": "synthetic-existing-token"}),
        )
        ticket = self._ticket()
        both_snapshots = Barrier(2, timeout=10)
        original_open = oauth_exchange._open

        def synchronize_snapshots(payload):
            result = original_open(payload)
            if str(getattr(_worker, "label", "")).startswith("redeem-") and not _worker.opened:
                _worker.opened = True
                both_snapshots.wait()
            return result

        with patch.object(oauth_exchange, "_open", synchronize_snapshots), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self._redeem, ticket, label="redeem-first")
            second = pool.submit(self._redeem, ticket, label="redeem-second")
            results = [first.result(timeout=15), second.result(timeout=15)]
        self.assertEqual(sorted(status for status, _body in results), [200, 400])
        success = next(body for status, body in results if status == 200)
        failure = next(body for status, body in results if status == 400)
        self.assertEqual(success["token"], self.token.key)
        self.assertEqual(failure["code"], "invalid_exchange")
        self.assertEqual(Token.objects.filter(user=self.parent).count(), 1)

    def _deletion_race(self, *, link, child_table):
        if not link:
            GoogleAccount.objects.create(
                user=self.parent, google_id=GOOGLE_ID, google_email="synthetic-concurrency@example.invalid",
                encrypted_credentials=GoogleAuthService.encrypt_credentials({"token": "synthetic-existing-token"}),
            )
        ticket = self._ticket(link=link)
        dependent_deleted, release_deletion = Event(), Event()

        def delete_account():
            self._thread_connection("delete")
            try:
                def hold_after_dependent_delete(execute, sql, params, many, context):
                    result = execute(sql, params, many, context)
                    if sql.lstrip().upper().startswith("DELETE FROM") and f'"{child_table}"' in sql:
                        # Django's actual cascade has deleted this dependent
                        # row but has not yet reached its final User DELETE.
                        dependent_deleted.set()
                        if not release_deletion.wait(10):
                            raise TimeoutError("Account cascade was not released")
                    return result

                with connection.execute_wrapper(hold_after_dependent_delete):
                    User.objects.get(pk=self.parent.pk).delete()
            finally:
                connection.close()
                _worker.label = None

        with ThreadPoolExecutor(max_workers=2) as pool:
            deleting = pool.submit(delete_account)
            try:
                self.assertTrue(dependent_deleted.wait(5), "Real account deletion did not reach its dependent row")
                exchanging = pool.submit(self._redeem, ticket, authenticated=link)
                # Exchange holds User before dependent rows; the old cascade
                # holds dependent rows before User. Decline while deletion is
                # still paused instead of relying on a deadlock victim/retry.
                status, body = exchanging.result(timeout=3)
                self.assertEqual(status, 400)
                self.assertEqual(body["code"], "authorization_changed")
            finally:
                release_deletion.set()
            deleting.result(timeout=15)
        self.assertFalse(User.objects.filter(pk=self.parent.pk).exists())
        self.assertFalse(Token.objects.filter(user_id=self.parent.pk).exists())
        self.assertFalse(GoogleAccount.objects.filter(google_id=GOOGLE_ID).exists())
        self.assertTrue(User.objects.filter(pk=self.child.pk).exists())

    def test_link_redemption_declines_while_actual_user_delete_holds_the_flow(self):
        self._deletion_race(link=True, child_table="google_integration_googleoauthtransaction")

    def test_login_redemption_declines_while_actual_user_delete_holds_google_account(self):
        self._deletion_race(link=False, child_table="google_integration_googleaccount")

    def test_child_unlink_declines_while_actual_user_delete_holds_calendar_mapping(self):
        GoogleAccount.objects.create(
            user=self.child, google_id=GOOGLE_ID, google_email="synthetic-concurrency@example.invalid",
            encrypted_credentials=GoogleAuthService.encrypt_credentials({"token": "synthetic-existing-token"}),
            linked_by=self.parent,
        )
        CalendarEventMapping.objects.create(
            user=self.child, content_type="chore", object_id=42,
            google_event_id="synthetic-concurrent-calendar-event",
        )
        mapping_deleted, release_deletion = Event(), Event()

        def delete_child():
            self._thread_connection("delete-child")
            try:
                def hold_after_mapping_delete(execute, sql, params, many, context):
                    result = execute(sql, params, many, context)
                    if (sql.lstrip().upper().startswith("DELETE FROM")
                            and '"google_integration_calendareventmapping"' in sql):
                        mapping_deleted.set()
                        if not release_deletion.wait(10):
                            raise TimeoutError("Child cascade was not released")
                    return result

                with connection.execute_wrapper(hold_after_mapping_delete):
                    User.objects.get(pk=self.child.pk).delete()
            finally:
                connection.close()
                _worker.label = None

        def unlink_child():
            self._thread_connection("unlink-child")
            try:
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
                response = client.delete(BASE + f"account/?for_user={self.child.pk}")
                return response.status_code, response.data
            finally:
                connection.close()
                _worker.label = None

        with ThreadPoolExecutor(max_workers=2) as pool:
            deleting = pool.submit(delete_child)
            try:
                self.assertTrue(mapping_deleted.wait(5), "Real child deletion did not reach its calendar mapping")
                unlinking = pool.submit(unlink_child)
                # The surviving parent is authorized, but unlink must not
                # wait on a cascade while holding that child's User lock.
                status, _body = unlinking.result(timeout=3)
                self.assertEqual(status, 409)
            finally:
                release_deletion.set()
            deleting.result(timeout=15)

        self.assertFalse(User.objects.filter(pk=self.child.pk).exists())
        self.assertFalse(GoogleAccount.objects.filter(google_id=GOOGLE_ID).exists())
        self.assertFalse(CalendarEventMapping.objects.filter(user_id=self.child.pk).exists())
        self.assertTrue(Token.objects.filter(key=self.token.key, user=self.parent).exists())

    def test_logout_releases_user_before_waiting_for_actual_account_token_deletion(self):
        token_deleted, release_deletion, waiting_for_token = Event(), Event(), Event()

        def delete_account():
            self._thread_connection("delete-logout-account")
            try:
                def hold_after_token_delete(execute, sql, params, many, context):
                    result = execute(sql, params, many, context)
                    if sql.lstrip().upper().startswith("DELETE FROM") and '"authtoken_token"' in sql:
                        token_deleted.set()
                        if not release_deletion.wait(10):
                            raise TimeoutError("Account token cascade was not released")
                    return result

                with connection.execute_wrapper(hold_after_token_delete):
                    User.objects.get(pk=self.parent.pk).delete()
            finally:
                connection.close()
                _worker.label = None

        def logout():
            self._thread_connection("logout")
            try:
                def observe_blocking_token_wait(execute, sql, params, many, context):
                    if ('"authtoken_token"' in sql and "FOR UPDATE" in sql.upper()
                            and "NOWAIT" not in sql.upper()):
                        waiting_for_token.set()
                    return execute(sql, params, many, context)

                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
                with connection.execute_wrapper(observe_blocking_token_wait):
                    response = client.post("/api/auth/", {"action": "logout"}, format="json")
                return response.status_code, response.data
            finally:
                connection.close()
                _worker.label = None

        with ThreadPoolExecutor(max_workers=2) as pool:
            deleting = pool.submit(delete_account)
            try:
                self.assertTrue(token_deleted.wait(5), "Real account deletion did not reach its token")
                logging_out = pool.submit(logout)
                self.assertTrue(waiting_for_token.wait(5), "Logout did not wait for the existing token operation")
                self.assertFalse(logging_out.done())
                # A blocking Token wait is safe only after releasing User:
                # the paused account cascade must still be able to delete it.
                with transaction.atomic():
                    self.assertTrue(User.objects.select_for_update(no_key=True, nowait=True).filter(
                        pk=self.parent.pk,
                    ).exists())
            finally:
                release_deletion.set()
            deleting.result(timeout=3)
            status, body = logging_out.result(timeout=3)

        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})
        self.assertFalse(User.objects.filter(pk=self.parent.pk).exists())
        self.assertFalse(Token.objects.filter(user_id=self.parent.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.child.pk).exists())
