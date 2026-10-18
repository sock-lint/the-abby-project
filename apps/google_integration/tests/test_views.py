"""Tests for google_integration views — OAuth flow + calendar settings.

Mocks the Google OAuth SDK because hitting real Google servers from tests
would be fragile and slow. Focus is on our glue logic: state handling, user
resolution, the proof-bound return contract, and permission gating.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.google_integration.models import GoogleAccount
from apps.google_integration.services import GoogleAuthService
from apps.google_integration.tests.test_oauth_exchange import VERIFIER, challenge, provider_authorization
from config.tests.factories import make_family


@override_settings(
    GOOGLE_CLIENT_ID="test-client-id",
    GOOGLE_CLIENT_SECRET="test-secret",
    GOOGLE_REDIRECT_URI="http://testserver/api/auth/google/callback/",
    FRONTEND_URL="http://testserver",
)
class _Fixture(TestCase):
    def setUp(self):
        family = make_family("Google view family", parents=[{"username": "parent"}], children=[{"username": "child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.token = Token.objects.create(user=self.parent)
        self.client = APIClient()
        cache.clear()

    def start_child_link(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        with patch.object(GoogleAuthService, "get_authorization_url", side_effect=provider_authorization):
            response = self.client.get("/api/auth/google/", {"for_user": self.child.pk, "code_challenge": challenge(), "code_challenge_method": "S256"})
        self.assertEqual(response.status_code, 200)
        return response.json()["state"]


class AuthInitViewTests(_Fixture):
    @patch("apps.google_integration.services.GoogleAuthService.get_authorization_url")
    def test_returns_auth_url(self, mock_get_url):
        mock_get_url.return_value = ("https://accounts.google.com/o/oauth2/auth?x=1", "state-abc", "verifier")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        resp = self.client.get("/api/auth/google/", {"code_challenge": challenge(), "code_challenge_method": "S256"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("authorization_url", resp.json())

    def test_unauthenticated_forbidden(self):
        resp = self.client.get("/api/auth/google/")
        self.assertEqual(resp.status_code, 401)


class CallbackLinkTests(_Fixture):
    @patch("apps.google_integration.services.GoogleAuthService.exchange_code")
    def test_link_with_missing_initiating_parent_is_refused(self, mock_exchange):
        """An old Google navigation cannot retain a deleted parent's authority."""
        mock_exchange.return_value = ("google-123", "child@example.com", {"token": "t"})
        state = self.start_child_link()
        self.parent.delete()
        resp = APIClient().get("/api/auth/google/callback/", {"code": "c", "state": state})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(GoogleAccount.objects.filter(user=self.child).exists())
        self.assertIn("google_error", parse_qs(urlsplit(resp.url).fragment))
        mock_exchange.assert_not_called()

    @patch("apps.google_integration.services.GoogleAuthService.exchange_code")
    def test_link_with_valid_linked_by(self, mock_exchange):
        mock_exchange.return_value = ("google-456", "c@example.com", {"token": "t"})

        state = self.start_child_link()
        resp = APIClient().get("/api/auth/google/callback/", {"code": "c", "state": state})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(GoogleAccount.objects.filter(user=self.child).exists())
        ticket = parse_qs(urlsplit(resp.url).fragment)["google_exchange"][0]
        exchanged = self.client.post("/api/auth/google/exchange/", {"exchange_code": ticket, "code_verifier": VERIFIER}, format="json")
        self.assertEqual(exchanged.status_code, 200)
        account = GoogleAccount.objects.get(user=self.child)
        self.assertEqual(account.linked_by, self.parent)

    def test_callback_with_missing_state_errors(self):
        resp = self.client.get("/api/auth/google/callback/?code=c&state=does-not-exist")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error", resp.url)


class GoogleAccountViewTests(_Fixture):
    def test_get_account_returns_linked_state(self):
        GoogleAuthService.link_account(self.parent, "g", "p@x.com", {"token": "t"})
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/auth/google/account/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["linked"])
        self.assertEqual(body["google_email"], "p@x.com")

    def test_get_account_unlinked(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/auth/google/account/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["linked"])

    def test_delete_unlinks(self):
        GoogleAuthService.link_account(self.parent, "g", "p@x.com", {"token": "t"})
        self.client.force_authenticate(self.parent)
        resp = self.client.delete("/api/auth/google/account/")
        self.assertIn(resp.status_code, (200, 204))
        self.assertFalse(GoogleAccount.objects.filter(user=self.parent).exists())


class CalendarSettingsViewTests(_Fixture):
    def test_toggle_sync_enabled(self):
        GoogleAuthService.link_account(self.parent, "g", "p@x.com", {"token": "t"})
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(
            "/api/auth/google/calendar/",
            {"calendar_sync_enabled": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        account = GoogleAccount.objects.get(user=self.parent)
        self.assertTrue(account.calendar_sync_enabled)

    def test_settings_without_account_errors(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(
            "/api/auth/google/calendar/",
            {"calendar_sync_enabled": True},
            format="json",
        )
        self.assertIn(resp.status_code, (400, 404))
