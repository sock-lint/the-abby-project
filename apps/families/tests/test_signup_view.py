"""Tests for the parent self-signup endpoint."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.families.models import Family


User = get_user_model()


class SignupViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_creates_family_and_returns_token(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "username": "mike",
                "password": "ApbBy1!Strong",
                "display_name": "Mike",
                "family_name": "The Sageb Family",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("token", body)
        self.assertEqual(body["user"]["username"], "mike")
        self.assertEqual(body["family"]["name"], "The Sageb Family")
        # Family + parent + token wired correctly.
        family = Family.objects.get(slug="the-sageb-family")
        self.assertEqual(family.primary_parent.username, "mike")
        self.assertTrue(Token.objects.filter(user__username="mike").exists())

    def test_signup_rejects_duplicate_username(self):
        User.objects.create_user(username="mike", password="pw")
        response = self.client.post(
            "/api/auth/signup/",
            {
                "username": "mike",
                "password": "ApbBy1!Strong",
                "family_name": "A",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already taken", response.json()["error"])

    def test_signup_rejects_weak_password(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "username": "mike",
                "password": "abc",
                "family_name": "A",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(ALLOW_PARENT_SIGNUP=False)
    def test_signup_disabled_when_setting_off(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "username": "mike",
                "password": "ApbBy1!Strong",
                "family_name": "A",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("disabled", response.json()["error"].lower())

    def test_signup_does_not_accept_role_in_payload(self):
        # Sneaking role=child must be ignored — the service hard-codes parent.
        response = self.client.post(
            "/api/auth/signup/",
            {
                "username": "mike",
                "password": "ApbBy1!Strong",
                "family_name": "A",
                "role": "child",  # should be ignored
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username="mike").role, "parent")
