"""Tests for GoogleAuthService encryption and account lifecycle."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.google_integration.models import CalendarEventMapping, GoogleAccount
from apps.google_integration.services import (
    GoogleAuthService,
    _decrypt,
    _encrypt,
)
from apps.projects.models import User


class EncryptionTests(TestCase):
    def test_round_trip(self):
        plaintext = b'{"token": "abc", "refresh_token": "xyz"}'
        cipher = _encrypt(plaintext)
        self.assertNotEqual(cipher, plaintext)
        self.assertTrue(len(cipher) >= len(plaintext) + 48)  # salt + hmac
        self.assertEqual(_decrypt(cipher), plaintext)

    def test_tamper_detection(self):
        cipher = bytearray(_encrypt(b"secret"))
        cipher[20] ^= 0xFF  # flip a ciphertext byte
        with self.assertRaises(ValueError):
            _decrypt(bytes(cipher))

    def test_too_short_raises(self):
        with self.assertRaises(ValueError):
            _decrypt(b"tiny")

    def test_each_encryption_unique(self):
        """Different salt each time → different ciphertext."""
        c1 = _encrypt(b"same-input")
        c2 = _encrypt(b"same-input")
        self.assertNotEqual(c1, c2)

    def test_credentials_json_round_trip(self):
        creds = {
            "token": "t", "refresh_token": "r",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": ["openid", "email"],
        }
        cipher = GoogleAuthService.encrypt_credentials(creds)
        self.assertEqual(GoogleAuthService.decrypt_credentials(cipher), creds)


class IsConfiguredTests(TestCase):
    @override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
    def test_unconfigured(self):
        self.assertFalse(GoogleAuthService.is_configured())

    @override_settings(GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="csec")
    def test_configured(self):
        self.assertTrue(GoogleAuthService.is_configured())


class LinkAccountTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")

    def test_link_creates_account(self):
        account = GoogleAuthService.link_account(
            self.parent, "google-abc", "p@x.com",
            {"token": "t", "refresh_token": "r"},
        )
        self.assertEqual(account.user, self.parent)
        self.assertEqual(account.google_id, "google-abc")
        self.assertEqual(account.google_email, "p@x.com")
        # encrypted_credentials is bytes and decrypts back to the input.
        creds = GoogleAuthService.decrypt_credentials(account.encrypted_credentials)
        self.assertEqual(creds["token"], "t")

    def test_link_with_parent_attribution(self):
        account = GoogleAuthService.link_account(
            self.child, "child-g", "c@x.com",
            {"token": "t"}, linked_by=self.parent,
        )
        self.assertEqual(account.linked_by, self.parent)

    def test_relinking_updates_existing(self):
        first = GoogleAuthService.link_account(
            self.parent, "g1", "old@x.com", {"token": "t1"},
        )
        second = GoogleAuthService.link_account(
            self.parent, "g2", "new@x.com", {"token": "t2"},
        )
        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.google_email, "new@x.com")
        self.assertEqual(GoogleAccount.objects.count(), 1)


class UnlinkAccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="pw", role="parent")

    def test_unlink_removes_account_and_mappings(self):
        GoogleAuthService.link_account(self.user, "g", "u@x.com", {"token": "t"})
        CalendarEventMapping.objects.create(
            user=self.user, content_type="chore", object_id=1, google_event_id="ev",
        )

        GoogleAuthService.unlink_account(self.user)

        self.assertFalse(GoogleAccount.objects.filter(user=self.user).exists())
        self.assertFalse(CalendarEventMapping.objects.filter(user=self.user).exists())

    def test_unlink_is_idempotent(self):
        """Calling unlink on a user who never linked should not raise."""
        GoogleAuthService.unlink_account(self.user)  # no-op
        GoogleAuthService.unlink_account(self.user)  # no-op
        self.assertFalse(GoogleAccount.objects.filter(user=self.user).exists())


class GetGoogleCredentialsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="pw", role="parent")
        self.account = GoogleAuthService.link_account(
            self.user, "g", "u@x.com",
            {
                "token": "access-token",
                "refresh_token": "refresh-token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "cid",
                "client_secret": "csec",
                "scopes": ["openid"],
                "expiry": "2030-01-01T00:00:00",
            },
        )

    def test_builds_credentials_with_all_fields(self):
        creds = GoogleAuthService.get_google_credentials(self.account)
        self.assertEqual(creds.token, "access-token")
        self.assertEqual(creds.refresh_token, "refresh-token")
        self.assertIsNotNone(creds.expiry)


class RefreshIfNeededTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="pw", role="parent")
        self.account = GoogleAuthService.link_account(
            self.user, "g", "u@x.com",
            {"token": "old", "refresh_token": "refresh", "expiry": "2000-01-01T00:00:00"},
        )

    @patch("apps.google_integration.services.GoogleAuthService.get_google_credentials")
    def test_refreshes_when_expired(self, mock_get):
        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh"
        mock_creds.token = "new-token"
        mock_creds.expiry = None
        mock_get.return_value = mock_creds

        with patch("google.auth.transport.requests.Request"):
            GoogleAuthService.refresh_if_needed(self.account)

        # Token was refreshed and re-encrypted.
        self.account.refresh_from_db()
        creds = GoogleAuthService.decrypt_credentials(self.account.encrypted_credentials)
        self.assertEqual(creds["token"], "new-token")

    @patch("apps.google_integration.services.GoogleAuthService.get_google_credentials")
    def test_no_refresh_when_fresh(self, mock_get):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_get.return_value = mock_creds

        GoogleAuthService.refresh_if_needed(self.account)

        # Token unchanged.
        self.account.refresh_from_db()
        creds = GoogleAuthService.decrypt_credentials(self.account.encrypted_credentials)
        self.assertEqual(creds["token"], "old")
