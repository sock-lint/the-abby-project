"""Tests for the OAuth 2.1 Bearer-token MCP auth middleware.

The internal API exposed for unit-testing:
* ``_parse_bearer_header(value)`` → ``(scheme, key)`` tuple, ``(None, None)`` on garbage.
* ``_resolve_user(token_key)`` → ``User`` for a live ``AccessToken``, else ``None``.

End-to-end Starlette dispatch is exercised in ``config/tests/test_oauth.py::MCPBearerAuthTests``.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.mcp_server.auth import _parse_bearer_header, _resolve_user
from apps.mcp_server.context import get_current_user, override_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.accounts.models import User
from config.tests.factories import make_oauth_token


class ParseBearerHeaderTests(TestCase):
    def test_splits_bearer_scheme(self) -> None:
        scheme, key = _parse_bearer_header("Bearer abc123")
        self.assertEqual(scheme, "bearer")
        self.assertEqual(key, "abc123")

    def test_case_insensitive_scheme(self) -> None:
        self.assertEqual(_parse_bearer_header("bearer abc123")[0], "bearer")
        self.assertEqual(_parse_bearer_header("BEARER abc123")[0], "bearer")

    def test_surfaces_legacy_token_scheme(self) -> None:
        """The middleware needs to see ``token`` separately so it can render a
        migration hint instead of a generic 'malformed header'."""
        scheme, key = _parse_bearer_header("Token abc123")
        self.assertEqual(scheme, "token")
        self.assertEqual(key, "abc123")

    def test_rejects_missing_key(self) -> None:
        self.assertEqual(_parse_bearer_header("Bearer"), (None, None))
        self.assertEqual(_parse_bearer_header(""), (None, None))
        self.assertEqual(_parse_bearer_header(None), (None, None))


@override_settings(MCP_RESOURCE_URL="https://example.test/mcp")
class ResolveUserTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="abby", password="pw", role="parent", is_staff=True,
        )
        self.access, header = make_oauth_token(self.user)
        # Strip the "Bearer " prefix to get the raw token value.
        self.token_value = header.removeprefix("Bearer ")

    def test_resolves_valid_token(self) -> None:
        self.assertEqual(_resolve_user(self.token_value), self.user)

    def test_returns_none_for_unknown_token(self) -> None:
        self.assertIsNone(_resolve_user("not-a-real-token"))

    def test_rejects_inactive_user(self) -> None:
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(_resolve_user(self.token_value))

    def test_rejects_expired_token(self) -> None:
        self.access.expires = timezone.now() - timedelta(seconds=60)
        self.access.save(update_fields=["expires"])
        self.assertIsNone(_resolve_user(self.token_value))

    def test_rejects_wrong_resource_claim(self) -> None:
        from apps.mcp_server.models import MCPTokenResource
        MCPTokenResource.objects.update_or_create(
            access_token=self.access,
            defaults={"resource": "https://attacker.example/mcp"},
        )
        # Drop the cached reverse-1-1 so the next lookup re-reads.
        self.access.refresh_from_db()
        self.assertIsNone(_resolve_user(self.token_value))


class ContextTests(TestCase):
    def test_get_current_user_without_context_raises(self) -> None:
        with self.assertRaises(MCPPermissionDenied):
            get_current_user()

    def test_override_user_sets_and_resets(self) -> None:
        user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        with override_user(user):
            self.assertEqual(get_current_user(), user)
        with self.assertRaises(MCPPermissionDenied):
            get_current_user()
