"""Keep API misses out of the successful HTML SPA fallback."""

import json

from django.conf import settings
from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False)
class APIRoutingTests(SimpleTestCase):
    def test_unknown_api_paths_return_json_not_the_spa(self):
        for path in ("/api/missing-endpoint/", "/api/missing/nested/"):
            for method in ("get", "post", "put", "patch", "delete"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path + "?private=synthetic")
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response["Content-Type"], "application/json")
                    fixture = settings.BASE_DIR / "contracts/api/fixtures/api-not-found.json"
                    self.assertEqual(response.json(), json.loads(fixture.read_text()))
                    self.assertEqual(response["Cache-Control"], "no-store")

    def test_head_api_miss_has_no_body(self):
        response = self.client.head("/api/missing-endpoint/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.content, b"")

    def test_registered_api_without_slash_uses_the_normal_redirect(self):
        for path in ("/api", "/api/homework/dashboard"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertRedirects(
                    response, path + "/", status_code=301,
                    fetch_redirect_response=False,
                )

    def test_registered_api_still_uses_its_authentication(self):
        for path in ("/api/", "/api/homework/dashboard/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["Content-Type"], "application/json")

    def test_similarly_named_spa_route_still_returns_html(self):
        response = self.client.get("/api-guide")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])

    def test_other_reserved_prefixes_keep_normal_not_found_handling(self):
        for path in ("/static/missing.js", "/oauth/missing/", "/.well-known/missing"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertIn("text/html", response["Content-Type"])
