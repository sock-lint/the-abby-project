"""Tests for /.well-known/* URL handling.

Problem we're fixing: Django's SPA catch-all (``re_path(r"^.*$", spa_view)``
in config/urls.py) greedily matches ANY unmatched path and returns the
React ``index.html`` with HTTP 200. This breaks MCP clients (``mcp-remote``,
Claude Desktop, Cursor, etc.) that probe ``/.well-known/oauth-protected-resource``
and ``/.well-known/oauth-authorization-server`` during connection: they
expect either 404 (→ fall back to the ``Authorization`` header they were
configured with) or valid OAuth metadata JSON. Getting HTML instead causes
``JSON.parse`` to crash and the MCP client disconnects before auth.

The fix excludes ``.well-known/*`` from the SPA catch-all so those paths
404 cleanly. No OAuth implementation is added — the Abby MCP uses DRF
TokenAuthentication, not OAuth 2.1.
"""
from django.test import TestCase


class WellKnownRoutingTests(TestCase):
    def test_oauth_protected_resource_404s(self):
        """mcp-remote probes this path first. 404 is the "no OAuth, use
        my header" signal. HTML with 200 was the breakage — a 404 with
        a text/html body is fine because clients check status code first
        and don't attempt to parse 4xx bodies as JSON."""
        resp = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(resp.status_code, 404)

    def test_oauth_authorization_server_404s(self):
        """Secondary probe used by some MCP clients."""
        resp = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(resp.status_code, 404)

    def test_arbitrary_well_known_path_404s(self):
        """Future well-known probes (security.txt, apple-app-site-association,
        etc.) should also 404 unless explicitly routed — NOT return the SPA."""
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
