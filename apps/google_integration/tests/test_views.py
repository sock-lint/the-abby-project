"""Tests for google_integration views — OAuth flow + calendar settings.

Mocks the Google OAuth SDK because hitting real Google servers from tests
would be fragile and slow. Focus is on our glue logic: state handling, user
resolution, error paths (including the logger.warning we added in PR #1),
and permission gating.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.google_integration.models import GoogleAccount
from apps.google_integration.services import GoogleAuthService
from apps.projects.models import User


@override_settings(
    GOOGLE_CLIENT_ID="test-client-id",
    GOOGLE_CLIENT_SECRET="test-secret",
    GOOGLE_REDIRECT_URI="http://testserver/api/auth/google/callback/",
    FRONTEND_URL="http://testserver",
)
class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="child", password="pw", role="child")
        self.client = APIClient()
        cache.clear()


class AuthInitViewTests(_Fixture):
    @patch("apps.google_integration.services.GoogleAuthService.get_authorization_url")
    def test_returns_auth_url(self, mock_get_url):
        mock_get_url.return_value = ("https://accounts.google.com/o/oauth2/auth?x=1", "state-abc", "verifier")
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/auth/google/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("authorization_url", resp.json())

    def test_unauthenticated_forbidden(self):
        resp = self.client.get("/api/auth/google/")
        self.assertEqual(resp.status_code, 401)


class CallbackLinkTests(_Fixture):
    @patch("apps.google_integration.services.GoogleAuthService.exchange_code")
    def test_link_with_missing_linked_by_logs_warning(self, mock_exchange):
        """The pass-stub fix from PR #1: missing parent ID should log a warning, not silently drop."""
        mock_exchange.return_value = ("google-123", "child@example.com", {"token": "t"})

        # Stash a state that claims an invalid linked_by_id
        cache.set(
            "google_oauth_state:state-x",
            {
                "mode": "link",
                "target_user_id": self.child.pk,
                "linked_by_id": 99999,  # invalid
                "code_verifier": "v",
            },
            timeout=300,
        )

        with self.assertLogs("apps.google_integration.views", level="WARNING") as cm:
            resp = self.client.get("/api/auth/google/callback/?code=c&state=state-x")

        self.assertEqual(resp.status_code, 302)
        # Account was still linked (graceful degradation).
        self.assertTrue(GoogleAccount.objects.filter(user=self.child).exists())
        # But a warning was logged with the bogus ID.
        joined = "\n".join(cm.output)
        self.assertIn("99999", joined)
        self.assertIn("linked_by", joined)

    @patch("apps.google_integration.services.GoogleAuthService.exchange_code")
    def test_link_with_valid_linked_by(self, mock_exchange):
        mock_exchange.return_value = ("google-456", "c@example.com", {"token": "t"})

        cache.set(
            "google_oauth_state:state-ok",
            {
                "mode": "link",
                "target_user_id": self.child.pk,
                "linked_by_id": self.parent.pk,
                "code_verifier": "v",
            },
            timeout=300,
        )

        resp = self.client.get("/api/auth/google/callback/?code=c&state=state-ok")
        self.assertEqual(resp.status_code, 302)
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
