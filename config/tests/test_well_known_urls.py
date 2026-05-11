"""Tests for /.well-known/* URL handling.

The MCP-spec OAuth 2.1 work made these paths real endpoints — they
return JSON metadata advertising the OAuth flow. Detailed shape tests
live in ``config/tests/test_oauth.py``; this file just guards the
boundary cases:

* The well-known URLs are NOT swallowed by the SPA catch-all (no HTML).
* Unhandled .well-known/* paths still 404 (so future probes like
  security.txt don't accidentally land on the SPA).
* Regular non-well-known routes still serve the SPA.
"""
from django.test import TestCase


class WellKnownRoutingTests(TestCase):
    def test_oauth_protected_resource_returns_json(self):
        """RFC 9728 — returns JSON metadata, not HTML."""
        resp = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp["Content-Type"])
        body = resp.json()
        self.assertIn("resource", body)
        self.assertIn("authorization_servers", body)

    def test_oauth_authorization_server_returns_json(self):
        """RFC 8414 — returns JSON metadata, not HTML."""
        resp = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp["Content-Type"])
        body = resp.json()
        self.assertIn("issuer", body)
        self.assertIn("authorization_endpoint", body)
        self.assertIn("token_endpoint", body)

    def test_arbitrary_well_known_path_404s(self):
        """Future well-known probes (security.txt, apple-app-site-association,
        etc.) should 404 unless explicitly routed — NOT return the SPA."""
        resp = self.client.get("/.well-known/security.txt")
        self.assertEqual(resp.status_code, 404)

    def test_regular_spa_route_still_returns_index(self):
        """Guard: we must NOT break the SPA catch-all for normal routes."""
        resp = self.client.get("/some-react-route")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])

    def test_root_still_returns_index(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])

    def test_oauth_authorize_does_not_serve_spa(self):
        """``/oauth/*`` is now real — the SPA must not capture it.

        The SPA view stamps a content-based ETag on every response
        (see ``spa_view`` in config/urls.py). OAuth views don't —
        absence of that ETag is the load-bearing signal that the
        URL didn't fall through to the SPA catch-all.
        """
        resp = self.client.get("/oauth/authorize/")
        # OAuth views never emit the SPA's content-based ETag.
        from config.urls import _INDEX_HTML_ETAG
        self.assertNotEqual(resp.get("ETag", ""), _INDEX_HTML_ETAG)
