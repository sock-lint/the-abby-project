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


IDENTITY_CHOICES = {
    "hair_style": "hair-04", "hair_color": "brown",
    "skin_tone": "tan", "outfit": "fire", "outfit_style": "archer-03", "face_style": "face-03",
    "head_style": "head-01",
}
WARDROBE_DEFAULTS = {
    "headwear_style": "none", "mask_style": "none", "bow_style": "none", "quiver_style": "none",
}
WARDROBE_CHOICES = {
    "headwear_style": "hood-mystical", "mask_style": "mask-undercover",
    "bow_style": "bow-myth", "quiver_style": "quiver-tale",
}
CHOICES = {**IDENTITY_CHOICES, **WARDROBE_CHOICES}
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

    def test_wardrobe_choices_save_and_retry_without_changing_earned_state(self):
        preferences = {**CHOICES, **WARDROBE_CHOICES}
        before = self.snapshot()
        response = self.post(preferences)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_preferences"], preferences)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, preferences)
        self.assertEqual(self.client.get("/api/character/").data, response.data)
        after = self.snapshot()
        comparable = self.snapshot()
        for profile in comparable["profiles"]:
            if profile["user_id"] == self.child.pk:
                prior = next(row for row in before["profiles"] if row["user_id"] == self.child.pk)
                profile["avatar_preferences"] = prior["avatar_preferences"]
                profile["updated_at"] = prior["updated_at"]
        self.assertEqual(comparable, before)
        with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(minutes=2)):
            repeated = self.post(preferences)
        self.assertEqual(repeated.data, response.data)
        self.assertEqual(self.snapshot(), after)

    def test_each_named_wardrobe_option_is_accepted(self):
        # Literal pack identities make this fail on the original seven-field
        # table instead of deriving acceptance from the implementation itself.
        choices = {
            "headwear_style": ("none", "crown-eve", "hood-mystical"),
            "mask_style": ("none", "mask-undercover"),
            "bow_style": ("none", "bow-greenhorn", "bow-vines", "bow-myth"),
            "quiver_style": ("none", "quiver-angel", "quiver-rook", "quiver-tale"),
        }
        for key, values in choices.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    expected = {**CHOICES, **WARDROBE_DEFAULTS, key: value}
                    response = self.post(expected)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data["avatar_preferences"], expected)

    def test_legacy_seven_option_appearance_projects_no_wardrobe_without_writes(self):
        self.profile.avatar_preferences = IDENTITY_CHOICES
        self.profile.save(update_fields=["avatar_preferences"])
        before = self.snapshot()
        response = self.client.get("/api/character/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_preferences"], {**IDENTITY_CHOICES, **WARDROBE_DEFAULTS})
        self.assertEqual(self.snapshot(), before)

    def test_omitted_wardrobe_options_reset_to_none_independently(self):
        preferences = {**CHOICES, **WARDROBE_CHOICES}
        for key in WARDROBE_DEFAULTS:
            with self.subTest(key=key):
                self.assertEqual(self.post(preferences).status_code, 200)
                response = self.post({field: value for field, value in preferences.items() if field != key})
                expected = {**preferences, key: "none"}
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["avatar_preferences"], expected)
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.avatar_preferences, expected)

    def test_wardrobe_fields_in_query_parameters_are_rejected_without_writes(self):
        before = self.snapshot()
        for key, value in WARDROBE_CHOICES.items():
            with self.subTest(key=key):
                response = self.client.post(
                    f"/api/character/avatar/?{key}={value}", {"avatar_preferences": {}}, format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(), before)

    def test_expanded_hair_colors_and_costumes_are_accepted_independently(self):
        # Keep these literal choices independent of the server option table so
        # this acceptance test fails before the expanded identity is supported.
        for costume in ("archer-01", "archer-02", "archer-03"):
            for hair_color in ("brown", "orange", "grey"):
                with self.subTest(costume=costume, hair_color=hair_color):
                    preferences = {**CHOICES, "outfit_style": costume, "hair_color": hair_color}
                    response = self.post(preferences)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data["avatar_preferences"], preferences)
                    self.profile.refresh_from_db()
                    self.assertEqual(self.profile.avatar_preferences, preferences)

    def test_all_three_verified_faces_are_accepted(self):
        for face_style in ("face-01", "face-02", "face-03"):
            with self.subTest(face_style=face_style):
                preferences = {**CHOICES, "face_style": face_style}
                response = self.post(preferences)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["avatar_preferences"], preferences)
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.avatar_preferences, preferences)

    def test_both_verified_heads_are_accepted(self):
        for head_style in ("head-01", "head-02"):
            with self.subTest(head_style=head_style):
                preferences = {**CHOICES, "head_style": head_style}
                response = self.post(preferences)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["avatar_preferences"], preferences)
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.avatar_preferences, preferences)

    def test_legacy_appearance_keeps_choices_and_projects_default_costume_without_writes(self):
        for hair_color in ("dark", "light"):
            with self.subTest(hair_color=hair_color):
                legacy = {
                    "hair_style": "hair-03", "hair_color": hair_color,
                    "skin_tone": "tan", "outfit": "aqua",
                }
                self.profile.avatar_preferences = legacy
                self.profile.save(update_fields=["avatar_preferences"])
                before = self.snapshot()
                response = self.client.get("/api/character/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["avatar_preferences"], {
                    **legacy, "outfit_style": "archer-01", "face_style": "face-01", "head_style": "head-02",
                    **WARDROBE_DEFAULTS,
                })
                self.assertEqual(self.snapshot(), before)

    def test_omitting_costume_in_a_save_resets_it_to_the_original_style(self):
        self.assertEqual(self.post(CHOICES).status_code, 200)
        legacy = {key: value for key, value in CHOICES.items() if key != "outfit_style"}
        response = self.post(legacy)
        self.assertEqual(response.status_code, 200)
        expected = {**legacy, "outfit_style": "archer-01"}
        self.assertEqual(response.data["avatar_preferences"], expected)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, expected)

    def test_omitting_face_in_a_save_resets_it_to_the_original_style(self):
        self.assertEqual(self.post(CHOICES).status_code, 200)
        legacy = {key: value for key, value in CHOICES.items() if key != "face_style"}
        response = self.post(legacy)
        self.assertEqual(response.status_code, 200)
        expected = {**legacy, "face_style": "face-01"}
        self.assertEqual(response.data["avatar_preferences"], expected)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, expected)

    def test_omitting_head_in_a_save_resets_it_to_the_existing_pointed_ears(self):
        self.assertEqual(self.post(CHOICES).status_code, 200)
        legacy = {key: value for key, value in CHOICES.items() if key != "head_style"}
        response = self.post(legacy)
        self.assertEqual(response.status_code, 200)
        expected = {**legacy, "head_style": "head-02"}
        self.assertEqual(response.data["avatar_preferences"], expected)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_preferences, expected)

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
