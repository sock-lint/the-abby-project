"""Tests for config.middleware.NoCacheAPIMiddleware."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import User


class NoCacheAPIMiddlewareTests(TestCase):
    """``Cache-Control: no-store`` is stamped on every ``/api/*`` response."""

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="pw", role="child")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_api_response_has_no_store(self):
        resp = self.client.get("/api/notifications/unread_count/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Cache-Control"], "no-store")

    def test_api_error_response_also_has_no_store(self):
        # Unauthenticated call — 401, but still must not be cacheable.
        unauth = APIClient()
        resp = unauth.get("/api/notifications/unread_count/")
        self.assertIn(resp.status_code, (401, 403))
        self.assertEqual(resp["Cache-Control"], "no-store")

    def test_non_api_response_is_untouched(self):
        # SPA catch-all explicitly sets its own Cache-Control: no-cache and an
        # ETag. The middleware must not clobber that.
        resp = self.client.get("/some-spa-route")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Cache-Control"], "no-cache")

    def test_health_endpoint_untouched(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        # /health is served by HealthCheckMiddleware before the URL resolver;
        # it should NOT be marked no-store (probes can cache briefly).
        self.assertNotEqual(resp.get("Cache-Control", ""), "no-store")
