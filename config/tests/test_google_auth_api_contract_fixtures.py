"""Google authorization contracts from real Abby endpoints and synthetic OAuth."""
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from apps.google_integration.models import GoogleAccount, GoogleOAuthTransaction
from apps.google_integration.services import GoogleAuthService
from apps.google_integration.tests.test_oauth_exchange import VERIFIER, challenge
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


BASE = "/api/auth/google/"
STATE = "s" * 43
TICKET = "t" * 43
REDIRECT = "https://journal.example.invalid/api/auth/google/callback/"


@override_settings(
    GOOGLE_CLIENT_ID="synthetic-client.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="synthetic-server-secret",
    GOOGLE_REDIRECT_URI=REDIRECT,
)
class GoogleAuthApiContractFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        family = make_family(
            "Google Authorization Fixture Family", family_id=901,
            parents=[{"id": 910, "username": "fixture-google-parent", "display_name": "Alex"}],
            children=[{"id": 912, "username": "fixture-google-child", "display_name": "River"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.credential = Token.objects.create(user=self.parent, key="e" * 40)
        secrets = patch("apps.google_integration.oauth_exchange.secrets.token_urlsafe", side_effect=[STATE, TICKET])
        secrets.start()
        self.addCleanup(secrets.stop)

        def authorization(*, state):
            return "https://accounts.google.com/o/oauth2/auth?" + urlencode({
                "client_id": "synthetic-client.apps.googleusercontent.com", "redirect_uri": REDIRECT,
                "response_type": "code", "state": state,
            }), state, "synthetic-provider-pkce"

        provider_url = patch.object(GoogleAuthService, "get_authorization_url", side_effect=authorization)
        provider_url.start()
        self.addCleanup(provider_url.stop)
        provider = patch.object(GoogleAuthService, "exchange_code", return_value=(
            "synthetic-fixture-google", "fixture@example.invalid", {"token": "synthetic-private-provider-token"},
        ))
        provider.start()
        self.addCleanup(provider.stop)

    def begin(self, *, linking=False):
        if linking:
            self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.credential.key}")
        query = {"code_challenge": challenge(), "code_challenge_method": "S256"}
        if linking:
            query["for_user"] = self.child.pk
        return self.client.get(BASE if linking else BASE + "login/", query)

    def finish(self):
        callback = APIClient().get(BASE + "callback/", {"state": STATE, "code": "synthetic-google-code"})
        self.assertEqual(callback.status_code, 302)
        self.assertEqual(urlsplit(callback.url).query, "")
        fragment = parse_qs(urlsplit(callback.url).fragment)
        self.assertEqual(fragment, {"google_exchange": [TICKET], "google_state": [STATE]})
        return self.client.post(BASE + "exchange/", {"exchange_code": TICKET, "code_verifier": VERIFIER}, format="json")

    def test_public_configuration_matches_shared_contract_without_allocating_authorization(self):
        self.assert_response_fixture(self.client.get(BASE + "config/"), "google-auth-config.json")
        self.assertFalse(GoogleOAuthTransaction.objects.exists())

    def test_authorization_capacity_failure_matches_shared_contract_without_persisting_secrets(self):
        with patch("apps.google_integration.oauth_exchange.MAX_TRANSACTIONS", 0):
            body = self.assert_response_fixture(self.begin(), "google-auth-busy.json", status=503)
        self.assertEqual(body["code"], "authorization_busy")
        self.assertFalse(GoogleOAuthTransaction.objects.exists())
        self.assertTrue(Token.objects.filter(pk=self.credential.key).exists())
        for secret in (self.credential.key, VERIFIER, "synthetic-provider-pkce", "synthetic-server-secret"):
            self.assertNotIn(secret, str(body))

    def test_login_initiation_matches_shared_contract_with_only_public_redirect_metadata(self):
        response = self.begin()
        self.assert_response_fixture(response, "google-auth-init.json")
        for secret in (self.credential.key, VERIFIER, "synthetic-provider-pkce", "synthetic-server-secret"):
            self.assertNotIn(secret, response.content.decode())

    def test_login_exchange_matches_shared_contract_and_reuses_actual_legacy_token(self):
        GoogleAuthService.link_account(self.parent, "synthetic-fixture-google", "fixture@example.invalid", {"token": "synthetic-before"})
        self.assertEqual(self.begin().status_code, 200)
        body = self.assert_response_fixture(self.finish(), "google-auth-login.json")
        self.assertEqual(body["token"], self.credential.key)
        self.assertEqual(body["user"]["id"], self.parent.pk)
        self.assertIs(body["user"]["is_staff"], False)
        self.assertNotIn("synthetic-private-provider-token", str(body))
        self.assertEqual(Token.objects.filter(user=self.parent).count(), 1)

    def test_parent_child_link_exchange_matches_shared_contract_without_child_signin(self):
        self.assertEqual(self.begin(linking=True).status_code, 200)
        self.assertFalse(GoogleAccount.objects.filter(user=self.child).exists())
        self.assert_response_fixture(self.finish(), "google-auth-linked.json")
        self.assertEqual(GoogleAccount.objects.get(user=self.child).linked_by_id, self.parent.pk)
        self.assertFalse(Token.objects.filter(user=self.child).exists())
