"""Parent-only homework AI settings projected without provider credentials."""
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class HomeworkAISettingsApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture
    url = "/api/homework/ai-settings/"

    def setUp(self):
        household = make_family(
            "Homework AI Fixture Family",
            parents=[{"username": "homework-ai-fixture-parent"}, {"username": "homework-ai-fixture-coparent"}],
            children=[{"username": "homework-ai-fixture-child"}],
        )
        self.parent, self.coparent = household.parents
        self.child = household.children[0]
        self.other_parent = make_family(
            "Other Homework AI Fixture Family",
            parents=[{"username": "homework-ai-fixture-other-parent"}],
        ).parents[0]
        token = Token.objects.create(user=self.parent, key="d" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_settings_fixture(self, response, name):
        body = self.assert_response_fixture(response, name)
        self.assertEqual(set(body), {"provider", "model", "has_api_key"})
        self.assertIsInstance(body["has_api_key"], bool)
        self.assertNotIn("synthetic-provider-key", response.content.decode())
        return body

    def test_save_read_retain_key_and_reset_match_the_shared_bodies(self):
        self.assert_settings_fixture(self.client.get(self.url), "homework-ai-default.json")
        for provider, model in (("openai", "gpt-5.4-mini"), ("anthropic", "claude-haiku-5-5")):
            with self.subTest(provider=provider):
                fixture = f"homework-ai-{provider}.json"
                self.assert_settings_fixture(self.client.put(self.url, {
                    "provider": provider, "model": model, "api_key": "synthetic-provider-key",
                }, format="json"), fixture)
                self.assert_settings_fixture(self.client.get(self.url), fixture)
                for key_fields in ({}, {"api_key": ""}):
                    self.assert_settings_fixture(self.client.put(self.url, {
                        "provider": provider, "model": model, **key_fields,
                    }, format="json"), fixture)
        self.assert_settings_fixture(self.client.delete(self.url), "homework-ai-default.json")
        self.assert_settings_fixture(self.client.get(self.url), "homework-ai-default.json")
        self.assert_settings_fixture(self.client.put(self.url, {
            "provider": "default", "model": "",
        }, format="json"), "homework-ai-default.json")

    def test_settings_are_shared_with_coparents_and_isolated_from_other_families_and_children(self):
        self.assert_settings_fixture(self.client.put(self.url, {
            "provider": "openai", "model": "gpt-5.4-mini", "api_key": "synthetic-provider-key",
        }, format="json"), "homework-ai-openai.json")
        self.client.force_authenticate(self.coparent)
        self.assert_settings_fixture(self.client.get(self.url), "homework-ai-openai.json")
        self.client.force_authenticate(self.other_parent)
        self.assert_settings_fixture(self.client.get(self.url), "homework-ai-default.json")
        self.assert_settings_fixture(self.client.delete(self.url), "homework-ai-default.json")
        self.client.force_authenticate(self.child)
        for method, data in (("get", None), ("put", {"provider": "default", "model": ""}), ("delete", None)):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, data, format="json")
                self.assertEqual(response.status_code, 403, response.content)
        self.client.force_authenticate(self.parent)
        self.assert_settings_fixture(self.client.get(self.url), "homework-ai-openai.json")

    def test_settings_require_authentication_for_every_method(self):
        self.client.credentials()
        for method, data in (("get", None), ("put", {"provider": "default", "model": ""}), ("delete", None)):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, data, format="json")
                self.assertEqual(response.status_code, 401, response.content)
