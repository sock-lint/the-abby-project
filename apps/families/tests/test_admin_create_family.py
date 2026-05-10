"""Staff-only ``/api/admin/families/`` endpoint.

The deployment owner (``createsuperuser``-style staff parent) needs a way
to mint sibling families from inside the app even when public signup is
turned off. This pins the staff gate, the FamilyService reuse, and the
``ALLOW_PARENT_SIGNUP`` bypass.
"""
from __future__ import annotations

from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.families.models import Family
from config.tests.factories import make_family


class AdminCreateFamilyTests(APITestCase):
    def setUp(self):
        self.fam = make_family(
            "Default", parents=[{"username": "regular"}],
        )
        self.regular_parent = self.fam.parents[0]
        # Create a staff parent in the same family to represent the deploy
        # owner. The staff bit is what gates IsStaffParent.
        self.staff_parent = User.objects.create_user(
            username="admin", password="pw", role="parent",
            family=self.fam.family, is_staff=True,
        )
        self.regular_token = Token.objects.create(user=self.regular_parent)
        self.staff_token = Token.objects.create(user=self.staff_parent)

    def _auth_staff(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")

    def _auth_regular(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.regular_token.key}")

    def test_unauthenticated_caller_forbidden(self):
        response = self.client.post(
            "/api/admin/families/",
            {"username": "u", "password": "p", "family_name": "F"},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_regular_parent_forbidden(self):
        self._auth_regular()
        response = self.client.post(
            "/api/admin/families/",
            {"username": "u", "password": "p", "family_name": "F"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_child_forbidden(self):
        kid = User.objects.create_user(
            username="kid", password="pw", role="child", family=self.fam.family,
        )
        token = Token.objects.create(user=kid)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.post(
            "/api/admin/families/",
            {"username": "u", "password": "p", "family_name": "F"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_parent_creates_new_family(self):
        self._auth_staff()
        response = self.client.post(
            "/api/admin/families/",
            {
                "username": "founder",
                "password": "ApbBy1!Strong",
                "display_name": "Founder",
                "family_name": "New House",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("token", body)
        self.assertEqual(body["user"]["username"], "founder")
        self.assertEqual(body["family"]["name"], "New House")

        new_family = Family.objects.get(slug="new-house")
        self.assertNotEqual(new_family.id, self.fam.family.id)
        founder = User.objects.get(username="founder")
        self.assertEqual(founder.role, "parent")
        self.assertEqual(founder.family_id, new_family.id)
        self.assertEqual(new_family.primary_parent_id, founder.id)

    @override_settings(ALLOW_PARENT_SIGNUP=False)
    def test_staff_creation_bypasses_allow_parent_signup_toggle(self):
        # Public signup off; admin endpoint must still work for staff.
        self._auth_staff()
        response = self.client.post(
            "/api/admin/families/",
            {
                "username": "founder2",
                "password": "ApbBy1!Strong",
                "family_name": "Another House",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_rejects_duplicate_username(self):
        self._auth_staff()
        response = self.client.post(
            "/api/admin/families/",
            {
                "username": "regular",  # already exists
                "password": "ApbBy1!Strong",
                "family_name": "X",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already taken", response.json()["error"])

    def test_rejects_weak_password(self):
        self._auth_staff()
        response = self.client.post(
            "/api/admin/families/",
            {"username": "u", "password": "abc", "family_name": "X"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_missing_family_name(self):
        self._auth_staff()
        response = self.client.post(
            "/api/admin/families/",
            {"username": "u", "password": "ApbBy1!Strong"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_get_returns_200_for_staff(self):
        # The frontend pings GET as a "is this user staff?" probe to gate
        # the Admin tab visibility.
        self._auth_staff()
        response = self.client.get("/api/admin/families/")
        self.assertEqual(response.status_code, 200)

    def test_get_returns_403_for_regular_parent(self):
        self._auth_regular()
        response = self.client.get("/api/admin/families/")
        self.assertEqual(response.status_code, 403)
