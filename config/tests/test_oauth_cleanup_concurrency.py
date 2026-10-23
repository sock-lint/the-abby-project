"""Client cleanup and OAuth issuance share the registration's PostgreSQL lock."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.db import close_old_connections, connection, connections
from django.test import Client, TransactionTestCase, override_settings
from oauth2_provider.models import AccessToken, Application, Grant
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError, InvalidRequestError
from rest_framework.test import APIClient

from apps.mcp_server.models import MCPAuthorizationResource, MCPTokenResource
from config.oauth_validator import AbbyOAuth2Validator
from config.tests.factories import make_family


class OAuthCleanupFixtures:
    def setUp(self):
        self.user = make_family(parents=[{
            "username": "cleanup-race-staff", "is_staff": True,
        }]).parents[0]
        self.app = Application.objects.create(
            name="Synthetic consent client", client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://localhost:7331/callback", client_secret="",
        )

    def request(self):
        return SimpleNamespace(
            client=Application.objects.get(pk=self.app.pk), user=self.user,
            resource=["https://example.test/mcp"], redirect_uri=self.app.redirect_uris,
            scopes=["mcp:read"], code_challenge="synthetic-challenge",
            code_challenge_method="S256", nonce=None, claims=None,
            grant_type="authorization_code", code="synthetic-consent-code",
            abby_mcp_resource="https://example.test/mcp",
        )


@override_settings(SITE_URL="https://example.test", MCP_RESOURCE_URL="https://example.test/mcp")
class OAuthCleanupStaleClientTests(OAuthCleanupFixtures, TransactionTestCase):
    def test_removed_cached_client_cannot_save_authorization_code(self):
        request = self.request()
        client_id = self.app.client_id
        self.app.delete()
        with self.assertRaises(InvalidRequestError):
            AbbyOAuth2Validator().save_authorization_code(
                client_id, {"code": request.code}, request,
            )
        self.assertFalse(Grant.objects.exists())
        self.assertFalse(MCPAuthorizationResource.objects.exists())

    def test_removed_cached_client_cannot_save_bearer_token(self):
        request = self.request()
        self.app.delete()
        with self.assertRaises(InvalidGrantError):
            # This is DOT's public entry point, which provides its transaction.
            AbbyOAuth2Validator().save_bearer_token({
                "access_token": "synthetic-cleanup-access", "scope": "mcp:read",
                "token_type": "Bearer", "expires_in": 3600,
            }, request)
        self.assertFalse(AccessToken.objects.exists())
        self.assertFalse(MCPTokenResource.objects.exists())


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks required")
@override_settings(SITE_URL="https://example.test", MCP_RESOURCE_URL="https://example.test/mcp")
class OAuthCleanupConcurrencyTests(OAuthCleanupFixtures, TransactionTestCase):
    def consent(self):
        client = Client()
        client.force_login(self.user)
        return client.post("/oauth/authorize/", {
            "client_id": self.app.client_id, "redirect_uri": self.app.redirect_uris,
            "response_type": "code", "scope": "mcp:read", "state": "synthetic-state",
            "code_challenge": "synthetic-challenge", "code_challenge_method": "S256",
            "resource": "https://example.test/mcp", "allow": "Authorize",
        })

    def cleanup(self):
        client = APIClient()
        client.force_authenticate(self.user)
        return client.delete(f"/api/admin/oauth/applications/{self.app.client_id}/")

    def worker(self, operation, pids, key):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids[key] = cursor.fetchone()[0]
            return operation()
        finally:
            connections.close_all()

    def assert_waiting_on(self, future, pids, waiter, holder):
        deadline = monotonic() + 4
        while monotonic() < deadline and not future.done():
            if waiter in pids:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))",
                                   [pids[holder], pids[waiter]])
                    if cursor.fetchone()[0]:
                        return
            sleep(0.01)
        self.fail(f"{waiter} did not wait for {holder}'s registration lock")

    def test_consent_committing_first_makes_cleanup_refuse(self):
        entered, release, pids = Event(), Event(), {}
        save = OAuth2Validator.save_authorization_code

        def paused_save(validator, *args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise AssertionError("Consent test release timed out")
            return save(validator, *args, **kwargs)

        with patch.object(OAuth2Validator, "save_authorization_code", paused_save):
            with ThreadPoolExecutor(max_workers=2) as executor:
                consent = executor.submit(self.worker, self.consent, pids, "consent")
                try:
                    self.assertTrue(entered.wait(10), "Consent did not reach grant issuance")
                    cleanup = executor.submit(self.worker, self.cleanup, pids, "cleanup")
                    self.assert_waiting_on(cleanup, pids, "cleanup", "consent")
                finally:
                    release.set()
                consent_response = consent.result(timeout=15)
                cleanup_response = cleanup.result(timeout=15)
        self.assertEqual(consent_response.status_code, 302)
        self.assertIn("code", parse_qs(urlparse(consent_response.url).query))
        self.assertEqual(cleanup_response.status_code, 409, cleanup_response.content)
        self.assertTrue(Application.objects.filter(pk=self.app.pk).exists())
        self.assertEqual(Grant.objects.filter(application=self.app).count(), 1)
        self.assertEqual(MCPAuthorizationResource.objects.count(), 1)

    def test_cleanup_committing_first_returns_oauth_error_to_inflight_consent(self):
        entered, release, validated, pids = Event(), Event(), Event(), {}
        delete = Application.delete
        save = AbbyOAuth2Validator.save_authorization_code

        def paused_delete(application, *args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise AssertionError("Cleanup test release timed out")
            return delete(application, *args, **kwargs)

        def validated_save(validator, *args, **kwargs):
            validated.set()
            return save(validator, *args, **kwargs)

        with patch.object(Application, "delete", paused_delete), patch.object(
            AbbyOAuth2Validator, "save_authorization_code", validated_save,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                cleanup = executor.submit(self.worker, self.cleanup, pids, "cleanup")
                try:
                    self.assertTrue(entered.wait(10), "Cleanup did not reach deletion")
                    consent = executor.submit(self.worker, self.consent, pids, "consent")
                    self.assertTrue(validated.wait(10), "Consent did not validate its client")
                    self.assert_waiting_on(consent, pids, "consent", "cleanup")
                finally:
                    release.set()
                cleanup_response = cleanup.result(timeout=15)
                consent_response = consent.result(timeout=15)
        self.assertEqual(cleanup_response.status_code, 200, cleanup_response.content)
        self.assertEqual(consent_response.status_code, 302, consent_response.content)
        error = parse_qs(urlparse(consent_response.url).query)
        self.assertEqual(error["error"], ["invalid_request"])
        self.assertEqual(error["state"], ["synthetic-state"])
        self.assertFalse(Application.objects.filter(pk=self.app.pk).exists())
        self.assertFalse(Grant.objects.exists())
        self.assertFalse(MCPAuthorizationResource.objects.exists())
