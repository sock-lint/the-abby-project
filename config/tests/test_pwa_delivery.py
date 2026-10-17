"""The release verifier must compare CDN scripts to the actual serving build."""
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from config.middleware import HealthCheckMiddleware


@override_settings(SOURCE_COMMIT="a" * 40, COOLIFY_RESOURCE_UUID="lr5dn6lhga31vyk6u5qvhm4c")
class PwaDeliveryEvidenceTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="abby-runtime-pwa-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.dist = self.base / "frontend_dist"
        self.dist.mkdir()
        self.files = {
            "sw.js": b'importScripts("/push-sw.js", "/privacy-sw.js");',
            "push-sw.js": b'self.addEventListener("push", () => {});',
            "privacy-sw.js": b'self.addEventListener("message", () => {});',
        }
        for name, data in self.files.items():
            (self.dist / name).write_bytes(data)
        self.settings_override = override_settings(BASE_DIR=self.base)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def health(self, *, database_error=False):
        middleware = HealthCheckMiddleware(lambda request: None)
        with patch("config.middleware.connection.ensure_connection",
                   side_effect=RuntimeError("not public") if database_error else None):
            return middleware(RequestFactory().get("/health"))

    def test_health_attests_the_serving_build_bytes(self):
        response = self.health()
        body = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["commit"], "a" * 40)
        self.assertEqual(body["pwaScripts"], {
            "/" + name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in self.files.items()
        })
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn(str(self.base), response.content.decode())

    def test_missing_script_cannot_attest_a_partial_release(self):
        (self.dist / "privacy-sw.js").unlink()
        response = self.health()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("pwaScripts", json.loads(response.content))

    def test_empty_or_oversized_script_cannot_attest_a_release(self):
        for data in (b"", b"x" * (2 * 1024 * 1024 + 1)):
            with self.subTest(bytes=len(data)):
                (self.dist / "sw.js").write_bytes(data)
                self.assertNotIn("pwaScripts", json.loads(self.health().content))

    def test_script_symlink_does_not_disclose_an_outside_file_fingerprint(self):
        outside = self.base / "outside-secret"
        outside.write_text("private fixture")
        script = self.dist / "sw.js"
        script.unlink()
        script.symlink_to(outside)
        response = self.health()
        self.assertNotIn("pwaScripts", json.loads(response.content))
        self.assertNotIn("private fixture", response.content.decode())

    def test_database_failure_preserves_failure_instead_of_proving_delivery(self):
        response = self.health(database_error=True)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("pwaScripts", json.loads(response.content))

    def test_unidentified_container_cannot_attest_a_release(self):
        with override_settings(SOURCE_COMMIT="", COOLIFY_RESOURCE_UUID=""):
            self.assertNotIn("pwaScripts", json.loads(self.health().content))
