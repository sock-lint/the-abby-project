"""Tests for the DRF-token-to-MCP-context auth middleware."""
from __future__ import annotations

from django.test import TestCase
from rest_framework.authtoken.models import Token

from apps.mcp_server.auth import _parse_token_header, _resolve_user
from apps.mcp_server.context import get_current_user, override_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.accounts.models import User


class ParseTokenHeaderTests(TestCase):
    def test_strips_token_prefix(self) -> None:
        self.assertEqual(_parse_token_header("Token abc123"), "abc123")

    def test_case_insensitive_scheme(self) -> None:
        self.assertEqual(_parse_token_header("token abc123"), "abc123")
        self.assertEqual(_parse_token_header("TOKEN abc123"), "abc123")

    def test_rejects_bearer_scheme(self) -> None:
        self.assertIsNone(_parse_token_header("Bearer abc123"))

    def test_rejects_missing_key(self) -> None:
        self.assertIsNone(_parse_token_header("Token"))
        self.assertIsNone(_parse_token_header(""))
        self.assertIsNone(_parse_token_header(None))


class ResolveUserTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="abby", password="pw", role="child",
        )
        self.token = Token.objects.create(user=self.user)

    def test_resolves_valid_token(self) -> None:
        self.assertEqual(_resolve_user(self.token.key), self.user)

    def test_returns_none_for_unknown_token(self) -> None:
        self.assertIsNone(_resolve_user("not-a-real-token"))

    def test_rejects_inactive_user(self) -> None:
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(_resolve_user(self.token.key))


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
