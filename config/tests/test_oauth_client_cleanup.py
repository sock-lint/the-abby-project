"""Staff cleanup must preserve every user's live OAuth connection."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from oauth2_provider.models import Application, Grant, RefreshToken
from rest_framework.test import APIClient

from apps.mcp_server.models import MCPAuthorizationResource, MCPTokenResource
from config.tests.factories import make_family, make_oauth_token


class OAuthClientCleanupTests(TestCase):
    def setUp(self):
        family = make_family(parents=[
            {"username": "cleanup-staff", "is_staff": True},
            {"username": "cleanup-parent"},
        ], children=[{"username": "cleanup-child", "is_staff": True}])
        self.staff, self.parent = family.parents
        self.child = family.children[0]
        self.other = make_family(parents=[
            {"username": "cleanup-other-staff", "is_staff": True},
        ]).parents[0]
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.app = Application.objects.create(
            name="Unused synthetic client", client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://localhost:7331/callback", client_secret="",
        )
        self.url = f"/api/admin/oauth/applications/{self.app.client_id}/"

    def eligibility(self):
        response = self.client.get("/api/admin/oauth/applications/")
        self.assertEqual(response.status_code, 200)
        return next(row["can_delete"] for row in response.json()["applications"]
                    if row["client_id"] == self.app.client_id)

    def grant(self, expires):
        grant = Grant.objects.create(
            application=self.app, user=self.other, code="synthetic-cleanup-code",
            expires=expires, redirect_uri="http://localhost:7331/callback",
        )
        MCPAuthorizationResource.objects.create(grant=grant, resource="https://example.test/mcp")
        return grant

    def assert_protected(self):
        self.assertFalse(self.eligibility())
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "application_in_use")
        self.assertTrue(Application.objects.filter(pk=self.app.pk).exists())

    def test_unused_registration_can_be_removed_without_touching_other_connections(self):
        token, _ = make_oauth_token(self.other)
        self.assertTrue(self.eligibility())
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(Application.objects.filter(pk=self.app.pk).exists())
        token.refresh_from_db()
        self.assertGreater(token.expires, timezone.now())
        self.assertTrue(Application.objects.filter(pk=token.application_id).exists())
        self.assertEqual(self.client.delete(self.url).status_code, 404)

    def test_another_households_access_token_protects_registration(self):
        token, _ = make_oauth_token(self.other, application=self.app)
        self.assert_protected()
        token.refresh_from_db()
        self.assertGreater(token.expires, timezone.now())
        self.assertEqual(self.client.get("/api/admin/oauth/tokens/").json(), {"tokens": []})

    def test_unrevoked_refresh_token_protects_expired_access(self):
        token, _ = make_oauth_token(self.other, application=self.app, expires_in_seconds=-60)
        refresh = RefreshToken.objects.create(
            user=self.other, application=self.app, access_token=token,
            token="synthetic-cleanup-refresh",
        )
        self.assert_protected()
        refresh.refresh_from_db()
        self.assertIsNone(refresh.revoked)

    def test_pending_authorization_code_protects_registration(self):
        grant = self.grant(timezone.now() + timedelta(minutes=5))
        self.assert_protected()
        self.assertTrue(Grant.objects.filter(pk=grant.pk).exists())

    def test_expired_and_revoked_history_is_removed_with_resource_bindings(self):
        now = timezone.now()
        token, _ = make_oauth_token(self.other, application=self.app)
        token.expires = now
        token.save(update_fields=["expires"])
        grant = self.grant(now)
        refresh = RefreshToken.objects.create(
            user=self.other, application=self.app, access_token=token,
            token="synthetic-revoked-refresh", revoked=now,
        )
        with patch("django.utils.timezone.now", return_value=now):
            self.assertTrue(self.eligibility())
            response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(MCPTokenResource.objects.filter(access_token_id=token.pk).exists())
        self.assertFalse(MCPAuthorizationResource.objects.filter(grant_id=grant.pk).exists())
        self.assertFalse(RefreshToken.objects.filter(pk=refresh.pk).exists())

    def test_delete_rechecks_eligibility_after_list(self):
        self.assertTrue(self.eligibility())
        make_oauth_token(self.other, application=self.app)
        self.assert_protected()

    def test_revoking_connection_then_removing_registration(self):
        token, _ = make_oauth_token(self.other, application=self.app)
        RefreshToken.objects.create(
            user=self.other, application=self.app, access_token=token,
            token="synthetic-revoke-then-remove",
        )
        self.assert_protected()
        response = self.client.delete(self.url + "tokens/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.eligibility())
        self.assertEqual(self.client.delete(self.url).status_code, 200)
        self.assertFalse(Application.objects.filter(pk=self.app.pk).exists())

    def test_delete_requires_active_staff_parent(self):
        for user in (None, self.parent, self.child):
            with self.subTest(user=user):
                self.client.force_authenticate(user)
                self.assertIn(self.client.delete(self.url).status_code, (401, 403))
                self.assertTrue(Application.objects.filter(pk=self.app.pk).exists())
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.assertTrue(Application.objects.filter(pk=self.app.pk).exists())
