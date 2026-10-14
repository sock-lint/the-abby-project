"""Shared equipment saves use reviewed bindings, not pack origin or earned items."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.rewards.models import CoinLedger
from apps.rpg import avatar
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests.factories import make_family


SLOTS = ["headwear", "face_accessory", "left_hand", "right_hand", "back"]
ARCHER_APPEARANCE = {
    "hair_style": "hair-01", "hair_color": "dark", "skin_tone": "fair", "outfit": "nature",
    "outfit_style": "archer-01", "face_style": "face-01", "head_style": "head-02",
}
NONE_ACCESSORIES = dict.fromkeys(SLOTS, "none")
SYNTHETIC_KNIGHT = {
    "id": "synthetic-knight", "label": "Synthetic Knight", "renderer_adapter": "synthetic-knight",
    "defaults": {"appearance": {"armor_style": "training"}, "accessories": NONE_ACCESSORIES},
    "groups": [
        {"id": "armor", "label": "Armor", "fields": [{
            "key": "armor_style", "label": "Armor", "choices": [
                {"value": "training", "label": "Training"}, {"value": "ceremonial", "label": "Ceremonial"},
            ],
        }]},
        {"id": "equipment", "label": "Equipment", "fields": [
            {"key": slot, "label": slot, "accessory_slot": slot} for slot in SLOTS
        ]},
    ],
    "accessory_bindings": {
        "headwear": {"item_ids": [], "attachment": None, "legacy_preference_key": None},
        "face_accessory": {"item_ids": [], "attachment": None, "legacy_preference_key": None},
        "left_hand": {"item_ids": ["bow-greenhorn", "synthetic-shield"], "attachment": "SyntheticKnightLeftHand", "legacy_preference_key": None},
        "right_hand": {"item_ids": ["synthetic-sword"], "attachment": "SyntheticKnightRightHand", "legacy_preference_key": None},
        "back": {"item_ids": ["quiver-rook"], "attachment": "SyntheticKnightBack", "legacy_preference_key": None},
    },
    "presets": [{"id": "guard", "label": "Guard", "appearance": {"armor_style": "ceremonial"},
                 "accessories": {"left_hand": "synthetic-shield", "right_hand": "synthetic-sword"}}],
}
SYNTHETIC_ITEMS = {
    "bow-greenhorn": {"label": "Greenhorn bow", "source_pack": "meshtint-female-archer-01"},
    "quiver-rook": {"label": "Rook quiver", "source_pack": "meshtint-female-archer-01"},
    "synthetic-shield": {"label": "Synthetic shield", "source_pack": "synthetic-knight-pack"},
    "synthetic-sword": {"label": "Synthetic sword", "source_pack": "synthetic-knight-pack"},
}


@contextmanager
def synthetic_registry():
    definitions = {**getattr(avatar, "AVATAR_DEFINITIONS", {}), "synthetic-knight": deepcopy(SYNTHETIC_KNIGHT)}
    items = {**getattr(avatar, "SHARED_ACCESSORIES", {}), **deepcopy(SYNTHETIC_ITEMS)}
    with patch.object(avatar, "AVATAR_DEFINITIONS", definitions, create=True), patch.object(
        avatar, "SHARED_ACCESSORIES", items, create=True,
    ):
        yield


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AvatarConfigurationTests(APITestCase):
    def setUp(self):
        family = make_family(
            "Avatar configuration family", parents=[{"username": "avatar-config-parent"}],
            children=[{"username": "avatar-config-child"}, {"username": "avatar-config-sibling"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        self.outsider = make_family(
            "Other avatar configuration family", children=[{"username": "avatar-config-outsider"}],
        ).children[0]
        self.profile = CharacterProfile.objects.get(user=self.child)
        self.profile.avatar_preferences = {**avatar.AVATAR_DEFAULTS, "hair_color": "grey"}
        self.profile.level = 7
        self.profile.unlocks = {"earlier": True}
        self.profile.save()
        item = ItemDefinition.objects.create(name="Previously earned configuration frame", item_type="cosmetic_frame")
        UserInventory.objects.create(user=self.child, item=item, quantity=1)
        CoinLedger.objects.create(user=self.child, amount=29, reason="adjustment")
        self.sign_in(self.child)

    def sign_in(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def snapshot(self):
        return {
            "profiles": list(CharacterProfile.objects.order_by("id").values()),
            "users": list(type(self.child).objects.order_by("id").values()),
            "coins": list(CoinLedger.objects.order_by("id").values()),
            "inventory": list(UserInventory.objects.order_by("id").values()),
        }

    def config(self, avatar_id="female-archer", appearance=None, **accessories):
        base = ARCHER_APPEARANCE if avatar_id == "female-archer" else {"armor_style": "training"}
        return {"avatar_id": avatar_id, "appearance": {**base, **(appearance or {})},
                "accessories": {**NONE_ACCESSORIES, **accessories}}

    def post(self, configuration):
        return self.client.post("/api/character/avatar/configuration/", {"avatar_configuration": configuration}, format="json")

    def assert_confirmed(self, configuration):
        response = self.post(configuration)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["avatar_configuration"], configuration)
        return response.json()

    def assert_earned_unchanged(self, before):
        after = self.snapshot()
        for state in (before, after):
            for profile in state["profiles"]:
                if profile["user_id"] == self.child.pk:
                    for key in ("avatar_preferences", "avatar_configuration", "updated_at"):
                        profile.pop(key, None)
        self.assertEqual(after, before)

    def test_generic_save_syncs_archer_legacy_preferences_and_retries_without_writes(self):
        configuration = self.config(appearance={"hair_color": "orange", "outfit": "fire"},
                                    left_hand="bow-vines", back="quiver-tale", headwear="crown-eve")
        before = self.snapshot()
        confirmed = self.assert_confirmed(configuration)
        self.assertEqual(confirmed["avatar_preferences"], {
            **avatar.AVATAR_DEFAULTS, "hair_color": "orange", "outfit": "fire",
            "bow_style": "bow-vines", "quiver_style": "quiver-tale", "headwear_style": "crown-eve",
        })
        self.assert_earned_unchanged(before)
        before_retry = self.snapshot()
        with patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(hours=1)):
            self.assertEqual(self.assert_confirmed(configuration), confirmed)
        self.assertEqual(self.snapshot(), before_retry)
        self.assertEqual(self.client.get("/api/character/").json()["avatar_configuration"], configuration)

    def test_legacy_projection_and_equal_legacy_retry_do_not_materialize_generic_json(self):
        before = self.snapshot()
        expected = self.config(appearance={"hair_color": "grey"})
        self.assertEqual(self.client.get("/api/character/").json()["avatar_configuration"], expected)
        self.assertEqual(self.client.get("/api/character/avatar/configuration/").json()["avatar_configuration"], expected)
        self.assertEqual(self.snapshot(), before)
        response = self.client.post("/api/character/avatar/", {
            "avatar_preferences": {**avatar.AVATAR_DEFAULTS, "hair_color": "grey"},
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["avatar_configuration"], expected)
        self.assertEqual(self.snapshot(), before)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_configuration, {})

    def test_reads_preserve_unavailable_saved_body_and_equipment_without_writes(self):
        unavailable = {"avatar_id": "retired-base", "appearance": {"retired_field": "saved"},
                       "accessories": {"left_hand": "retired-sword", "future_slot": "earlier-item"}}
        CharacterProfile.objects.filter(pk=self.profile.pk).update(avatar_configuration=unavailable)
        before = self.snapshot()
        for url in ("/api/character/", "/api/character/avatar/configuration/"):
            self.assertEqual(self.client.get(url).json()["avatar_configuration"], unavailable)
        self.assertEqual(self.snapshot(), before)

    def test_configuration_read_ignores_only_the_noncredential_session_cache_namespace(self):
        before = self.snapshot()
        response = self.client.get("/api/character/avatar/configuration/?_abby_session=synthetic-cache-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["avatar_configuration"], self.config(appearance={"hair_color": "grey"}))
        self.assertEqual(self.client.get(
            f"/api/character/avatar/configuration/?_abby_session=synthetic-cache-key&user_id={self.outsider.pk}",
        ).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_registered_knight_saves_archer_bow_quiver_and_knight_sword_without_source_restriction(self):
        with synthetic_registry():
            # An explicit binding is the rule. Public provenance cannot act as
            # an ownership or same-pack requirement, even if it changes.
            avatar.SHARED_ACCESSORIES["bow-greenhorn"]["source_pack"] = "another-synthetic-source"
            configuration = self.config("synthetic-knight", {"armor_style": "ceremonial"},
                                        left_hand="bow-greenhorn", back="quiver-rook", right_hand="synthetic-sword")
            before = self.snapshot()
            confirmed = self.assert_confirmed(configuration)
            self.assertEqual(confirmed["avatar_preferences"], {**avatar.AVATAR_DEFAULTS, "hair_color": "grey"})
            self.assert_earned_unchanged(before)
            configuration["accessories"]["left_hand"] = "synthetic-shield"
            self.assert_confirmed(configuration)
        catalog = self.client.get("/api/character/avatar/catalog/").json()
        self.assertEqual([entry["id"] for entry in catalog["avatars"]], ["female-archer"])
        self.assertNotIn("synthetic-sword", catalog["accessories"])

    def test_base_switch_keeps_shared_pieces_and_requires_explicit_removal_of_unfit_equipment(self):
        with synthetic_registry():
            self.assert_confirmed(self.config("synthetic-knight", left_hand="bow-greenhorn", back="quiver-rook",
                                              right_hand="synthetic-sword"))
            switch = self.config(left_hand="bow-greenhorn", back="quiver-rook", right_hand="synthetic-sword")
            before = self.snapshot()
            self.assertEqual(self.post(switch).status_code, 400)
            self.assertEqual(self.snapshot(), before)
            switch["accessories"]["right_hand"] = "none"
            self.assert_confirmed(switch)
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.avatar_preferences["bow_style"], "bow-greenhorn")
            self.assertEqual(self.profile.avatar_preferences["quiver_style"], "quiver-rook")

    def test_legacy_save_explicitly_selects_archer_and_keeps_configuration_synchronized(self):
        with synthetic_registry():
            self.assert_confirmed(self.config("synthetic-knight", left_hand="synthetic-shield"))
            response = self.client.post("/api/character/avatar/", {
                "avatar_preferences": {**avatar.AVATAR_DEFAULTS, "bow_style": "bow-myth"},
            }, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["avatar_configuration"], self.config(left_hand="bow-myth"))

    def test_generic_replacement_defaults_omitted_choices_but_requires_explicit_base(self):
        self.assert_confirmed(self.config(left_hand="bow-myth", back="quiver-tale"))
        response = self.post({"avatar_id": "female-archer"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["avatar_configuration"], self.config())
        before = self.snapshot()
        self.assertEqual(self.post({}).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_unregistered_and_unfit_configuration_cannot_change_state(self):
        before = self.snapshot()
        invalid = [None, [], False, {"avatar_id": "synthetic-knight"}, {"avatar_id": False},
                   {"avatar_id": "female-archer", "unlocks": {}},
                   {"avatar_id": "female-archer", "appearance": []},
                   {"avatar_id": "female-archer", "appearance": {"armor_style": "training"}},
                   {"avatar_id": "female-archer", "appearance": {"hair_color": 7}},
                   {"avatar_id": "female-archer", "accessories": None},
                   {"avatar_id": "female-archer", "accessories": {"future_slot": "none"}},
                   self.config(left_hand="quiver-rook"), self.config(back="unknown-item"),
                   self.config(right_hand="bow-greenhorn"), self.config(left_hand={"id": "bow-myth"})]
        for configuration in invalid:
            with self.subTest(configuration=configuration):
                self.assertEqual(self.post(configuration).status_code, 400)
                self.assertEqual(self.snapshot(), before)

    def test_configuration_authentication_and_account_targeting_remain_self_only(self):
        before = self.snapshot()
        for query in (f"user_id={self.sibling.pk}", f"user_id={self.outsider.pk}", "unexpected=true", "_abby_session=synthetic-cache-key"):
            response = self.client.post(f"/api/character/avatar/configuration/?{query}", {
                "avatar_configuration": self.config(),
            }, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/api/character/avatar/configuration/", {
            "avatar_configuration": self.config(), "user_id": self.outsider.pk,
        }, format="json").status_code, 400)
        self.assertEqual(self.snapshot(), before)
        self.client.credentials()
        self.assertEqual(self.post(self.config()).status_code, 401)
        self.sign_in(self.child)
        Token.objects.filter(user=self.child).delete()
        self.assertEqual(self.post(self.config()).status_code, 401)
        self.assertEqual(self.snapshot(), before)

    def test_each_role_replaces_only_its_own_configuration_and_inactive_accounts_cannot_save(self):
        for actor, color in ((self.child, "brown"), (self.parent, "orange"), (self.outsider, "grey")):
            self.sign_in(actor)
            before = {row["user_id"]: row for row in CharacterProfile.objects.values()}
            configuration = self.config(appearance={"hair_color": color}, back="quiver-rook")
            self.assert_confirmed(configuration)
            after = {row["user_id"]: row for row in CharacterProfile.objects.values()}
            for user_id, row in before.items():
                if user_id != actor.pk:
                    self.assertEqual(after[user_id], row)
        self.sign_in(self.child)
        type(self.child).objects.filter(pk=self.child.pk).update(is_active=False)
        before = self.snapshot()
        self.assertEqual(self.post(self.config()).status_code, 401)
        self.assertEqual(self.snapshot(), before)
