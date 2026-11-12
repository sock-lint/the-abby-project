from django.test import SimpleTestCase, override_settings


@override_settings(CORS_ALLOWED_ORIGINS=["capacitor://localhost", "https://localhost"])
class NativeCorsTests(SimpleTestCase):
    def test_selected_webview_can_request_personal_space_without_adding_origins(self):
        for origin in ("capacitor://localhost", "https://localhost"):
            with self.subTest(origin=origin):
                response = self.client.options(
                    "/api/dashboard/", HTTP_ORIGIN=origin,
                    HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
                    HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-abby-space",
                )
                self.assertEqual(response["Access-Control-Allow-Origin"], origin)
                self.assertIn("x-abby-space", response["Access-Control-Allow-Headers"])

    def test_selected_webview_can_revalidate_public_sprite_catalog(self):
        for origin in ("capacitor://localhost", "https://localhost"):
            with self.subTest(origin=origin):
                response = self.client.options(
                    "/api/sprites/catalog/",
                    HTTP_ORIGIN=origin,
                    HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
                    HTTP_ACCESS_CONTROL_REQUEST_HEADERS="if-none-match",
                )
                self.assertEqual(response["Access-Control-Allow-Origin"], origin)
                self.assertIn("if-none-match", response["Access-Control-Allow-Headers"])

    def test_unselected_origin_is_not_allowed(self):
        response = self.client.options(
            "/api/sprites/catalog/",
            HTTP_ORIGIN="https://untrusted.example",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )
        self.assertNotIn("Access-Control-Allow-Origin", response)
