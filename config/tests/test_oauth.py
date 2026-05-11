"""Tests for the MCP-spec OAuth 2.1 surface.

Three groups:

* **Discovery shape** — /.well-known/oauth-protected-resource (RFC 9728) +
  /.well-known/oauth-authorization-server (RFC 8414) return well-formed
  JSON the MCP client can probe before sending an Authorization header.
* **End-to-end PKCE flow** — exercises DCR → authorize → token exchange →
  Bearer auth against the MCP middleware → refresh.
* **Negatives** — non-staff parent + child blocked at consent, expired /
  revoked / wrong-resource tokens rejected at MCP, legacy Token-style
  header gets a 401 with a discovery hint.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config.tests.factories import make_family, make_oauth_token


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256-challenge) for an end-to-end PKCE test."""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@override_settings(SITE_URL="https://example.test", MCP_RESOURCE_URL="https://example.test/mcp")
class WellKnownDiscoveryTests(TestCase):
    def test_protected_resource_metadata(self):
        resp = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["resource"], "https://example.test/mcp")
        self.assertEqual(body["authorization_servers"], ["https://example.test"])
        self.assertIn("header", body["bearer_methods_supported"])
        self.assertIn("mcp", body["scopes_supported"])

    def test_protected_resource_is_cacheable(self):
        resp = self.client.get("/.well-known/oauth-protected-resource")
        self.assertIn("max-age=3600", resp.get("Cache-Control", ""))

    def test_authorization_server_metadata(self):
        resp = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["issuer"], "https://example.test")
        self.assertEqual(body["authorization_endpoint"], "https://example.test/oauth/authorize/")
        self.assertEqual(body["token_endpoint"], "https://example.test/oauth/token/")
        self.assertEqual(body["registration_endpoint"], "https://example.test/oauth/register/")
        self.assertEqual(body["response_types_supported"], ["code"])
        self.assertIn("authorization_code", body["grant_types_supported"])
        self.assertIn("refresh_token", body["grant_types_supported"])
        self.assertEqual(body["code_challenge_methods_supported"], ["S256"])
        self.assertEqual(body["token_endpoint_auth_methods_supported"], ["none"])


# ---------------------------------------------------------------------------
# Dynamic Client Registration (RFC 7591)
# ---------------------------------------------------------------------------


class DynamicClientRegistrationTests(TestCase):
    def test_register_creates_public_client(self):
        resp = self.client.post(
            "/oauth/register/",
            data=json.dumps({
                "client_name": "Cowork",
                "redirect_uris": ["http://localhost:7331/callback"],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("client_id", body)
        self.assertEqual(body["client_name"], "Cowork")
        self.assertEqual(body["token_endpoint_auth_method"], "none")
        self.assertIn("authorization_code", body["grant_types"])

        # Application was actually created as public + auth-code-grant.
        # (DOT hashes ``client_secret`` on save, so asserting on the literal
        # empty string would fail — what matters is ``client_type=public``,
        # which is what ``client_authentication_required`` keys off.)
        from oauth2_provider.models import Application
        app = Application.objects.get(client_id=body["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_PUBLIC)
        self.assertEqual(app.authorization_grant_type, Application.GRANT_AUTHORIZATION_CODE)

    def test_register_rejects_missing_redirect_uris(self):
        resp = self.client.post(
            "/oauth/register/",
            data=json.dumps({"client_name": "Bad"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_redirect_uri")

    def test_register_rejects_unsupported_scheme(self):
        resp = self.client.post(
            "/oauth/register/",
            data=json.dumps({
                "client_name": "Phisher",
                "redirect_uris": ["javascript:alert(1)"],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_redirect_uri")


# ---------------------------------------------------------------------------
# Authorize view — staff-parent gate + end-to-end PKCE
# ---------------------------------------------------------------------------


@override_settings(SITE_URL="https://example.test", MCP_RESOURCE_URL="https://example.test/mcp")
class AuthorizeGateTests(TestCase):
    def setUp(self):
        # Three accounts: a staff parent (the only one allowed to grant),
        # a non-staff parent (rejected), and a child (rejected).
        fam = make_family(
            parents=[
                {"username": "staff_parent", "is_staff": True},
                {"username": "regular_parent", "is_staff": False},
            ],
            children=[{"username": "kid"}],
        )
        self.staff_parent = fam.parents[0]
        self.regular_parent = fam.parents[1]
        self.kid = fam.children[0]

        from oauth2_provider.models import Application
        self.app = Application.objects.create(
            name="Cowork",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://localhost:7331/callback",
            client_secret="",
            skip_authorization=False,
        )

    def _authorize_url(self, **extra):
        from urllib.parse import urlencode
        params = {
            "response_type": "code",
            "client_id": self.app.client_id,
            "redirect_uri": "http://localhost:7331/callback",
            "scope": "mcp",
            "state": "xyz",
            "code_challenge": "abc",
            "code_challenge_method": "S256",
        }
        params.update(extra)
        return f"/oauth/authorize/?{urlencode(params)}"

    def test_unauthenticated_bounces_to_oauth_login(self):
        resp = self.client.get(self._authorize_url())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith("/oauth/login/"))

    def test_regular_parent_is_rejected(self):
        self.client.force_login(self.regular_parent)
        resp = self.client.get(self._authorize_url())
        self.assertEqual(resp.status_code, 403)

    def test_child_is_rejected(self):
        self.client.force_login(self.kid)
        resp = self.client.get(self._authorize_url())
        self.assertEqual(resp.status_code, 403)

    def test_staff_parent_sees_consent_screen(self):
        self.client.force_login(self.staff_parent)
        resp = self.client.get(self._authorize_url())
        self.assertEqual(resp.status_code, 200)
        # The custom template renders the application name.
        self.assertContains(resp, "Cowork")


@override_settings(SITE_URL="https://example.test", MCP_RESOURCE_URL="https://example.test/mcp")
class EndToEndPKCEFlowTests(TestCase):
    def setUp(self):
        fam = make_family(parents=[{"username": "staff_parent", "is_staff": True}])
        self.staff_parent = fam.parents[0]
        # Register a client via DCR.
        resp = self.client.post(
            "/oauth/register/",
            data=json.dumps({
                "client_name": "Cowork",
                "redirect_uris": ["http://localhost:7331/callback"],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.client_id = resp.json()["client_id"]

    def test_full_authorization_code_with_pkce(self):
        verifier, challenge = _pkce_pair()
        # Sign in as the staff parent (session auth).
        self.client.force_login(self.staff_parent)

        # POST the consent form to /oauth/authorize/ with allow=Authorize.
        post_data = {
            "client_id": self.client_id,
            "redirect_uri": "http://localhost:7331/callback",
            "response_type": "code",
            "scope": "mcp",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": "https://example.test/mcp",
            "allow": "Authorize",
        }
        resp = self.client.post("/oauth/authorize/", data=post_data)
        # DOT redirects with the code.
        self.assertIn(resp.status_code, (302, 303))
        parsed = urlparse(resp.url)
        qs = parse_qs(parsed.query)
        self.assertIn("code", qs, f"no code in redirect: {resp.url}")
        code = qs["code"][0]

        # Exchange code for a token. Public client → no Authorization header.
        token_resp = self.client.post(
            "/oauth/token/",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:7331/callback",
                "client_id": self.client_id,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(token_resp.status_code, 200, token_resp.content)
        body = token_resp.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        self.assertEqual(body["token_type"].lower(), "bearer")
        self.assertEqual(body["scope"], "mcp")

        # The minted AccessToken carries the resource claim on the side table.
        from oauth2_provider.models import AccessToken
        from apps.mcp_server.models import MCPTokenResource
        at = AccessToken.objects.get(token=body["access_token"])
        self.assertEqual(at.user, self.staff_parent)
        binding = MCPTokenResource.objects.get(access_token=at)
        self.assertEqual(binding.resource, "https://example.test/mcp")

        # Refresh-token grant returns a fresh access_token.
        refresh_resp = self.client.post(
            "/oauth/token/",
            data={
                "grant_type": "refresh_token",
                "refresh_token": body["refresh_token"],
                "client_id": self.client_id,
            },
        )
        self.assertEqual(refresh_resp.status_code, 200, refresh_resp.content)
        refreshed = refresh_resp.json()
        self.assertIn("access_token", refreshed)
        self.assertNotEqual(refreshed["access_token"], body["access_token"])


# ---------------------------------------------------------------------------
# MCP middleware — Bearer auth + resource binding
# ---------------------------------------------------------------------------


@override_settings(MCP_RESOURCE_URL="https://example.test/mcp", SITE_URL="https://example.test")
class MCPBearerAuthTests(TransactionTestCase):
    """Drive the Starlette middleware directly — no Starlette test client needed.

    ``TransactionTestCase`` so the AccessToken row inserted in setUp is
    visible to the worker thread that asgiref's ``sync_to_async`` uses
    for the ORM lookup. With a plain ``TestCase`` the savepoint isolation
    prevents the worker thread from seeing the parent test's writes on
    SQLite (``database table is locked``).
    """

    def setUp(self):
        fam = make_family(parents=[{"username": "staff", "is_staff": True}])
        self.user = fam.parents[0]

    def _run_middleware(self, header_value: str | None):
        """Invoke ``TokenAuthMiddleware`` with a fake Starlette request.

        Returns (status_code, body_dict).
        """
        import asyncio
        from apps.mcp_server.auth import TokenAuthMiddleware

        async def call_next(_request):
            from starlette.responses import JSONResponse
            return JSONResponse({"ok": True})

        async def runner():
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/mcp/",
                "raw_path": b"/mcp/",
                "headers": [
                    (b"authorization", header_value.encode("ascii")),
                ] if header_value else [],
                "query_string": b"",
                "server": ("example.test", 443),
                "scheme": "https",
                "root_path": "",
            }

            sent: list[dict] = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                sent.append(message)

            # Wrap a no-op ASGI app — TokenAuthMiddleware will short-circuit on
            # error and only call into ``call_next`` (the inner app) on success.
            class InnerApp:
                async def __call__(self, _scope, _receive, _send):
                    from starlette.responses import JSONResponse
                    response = JSONResponse({"ok": True})
                    await response(_scope, _receive, _send)

            mw = TokenAuthMiddleware(InnerApp())
            await mw(scope, receive, send)
            return sent

        sent = asyncio.run(runner())
        # First message is response.start, second is response.body.
        start = next((m for m in sent if m["type"] == "http.response.start"), None)
        body_msg = next((m for m in sent if m["type"] == "http.response.body"), None)
        body = json.loads(body_msg["body"].decode("utf-8")) if body_msg and body_msg.get("body") else {}
        return start["status"], body

    def test_bearer_token_passes(self):
        _, header = make_oauth_token(self.user)
        status, body = self._run_middleware(header)
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})

    def test_missing_authorization_returns_401_with_discovery_hint(self):
        status, body = self._run_middleware(None)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], -32001)
        self.assertIn("discovery_url", body["error"]["data"])

    def test_legacy_token_scheme_rejected_with_hint(self):
        status, body = self._run_middleware("Token doesnotmatter")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], -32001)
        self.assertIn("OAuth 2.1", body["error"]["message"])
        self.assertIn("discovery_url", body["error"]["data"])

    def test_expired_token_rejected(self):
        access, header = make_oauth_token(self.user)
        access.expires = timezone.now() - timedelta(seconds=60)
        access.save(update_fields=["expires"])
        status, body = self._run_middleware(header)
        self.assertEqual(status, 401)

    def test_wrong_resource_binding_rejected(self):
        _, header = make_oauth_token(self.user, resource="https://attacker.example/mcp")
        status, body = self._run_middleware(header)
        self.assertEqual(status, 401)

    def test_missing_resource_claim_accepted(self):
        """Missing claim = legacy / test fixture; we only reject on explicit mismatch."""
        _, header = make_oauth_token(self.user, resource="")  # no claim stored
        status, _ = self._run_middleware(header)
        self.assertEqual(status, 200)

    def test_inactive_user_rejected(self):
        _, header = make_oauth_token(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        status, _ = self._run_middleware(header)
        self.assertEqual(status, 401)


# ---------------------------------------------------------------------------
# Admin REST endpoints
# ---------------------------------------------------------------------------


class AdminOAuthEndpointTests(TestCase):
    def setUp(self):
        fam = make_family(parents=[
            {"username": "staff", "is_staff": True},
            {"username": "regular"},
        ], children=[{"username": "kid"}])
        self.staff = fam.parents[0]
        self.regular = fam.parents[1]
        self.kid = fam.children[0]

    def _client_with_token(self, user):
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=user)
        c = self.client_class()
        c.defaults["HTTP_AUTHORIZATION"] = f"Token {token.key}"
        return c

    def test_list_applications_blocks_non_staff(self):
        c = self._client_with_token(self.regular)
        resp = c.get("/api/admin/oauth/applications/")
        self.assertEqual(resp.status_code, 403)
        c = self._client_with_token(self.kid)
        resp = c.get("/api/admin/oauth/applications/")
        self.assertEqual(resp.status_code, 403)

    def test_list_applications_allows_staff(self):
        c = self._client_with_token(self.staff)
        resp = c.get("/api/admin/oauth/applications/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("applications", resp.json())

    def test_list_tokens_returns_only_own(self):
        # Create a token for staff and a token for regular; the listing must
        # not leak other users' tokens.
        make_oauth_token(self.staff)
        make_oauth_token(self.regular)
        c = self._client_with_token(self.staff)
        resp = c.get("/api/admin/oauth/tokens/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["tokens"]), 1)
