"""Co-parent invite links — minting + redemption.

Covers the FamilyInvite model TTL/single-use invariants, the parent-only
mint endpoint, and the anonymous /api/auth/join/<token>/ surface (GET
preview + POST redeem). The generic-404 posture for bad tokens is pinned
here too: unknown, expired, and already-used tokens are indistinguishable
to an unauthenticated caller.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.families.models import FamilyInvite
from apps.projects.models import User
from config.tests.factories import make_family


class _Fixture(TestCase):
    def setUp(self):
        # The join endpoint shares the "signup" throttle scope (5/hour per
        # IP) and DRF throttle history lives in the cache, which persists
        # across tests in a process. Clear on both sides so these tests
        # neither inherit nor leak throttle counts.
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        fam = make_family(
            "Inviters",
            parents=[{"username": "founder", "display_name": "Sage"}],
            children=[{"username": "kid"}],
        )
        self.family = fam.family
        self.parent = fam.parents[0]
        self.child = fam.children[0]
        self.client = APIClient()

    def _mint(self):
        return FamilyInvite.mint(family=self.family, created_by=self.parent)


class InviteMintEndpointTests(_Fixture):
    URL = "/api/family/invites/"

    def test_parent_mints_invite(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(self.URL)

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        invite = FamilyInvite.objects.get(token=body["token"])
        self.assertEqual(invite.family, self.family)
        self.assertEqual(invite.created_by, self.parent)
        self.assertEqual(body["join_path"], f"/join/{invite.token}")
        # 24h TTL window.
        self.assertGreater(invite.expires_at, timezone.now() + timedelta(hours=23))
        self.assertLess(invite.expires_at, timezone.now() + timedelta(hours=25))

    def test_child_cannot_mint(self):
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.post(self.URL).status_code, 403)

    def test_anonymous_cannot_mint(self):
        self.assertEqual(self.client.post(self.URL).status_code, 401)


class JoinPreviewTests(_Fixture):
    def test_open_invite_returns_family_name(self):
        invite = self._mint()
        resp = self.client.get(f"/api/auth/join/{invite.token}/")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["family_name"], "Inviters")
        self.assertEqual(body["invited_by"], "Sage")

    def test_unknown_token_404s_generically(self):
        resp = self.client.get("/api/auth/join/not-a-real-token/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("invalid or has expired", resp.json()["error"])

    def test_expired_token_404s(self):
        invite = self._mint()
        FamilyInvite.objects.filter(pk=invite.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(
            self.client.get(f"/api/auth/join/{invite.token}/").status_code, 404,
        )


class JoinRedeemTests(_Fixture):
    def _join(self, invite, **overrides):
        payload = {
            "username": "coparent",
            "password": "sturdy-passphrase-9",
            "display_name": "Robin",
            **overrides,
        }
        return self.client.post(
            f"/api/auth/join/{invite.token}/", payload, format="json",
        )

    def test_redeem_creates_parent_in_inviters_family(self):
        invite = self._mint()
        resp = self._join(invite)

        self.assertEqual(resp.status_code, 201, msg=resp.content)
        body = resp.json()
        self.assertTrue(body["token"])
        new_parent = User.objects.get(username="coparent")
        self.assertEqual(new_parent.role, "parent")
        self.assertEqual(new_parent.family, self.family)
        self.assertEqual(body["family"]["name"], "Inviters")
        invite.refresh_from_db()
        self.assertIsNotNone(invite.used_at)
        self.assertEqual(invite.used_by, new_parent)

    def test_role_is_hardcoded_parent(self):
        invite = self._mint()
        resp = self._join(invite, role="child")

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(User.objects.get(username="coparent").role, "parent")

    def test_invite_is_single_use(self):
        invite = self._mint()
        self._join(invite)
        resp = self._join(invite, username="second")

        self.assertEqual(resp.status_code, 404)
        self.assertFalse(User.objects.filter(username="second").exists())

    def test_expired_invite_rejected(self):
        invite = self._mint()
        FamilyInvite.objects.filter(pk=invite.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        resp = self._join(invite)

        self.assertEqual(resp.status_code, 404)
        self.assertFalse(User.objects.filter(username="coparent").exists())

    def test_weak_password_rejected_without_consuming_invite(self):
        invite = self._mint()
        resp = self._join(invite, password="123")

        self.assertEqual(resp.status_code, 400)
        invite.refresh_from_db()
        self.assertIsNone(invite.used_at)
        # A corrected retry still works.
        self.assertEqual(self._join(invite).status_code, 201)

    def test_duplicate_username_rejected(self):
        invite = self._mint()
        resp = self._join(invite, username="founder")

        self.assertEqual(resp.status_code, 400)
        self.assertIn("already taken", resp.json()["error"])

    def test_join_ignores_allow_parent_signup_toggle(self):
        # Invites are parent-initiated — the public-signup kill switch
        # must not lock a founder out of adding their co-parent.
        from django.test import override_settings

        invite = self._mint()
        with override_settings(ALLOW_PARENT_SIGNUP=False):
            resp = self._join(invite)
        self.assertEqual(resp.status_code, 201)
