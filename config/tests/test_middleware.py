"""Tests for config.middleware (NoCacheAPIMiddleware + HealthCheckMiddleware)."""
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
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

    def test_health_endpoint_has_its_own_no_store(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        # /health is served by HealthCheckMiddleware before the URL resolver;
        # Its release evidence must identify the current serving container.
        self.assertEqual(resp["Cache-Control"], "no-store")

    def test_api_view_that_sets_cache_control_is_not_clobbered(self):
        """Views that explicitly set Cache-Control opt out of the no-store
        default. SpriteCatalogView is the canonical example.
        """
        from rest_framework.test import APIClient
        unauth = APIClient()
        resp = unauth.get("/api/sprites/catalog/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("public", resp["Cache-Control"])
        self.assertNotEqual(resp["Cache-Control"], "no-store")


class HealthCheckDeepModeTests(TestCase):
    """The ``?deep=true`` opt-in probes the sprite storage backend on top
    of the default DB-only liveness check. Useful for surfacing
    Cloudflare / Ceph-edge 521s that would otherwise only show up when
    someone tries to write a sprite — the bug shape that wasted a Gemini
    sheet's worth of API budget before the pre-flight in sprite_generation
    landed.
    """

    def test_default_health_does_not_probe_storage(self):
        """The cheap default path stays cheap — Coolify polls every 10s."""
        with patch("apps.rpg.storage.probe_storage") as probe:
            probe.return_value = (True, "ok")
            resp = self.client.get("/health")
            self.assertEqual(resp.status_code, 200)
            probe.assert_not_called()
        body = json.loads(resp.content)
        self.assertNotIn("storage", body)

    def test_deep_mode_reports_storage_up(self):
        with patch("apps.rpg.storage.probe_storage", return_value=(True, "ok")) as probe:
            resp = self.client.get("/health?deep=true")
            self.assertEqual(resp.status_code, 200)
            probe.assert_called_once()
        body = json.loads(resp.content)
        self.assertEqual(body["storage"], "up")
        self.assertEqual(body["status"], "ok")

    def test_deep_mode_reports_storage_down_with_503(self):
        with patch(
            "apps.rpg.storage.probe_storage",
            return_value=(False, "ClientError: 521 Web Server Is Down"),
        ):
            resp = self.client.get("/health?deep=true")
        self.assertEqual(resp.status_code, 503)
        body = json.loads(resp.content)
        self.assertEqual(body["storage"], "down")
        self.assertEqual(body["status"], "degraded")
        self.assertIn("521", body["storage_error"])
        self.assertEqual(resp["Cache-Control"], "no-store")

    def test_deep_mode_accepts_alternate_truthy_values(self):
        """Operators have muscle memory for ``?deep=1`` from other tools."""
        with patch("apps.rpg.storage.probe_storage", return_value=(True, "ok")) as probe:
            self.client.get("/health?deep=1")
            self.client.get("/health?deep=yes")
            self.client.get("/health?deep=TRUE")
            self.assertEqual(probe.call_count, 3)


class HealthCheckReleaseEvidenceTests(TestCase):
    commit = "a" * 40
    resource_uuid = "lr5dn6lhga31vyk6u5qvhm4c"

    @override_settings(SOURCE_COMMIT="a" * 40, COOLIFY_RESOURCE_UUID="lr5dn6lhga31vyk6u5qvhm4c")
    def test_served_identity_is_validated_and_never_cached(self):
        response = self.client.get("/health")
        self.assertEqual(response.json(), {
            "status": "ok", "db": "up", "commit": self.commit,
            "resourceUuid": self.resource_uuid,
        })
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_missing_or_invalid_environment_is_omitted(self):
        for commit in ("", "a" * 39, "a" * 41, "A" * 40, "main", "a" * 40 + "\n", None):
            with self.subTest(commit=commit), override_settings(
                SOURCE_COMMIT=commit, COOLIFY_RESOURCE_UUID="not-the-abby-application",
            ):
                response = self.client.get("/health")
                self.assertEqual(response.json(), {"status": "ok", "db": "up"})
                self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(SOURCE_COMMIT="a" * 40, COOLIFY_RESOURCE_UUID="")
    def test_valid_commit_does_not_invent_resource_identity(self):
        self.assertEqual(self.client.get("/health").json(), {
            "status": "ok", "db": "up", "commit": self.commit,
        })

    @override_settings(SOURCE_COMMIT="a" * 40, COOLIFY_RESOURCE_UUID="lr5dn6lhga31vyk6u5qvhm4c")
    def test_database_failure_preserves_failure_and_uncached_identity(self):
        with patch("config.middleware.connection.ensure_connection", side_effect=RuntimeError("private detail")):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "status": "degraded", "db": "down", "commit": self.commit,
            "resourceUuid": self.resource_uuid,
        })
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn("private detail", response.content.decode())

    @override_settings(SOURCE_COMMIT="a" * 40, COOLIFY_RESOURCE_UUID="lr5dn6lhga31vyk6u5qvhm4c")
    def test_deep_failure_keeps_served_identity(self):
        with patch("apps.rpg.storage.probe_storage", return_value=(False, "unavailable")):
            response = self.client.get("/health?deep=true")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["commit"], self.commit)
        self.assertEqual(response.json()["resourceUuid"], self.resource_uuid)
        self.assertEqual(response["Cache-Control"], "no-store")
