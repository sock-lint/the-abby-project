from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token

from config.tests.factories import make_family


@override_settings(
    SECURE_CROSS_ORIGIN_OPENER_POLICY="same-origin",
    SECURE_REFERRER_POLICY="same-origin",
)
class DrivePopupPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parent = make_family(parents=[{"username": "drive-policy-parent"}]).parents[0]
        cls.token = Token.objects.create(user=cls.parent, key="d" * 40)

    def assert_journal_policy(self, response):
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin-allow-popups")
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")

    def assert_private_policy(self, response):
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_journal_allows_google_popup_and_origin_referrer(self):
        for path in ("/", "/quests/ventures/ingest", "/quests/ventures/42?resource=private"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assert_journal_policy(response)

    def test_journal_preserves_google_policy_on_revalidation(self):
        response = self.client.get("/quests/ventures/ingest")
        cached = self.client.get("/quests/ventures/ingest", HTTP_IF_NONE_MATCH=response["ETag"])
        self.assertEqual(cached.status_code, 304)
        self.assert_journal_policy(cached)

    def test_private_api_keeps_default_policies(self):
        response = self.client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.parent.pk)
        self.assert_private_policy(response)

    def test_api_authentication_failure_keeps_default_policies(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)
        self.assert_private_policy(response)

    def test_admin_keeps_default_policies(self):
        for path, status_code in (("/admin/", 302), ("/admin/login/?next=/admin/", 200)):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, status_code)
                self.assert_private_policy(response)
