"""Tests for AuthView — login, logout, token rotation, throttling.

Audit C5 + H2: prior version had no throttle on login (unlimited
brute-force per IP) and never rotated the auth token (one leak = permanent
backdoor). Both are pinned here.
"""
from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.projects.models import User


class _AuthFixture(TestCase):
    def setUp(self):
        # ScopedRateThrottle keeps its counters in the default cache
        # (LocMemCache in tests). Wipe between tests so one test's hammered
        # bucket doesn't poison the next.
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="parent", password="correct-horse-battery-staple",
            role="parent",
        )


class LoginSuccessTests(_AuthFixture):
    def test_valid_credentials_return_token_and_user(self):
        resp = self.client.post(
            "/api/auth/",
            {"action": "login", "username": "parent", "password": "correct-horse-battery-staple"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("token", body)
        self.assertEqual(body["username"], "parent")
        self.assertEqual(body["role"], "parent")
        # Token actually persists.
        self.assertTrue(Token.objects.filter(user=self.user, key=body["token"]).exists())


class LoginFailureTests(_AuthFixture):
    def test_unknown_user_returns_401(self):
        resp = self.client.post(
            "/api/auth/",
            {"action": "login", "username": "ghost", "password": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid credentials", resp.json()["error"])

    def test_wrong_password_returns_401(self):
        resp = self.client.post(
            "/api/auth/",
            {"action": "login", "username": "parent", "password": "wrong"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        # No token gets minted on failed login.
        self.assertFalse(Token.objects.filter(user=self.user).exists())


class LoginTokenRotationTests(_AuthFixture):
    """Audit H2: every successful login mints a fresh token and revokes any
    prior one. Pre-fix, ``Token.objects.get_or_create`` returned the same
    key forever — once leaked, no rotation path.
    """

    def test_second_login_returns_different_token(self):
        first = self.client.post(
            "/api/auth/",
            {"action": "login", "username": "parent", "password": "correct-horse-battery-staple"},
            format="json",
        ).json()["token"]
        second = self.client.post(
            "/api/auth/",
            {"action": "login", "username": "parent", "password": "correct-horse-battery-staple"},
            format="json",
        ).json()["token"]

        self.assertNotEqual(first, second)

    def test_old_token_is_invalidated_after_relogin(self):
        first = self.client.post(
            "/api/auth/",
            {"action": "login", "username": "parent", "password": "correct-horse-battery-staple"},
            format="json",
        ).json()["token"]

        # Re-login → first token is revoked, replaced by a new one.
        second = self.client.post(
            "/api/auth/",
            {"action": "login", "username": "parent", "password": "correct-horse-battery-staple"},
            format="json",
        ).json()["token"]

        self.assertFalse(Token.objects.filter(key=first).exists())
        self.assertTrue(Token.objects.filter(key=second).exists())

    def test_only_one_token_per_user_after_rotation(self):
        for _ in range(3):
            self.client.post(
                "/api/auth/",
                {"action": "login", "username": "parent", "password": "correct-horse-battery-staple"},
                format="json",
            )
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)


class LogoutTests(_AuthFixture):
    def test_logout_deletes_token(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        resp = self.client.post(
            "/api/auth/", {"action": "logout"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_unauthenticated_logout_is_noop(self):
        resp = self.client.post(
            "/api/auth/", {"action": "logout"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})


class UnknownActionTests(_AuthFixture):
    def test_returns_400(self):
        resp = self.client.post("/api/auth/", {"action": "fly"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid action", resp.json()["error"])

    def test_missing_action_returns_400(self):
        resp = self.client.post("/api/auth/", {}, format="json")
        self.assertEqual(resp.status_code, 400)


class LoginThrottleTests(_AuthFixture):
    """Audit C5: ``AuthView`` is throttled. Pre-fix it had no throttle and
    a bot could grind unlimited credential guesses against a known
    username from a single IP.

    Tests use the production rate (10/min) directly rather than via
    ``@override_settings(REST_FRAMEWORK=…)`` because DRF's ``api_settings``
    cache doesn't reliably reload on per-test overrides — override-based
    tests pass on isolated runs but flake when run alongside other tests
    that touch DRF settings. Firing 11 requests is cheap (no DB hit on
    failed-auth path) and pins the actual production behaviour.
    """

    def _login(self, password="wrong"):
        return self.client.post(
            "/api/auth/",
            {"action": "login", "username": "parent", "password": password},
            format="json",
        )

    def test_throttle_returns_429_after_rate_exhausted(self):
        # First 10 attempts pass the throttle (and 401 for wrong password).
        for i in range(10):
            resp = self._login()
            self.assertEqual(
                resp.status_code, 401,
                f"Attempt {i + 1} returned {resp.status_code}, expected 401",
            )
        # 11th attempt is throttled.
        resp = self._login()
        self.assertEqual(resp.status_code, 429)

    def test_successful_logins_also_count_toward_throttle(self):
        # Documented behaviour — the throttle is per-endpoint, not per-
        # outcome. Pin so a future refactor that splits success/failure
        # buckets makes a deliberate choice.
        for _ in range(10):
            resp = self._login(password="correct-horse-battery-staple")
            self.assertEqual(resp.status_code, 200)
        resp = self._login(password="correct-horse-battery-staple")
        self.assertEqual(resp.status_code, 429)
