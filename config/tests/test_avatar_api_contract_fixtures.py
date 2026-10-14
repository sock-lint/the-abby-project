"""Archer appearance responses produced by the real authenticated API."""

from unittest.mock import patch

from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.rpg.avatar import AVATAR_DEFAULTS
from apps.rpg.models import CharacterProfile
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared_fixtures


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AvatarApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared_fixtures.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.child = make_family(
            "Avatar Fixture Family", family_id=13,
            children=[{
                "id": 7, "username": "fixture-avatar-child", "display_name": "Fixture Avatar Child",
            }],
        ).children[0]
        # The only synthetic profile gets a fixed identity across SQLite/PostgreSQL sequence state.
        CharacterProfile.objects.filter(user=self.child).update(id=301)
        self.profile = CharacterProfile.objects.get(user=self.child)
        token = Token.objects.create(user=self.child, key="a" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_default_and_saved_avatar_character_responses(self):
        default = self.assert_response_fixture(
            self.client.get("/api/character/"), "character-avatar-default.json",
        )
        self.assertEqual(default["avatar_preferences"], AVATAR_DEFAULTS)
        self.assertEqual(self.profile.avatar_preferences, {})
        choices = {
            "hair_style": "hair-04", "hair_color": "grey", "skin_tone": "tan",
            "outfit": "fire", "outfit_style": "archer-03", "face_style": "face-02", "head_style": "head-01",
            "headwear_style": "crown-eve", "mask_style": "mask-undercover",
            "bow_style": "bow-vines", "quiver_style": "quiver-rook",
        }
        saved = self.assert_response_fixture(
            self.client.post("/api/character/avatar/", {"avatar_preferences": choices}, format="json"),
            "character-avatar-saved.json",
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, choices)
        self.assertEqual(self.client.get("/api/character/").json(), saved)
        self.assertEqual(self.client.post(
            "/api/character/avatar/", {"avatar_preferences": choices}, format="json",
        ).json(), saved)

    def test_legacy_avatar_projects_default_costume_without_persisting_a_read(self):
        legacy = {
            "hair_style": "hair-02", "hair_color": "light", "skin_tone": "tan", "outfit": "aqua",
        }
        self.profile.avatar_preferences = legacy
        self.profile.save(update_fields=["avatar_preferences"])
        before = CharacterProfile.objects.filter(pk=self.profile.pk).values().get()
        response = self.assert_response_fixture(
            self.client.get("/api/character/"), "character-avatar-legacy.json",
        )
        self.assertEqual(response["avatar_preferences"], {
            **legacy, "outfit_style": "archer-01", "face_style": "face-01", "head_style": "head-02",
            "headwear_style": "none", "mask_style": "none", "bow_style": "none", "quiver_style": "none",
        })
        self.assertEqual(CharacterProfile.objects.filter(pk=self.profile.pk).values().get(), before)

    def test_invalid_appearance_fixture_has_no_write(self):
        before = CharacterProfile.objects.get(user=self.child).avatar_preferences
        self.assert_response_fixture(
            self.client.post("/api/character/avatar/", {
                "avatar_preferences": {"outfit": "unsupported"},
            }, format="json"), "character-avatar-invalid.json", status=400,
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, before)
