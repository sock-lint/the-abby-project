"""Saved avatar appearance is self-scoped presentation, never earned state."""

from datetime import date, datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.rewards.models import CoinLedger
from apps.rpg.avatar import AVATAR_DEFAULTS, AVATAR_OPTIONS
from apps.rpg.models import CharacterProfile, DropLog, ItemDefinition, UserInventory
from config.tests.factories import make_family


CHOICES = {
    "hair_style": "hair-04", "hair_color": "light",
    "skin_tone": "tan", "outfit": "fire",
}
FIXED_NOW = datetime(2026, 10, 12, 18, 0, tzinfo=datetime_timezone.utc)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AvatarPreferencesTests(APITestCase):
    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Avatar Family",
            parents=[{"username": "avatar-parent"}],
            children=[{"username": "avatar-child"}, {"username": "avatar-sibling"}],
        )
        other = make_family(
            "Other Avatar Family", parents=[{"username": "avatar-foreign-parent"}],
            children=[{"username": "avatar-outsider"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.foreign_parent, self.outsider = other.parents[0], other.children[0]
        self.profile = CharacterProfile.objects.get(user=self.child)
        frame = ItemDefinition.objects.create(name="Owned frame", item_type="cosmetic_frame")
        UserInventory.objects.create(user=self.child, item=frame, quantity=1)
        self.badge = Badge.objects.create(
            name="Already earned", description="A prior achievement.", criteria_type="first_project",
        )
        UserBadge.objects.create(user=self.child, badge=self.badge)
        self.profile.active_frame = frame
        self.profile.active_trophy_badge = self.badge
        self.profile.level = 3
        self.profile.login_streak = 5
        self.profile.last_active_date = date(2026, 10, 10)
        self.profile.pending_companion_growth = [{"pet_id": 51, "growth_added": 1}]
        self.profile.save()
        category = SkillCategory.objects.create(name="Avatar test skill category")
        skill = Skill.objects.create(name="Existing skill", category=category)
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=42, level=2)
        CoinLedger.objects.create(user=self.child, amount=23, reason="adjustment")
        self.sign_in(self.child)

    def sign_in(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def snapshot(self):
        return {
            "profiles": list(CharacterProfile.objects.order_by("id").values()),
            "users": list(type(self.child).objects.order_by("id").values()),
            "coins": list(CoinLedger.objects.order_by("id").values()),
            "skills": list(SkillProgress.objects.order_by("id").values()),
            "inventory": list(UserInventory.objects.order_by("id").values()),
            "badges": list(UserBadge.objects.order_by("id").values()),
            "drops": list(DropLog.objects.order_by("id").values()),
        }

    def post(self, preferences, **body):
        return self.client.post(
            "/api/character/avatar/", {"avatar_preferences": preferences, **body}, format="json",
        )

    def test_new_and_existing_profiles_return_defaults_without_persisting_a_read(self):
        self.assertEqual(self.profile.avatar_preferences, {})
        before = self.snapshot()
        response = self.client.get("/api/character/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_preferences"], AVATAR_DEFAULTS)
        self.assertEqual(self.snapshot(), before)

    def test_save_persists_full_response_without_changing_any_earned_state(self):
        before = self.snapshot()
        response = self.post(CHOICES)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_preferences"], CHOICES)
        self.assertEqual(response.data["active_trophy_badge"]["id"], self.badge.pk)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, CHOICES)
        self.assertEqual(self.client.get("/api/character/").data, response.data)
        after = self.snapshot()
        for profile in after["profiles"]:
            if profile["user_id"] == self.child.pk:
                profile["avatar_preferences"] = {}
                profile["updated_at"] = next(row["updated_at"] for row in before["profiles"] if row["user_id"] == self.child.pk)
        self.assertEqual(after, before)

    def test_partial_replacement_and_empty_reset_use_all_defaults(self):
        self.assertEqual(self.post(CHOICES).status_code, 200)
        response = self.post({"hair_style": "hair-02"})
        self.assertEqual(response.data["avatar_preferences"], {**AVATAR_DEFAULTS, "hair_style": "hair-02"})
        response = self.post({})
        self.assertEqual(response.data["avatar_preferences"], AVATAR_DEFAULTS)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, AVATAR_DEFAULTS)

    def test_retry_is_idempotent_even_after_time_passes(self):
        first = self.post(CHOICES)
        before = self.snapshot()
        with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(minutes=2)):
            second = self.post(CHOICES)
        self.assertEqual(second.data, first.data)
        self.assertEqual(self.snapshot(), before)

    def test_every_recorded_option_is_accepted(self):
        for key, values in AVATAR_OPTIONS.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    response = self.post({key: value})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data["avatar_preferences"], {**AVATAR_DEFAULTS, key: value})

    def test_invalid_preferences_and_unknown_fields_are_rejected_without_writes(self):
        before = self.snapshot()
        invalid = [None, [], "hair-01", 1, True, {"unknown": "value"}]
        for key in AVATAR_OPTIONS:
            invalid.extend({key: value} for value in (None, [], {}, 1, True, "", "unsupported"))
        for preferences in invalid:
            with self.subTest(preferences=preferences):
                self.assertEqual(self.post(preferences).status_code, 400)
                self.assertEqual(self.snapshot(), before)
        for body in ({}, [], None, {"avatar_preferences": {}, "level": 99}):
            with self.subTest(body=body):
                response = self.client.post("/api/character/avatar/", body, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(), before)

    def test_sibling_and_foreign_account_targeting_is_rejected_for_children_and_parents(self):
        before = self.snapshot()
        for actor in (self.child, self.parent, self.foreign_parent):
            self.sign_in(actor)
            for target in (self.child, self.sibling, self.outsider):
                with self.subTest(actor=actor.pk, target=target.pk):
                    self.assertEqual(self.post(CHOICES, user_id=target.pk).status_code, 400)
                    self.assertEqual(self.post({**CHOICES, "user_id": target.pk}).status_code, 400)
                    response = self.client.post(
                        f"/api/character/avatar/?user_id={target.pk}", {"avatar_preferences": CHOICES}, format="json",
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(self.snapshot(), before)

    def test_each_role_saves_only_its_own_profile(self):
        for actor in (self.sibling, self.parent, self.foreign_parent, self.outsider):
            self.sign_in(actor)
            response = self.post(CHOICES)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["username"], actor.username)
            self.assertEqual(CharacterProfile.objects.get(user=actor).avatar_preferences, CHOICES)
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.avatar_preferences, {})

    def test_anonymous_or_revoked_session_cannot_save(self):
        before = self.snapshot()
        self.client.credentials()
        self.assertEqual(self.post(CHOICES).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {'0' * 40}")
        self.assertEqual(self.post(CHOICES).status_code, 401)
        self.assertEqual(self.snapshot(), before)

    def test_corrupt_saved_preferences_project_safe_defaults(self):
        for stored in ([], None, "invalid", {"hair_style": "invalid", "hair_color": "light", "extra": "unknown"}):
            with self.subTest(stored=stored):
                # JSONField is non-null; legacy invalid JSON shapes are still defensively projected.
                self.profile.avatar_preferences = stored if stored is not None else {"outfit": None}
                self.profile.save(update_fields=["avatar_preferences"])
                response = self.client.get("/api/character/")
                expected = {**AVATAR_DEFAULTS, **({"hair_color": "light"} if isinstance(stored, dict) else {})}
                self.assertEqual(response.data["avatar_preferences"], expected)
