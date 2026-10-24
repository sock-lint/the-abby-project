"""Real OAuth registration metadata shared with the management page checks."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings
from oauth2_provider.models import Application
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.tests.factories import make_family, make_oauth_token


FIXTURE_PATH = Path(settings.BASE_DIR) / "contracts" / "api" / "fixtures" / "oauth-applications.json"
FIXED_NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OAuthApiContractFixtureTests(APITestCase):
    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        caller = make_family(
            "OAuth Fixture Family",
            parents=[{"username": "oauth-fixture-parent", "is_staff": True}],
        ).parents[0]
        other_parent = make_family(
            "Other OAuth Fixture Family",
            parents=[{"username": "other-oauth-fixture-parent", "is_staff": True}],
        ).parents[0]
        self.auth_token = Token.objects.create(user=caller, key="d" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.auth_token.key}")
        self.applications = [
            Application.objects.create(
                client_id=f"synthetic-client-{index}",
                name=f"Codex attempt {index}",
                client_type=Application.CLIENT_PUBLIC,
                authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
                redirect_uris="http://localhost:7331/callback",
                client_secret="",
            )
            for index in (1, 2)
        ]
        Application.objects.filter(pk=self.applications[1].pk).update(
            created=FIXED_NOW - timedelta(days=1),
        )
        with patch("secrets.token_urlsafe", return_value="synthetic-private-access-token"):
            self.other_token, _ = make_oauth_token(
                other_parent, application=self.applications[1], scope="mcp:catalog",
            )

    def test_application_eligibility_matches_shared_contract_across_users(self):
        response = self.client.get("/api/admin/oauth/applications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        body = response.json()
        expected = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        # Preserve JSON boolean types: Python equality alone accepts True == 1.
        self.assertEqual(
            json.dumps(body, sort_keys=True, indent=2),
            json.dumps(expected, sort_keys=True, indent=2),
            "Review both the API and management-page contract when this fixture changes.",
        )
        own_tokens = self.client.get("/api/admin/oauth/tokens/")
        self.assertEqual(own_tokens.status_code, 200)
        self.assertEqual(own_tokens.json(), {"tokens": []})
        for private_value in (
            self.auth_token.key,
            self.other_token.token,
            "other-oauth-fixture-parent",
            "Other OAuth Fixture Family",
        ):
            self.assertNotIn(private_value, response.content.decode())
