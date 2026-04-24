"""Tests for PWA root-file URL handling.

Problem: Django's SPA catch-all (re_path(r"^(?!static/|[.]well-known/).*$", spa_view))
greedily matches any unmatched path and returns the React index.html. For a PWA
this is fatal — the service worker MUST be served from /sw.js (not /static/sw.js)
to control the whole app, and browsers reject manifests served as text/html.

Fix: explicit URL routes for the small set of PWA root files, served from
frontend_dist/ directly. sw.js gets Cache-Control: no-cache so update detection
isn't blocked by stale browser caches.

Test hygiene: we can't point static_serve at a non-existent directory, so each
test run writes tiny fixture files to a tempdir and overrides BASE_DIR so the
_pwa_static_serve view reads from the tempdir. No files are created in the real
frontend_dist/ directory — running these tests never touches the build output.
"""
import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

_FIXTURE_FILES = {
    "sw.js": b"// fixture sw\n",
    "registerSW.js": b"// fixture registerSW\n",
    "manifest.webmanifest": b'{"name":"Abby"}',
    "pwa-192x192.png": b"\x89PNG\r\n\x1a\n",
    "pwa-512x512.png": b"\x89PNG\r\n\x1a\n",
    "maskable-icon-512x512.png": b"\x89PNG\r\n\x1a\n",
    "apple-touch-icon.png": b"\x89PNG\r\n\x1a\n",
    "favicon.svg": b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
}


class PwaRoutingTests(TestCase):
    """Pins the PWA root-file routes added in config/urls.py.

    setUpClass spins up a tempdir, materializes fixture files there, and uses
    override_settings to repoint BASE_DIR at it. tearDownClass rips the tempdir
    back down. The real frontend_dist/ is never touched.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp_base_dir = Path(tempfile.mkdtemp(prefix="abby-pwa-test-"))
        (cls._tmp_base_dir / "frontend_dist").mkdir()
        for name, body in _FIXTURE_FILES.items():
            (cls._tmp_base_dir / "frontend_dist" / name).write_bytes(body)
        cls._settings_override = override_settings(BASE_DIR=cls._tmp_base_dir)
        cls._settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._settings_override.disable()
        finally:
            shutil.rmtree(cls._tmp_base_dir, ignore_errors=True)
        super().tearDownClass()

    def test_sw_js_returns_file_not_html(self):
        resp = self.client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_sw_js_has_no_cache_header(self):
        """SW must revalidate on every load — otherwise users get stuck on a
        stale SW that controls a bundle that no longer exists."""
        resp = self.client.get("/sw.js")
        self.assertEqual(resp["Cache-Control"], "no-cache")

    def test_register_sw_js_returns_file_not_html(self):
        resp = self.client.get("/registerSW.js")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_manifest_returns_file_not_html(self):
        resp = self.client.get("/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_pwa_icon_returns_file_not_html(self):
        resp = self.client.get("/pwa-192x192.png")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_pwa_icon_large_returns_file_not_html(self):
        resp = self.client.get("/pwa-512x512.png")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_maskable_icon_returns_file_not_html(self):
        resp = self.client.get("/maskable-icon-512x512.png")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_apple_touch_icon_returns_file_not_html(self):
        resp = self.client.get("/apple-touch-icon.png")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_favicon_svg_returns_file_not_html(self):
        resp = self.client.get("/favicon.svg")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_unknown_root_file_falls_through_to_spa(self):
        """Guard: only the listed PWA files get intercepted. Everything else
        still hits the SPA catch-all so React Router keeps working."""
        resp = self.client.get("/random-nonexistent-thing.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])

    def test_unknown_root_path_falls_through_to_spa(self):
        resp = self.client.get("/some-react-route")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])
