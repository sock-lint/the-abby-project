"""Authenticated metadata shares item IDs without assuming a pack or gear class."""
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.rewards.models import CoinLedger
from apps.rpg import avatar
from apps.rpg.models import CharacterProfile, DropLog, ItemDefinition, UserInventory
from apps.rpg.tests.test_avatar_configuration import SYNTHETIC_ITEMS, SYNTHETIC_KNIGHT
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AvatarCatalogTests(APITestCase):
    def setUp(self):
        family = make_family("Avatar catalog family", parents=[{"username": "avatar-catalog-parent"}],
                             children=[{"username": "avatar-catalog-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.outsider = make_family("Other avatar catalog family", children=[{"username": "avatar-catalog-outsider"}]).children[0]
        self.profile = CharacterProfile.objects.get(user=self.child)
        self.profile.avatar_preferences = {"hair_style": "hair-02", "outfit": "aqua"}
        self.profile.level = 5
        self.profile.unlocks = {"existing": True}
        self.profile.save()
        frame = ItemDefinition.objects.create(name="Existing catalog-test frame", item_type="cosmetic_frame")
        UserInventory.objects.create(user=self.child, item=frame, quantity=1)
        CoinLedger.objects.create(user=self.child, amount=31, reason="adjustment")
        self.sign_in(self.child)

    def sign_in(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def snapshot(self):
        return {"profiles": list(CharacterProfile.objects.order_by("id").values()),
                "users": list(type(self.child).objects.order_by("id").values()),
                "coins": list(CoinLedger.objects.order_by("id").values()),
                "inventory": list(UserInventory.objects.order_by("id").values()),
                "drops": list(DropLog.objects.order_by("id").values())}

    def catalog(self):
        response = self.client.get("/api/character/avatar/catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        return response.json()

    def test_catalog_declares_only_registered_avatar_controls_for_each_authenticated_role(self):
        for actor in (self.child, self.parent, self.outsider):
            with self.subTest(role=actor.role, family=actor.family_id):
                self.sign_in(actor)
                catalog = self.catalog()
                self.assertEqual(set(catalog), {"schema_version", "default_avatar_id", "accessory_slots", "accessories", "avatars"})
                self.assertEqual(catalog["schema_version"], 1)
                self.assertEqual(catalog["default_avatar_id"], "female-archer")
                self.assertEqual([entry["id"] for entry in catalog["avatars"]], ["female-archer"])
                self.assertEqual([slot["id"] for slot in catalog["accessory_slots"]], ["headwear", "face_accessory", "left_hand", "right_hand", "back"])
                definition = catalog["avatars"][0]
                self.assertEqual(definition["renderer_adapter"], "female-archer")
                self.assertEqual([group["id"] for group in definition["groups"]], ["identity", "wardrobe"])
                fields = [field for group in definition["groups"] for field in group["fields"]]
                self.assertEqual([field["key"] for field in fields], [
                    "outfit_style", "hair_style", "hair_color", "face_style", "head_style", "skin_tone", "outfit",
                    "headwear", "face_accessory", "left_hand", "right_hand", "back",
                ])
                for field in fields:
                    slot = field.get("accessory_slot")
                    if slot is None:
                        self.assertEqual(tuple(choice["value"] for choice in field["choices"]), avatar.AVATAR_OPTIONS[field["key"]])
                        self.assertIn(definition["defaults"]["appearance"][field["key"]], [choice["value"] for choice in field["choices"]])
                    else:
                        binding = definition["accessory_bindings"][slot]
                        self.assertEqual([choice["value"] for choice in field["choices"]], ["none", *binding["item_ids"]])
                        for choice in field["choices"][1:]:
                            self.assertEqual(choice["value"], choice["accessory_id"])
                            self.assertIn(choice["accessory_id"], catalog["accessories"])
                        legacy_key = binding["legacy_preference_key"]
                        if legacy_key is not None:
                            self.assertEqual(tuple(choice["value"] for choice in field["choices"]), avatar.AVATAR_OPTIONS[legacy_key])
                self.assertEqual([preset["id"] for preset in definition["presets"]], ["aqua", "nature", "fire", "dark"])
                self.assertNotIn(actor.username, str(catalog))

    def test_catalog_get_preserves_legacy_preferences_and_all_existing_state(self):
        before = self.snapshot()
        first = self.catalog()
        self.assertEqual(self.catalog(), first)
        self.assertEqual(self.snapshot(), before)
        CharacterProfile.objects.filter(user=self.child).delete()
        before = self.snapshot()
        self.assertEqual(self.catalog(), first)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(CharacterProfile.objects.filter(user=self.child).exists())

    def test_catalog_requires_active_authentication(self):
        self.client.credentials()
        self.assertEqual(self.client.get("/api/character/avatar/catalog/").status_code, 401)
        self.sign_in(self.child)
        Token.objects.filter(user=self.child).delete()
        self.assertEqual(self.client.get("/api/character/avatar/catalog/").status_code, 401)
        self.sign_in(self.child)
        type(self.child).objects.filter(pk=self.child.pk).update(is_active=False)
        self.assertEqual(self.client.get("/api/character/avatar/catalog/").status_code, 401)

    def test_ignored_session_cache_namespace_keeps_catalog_get_compatible_with_the_client(self):
        expected = self.catalog()
        before = self.snapshot()
        response = self.client.get("/api/character/avatar/catalog/?_abby_session=synthetic-cache-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        self.assertEqual(self.client.get(
            f"/api/character/avatar/catalog/?_abby_session=synthetic-cache-key&user_id={self.outsider.pk}",
        ).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_catalog_rejects_account_targeting_and_write_methods_without_state_changes(self):
        before = self.snapshot()
        for query in (f"user_id={self.outsider.pk}", "avatar_id=synthetic-knight", "unrecognized=true"):
            self.assertEqual(self.client.get(f"/api/character/avatar/catalog/?{query}").status_code, 400)
        for method in (self.client.post, self.client.patch, self.client.delete):
            self.assertEqual(method("/api/character/avatar/catalog/", {"level": 99}, format="json").status_code, 405)
        self.assertEqual(self.snapshot(), before)

    def test_catalog_presets_save_without_replacing_identity_or_earned_state(self):
        definition = self.catalog()["avatars"][0]
        identity = {**definition["defaults"]["appearance"], "hair_style": "hair-04", "hair_color": "grey",
                    "skin_tone": "tan", "outfit_style": "archer-03", "face_style": "face-03", "head_style": "head-01"}
        for preset in definition["presets"]:
            with self.subTest(preset=preset["id"]):
                choices = {"avatar_id": definition["id"], "appearance": {**identity, **preset["appearance"]},
                           "accessories": {**definition["defaults"]["accessories"], **preset["accessories"]}}
                before = self.snapshot()
                response = self.client.post("/api/character/avatar/configuration/", {"avatar_configuration": choices}, format="json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["avatar_configuration"], choices)
                after = self.snapshot()
                for state in (before, after):
                    for profile in state["profiles"]:
                        if profile["user_id"] == self.child.pk:
                            for key in ("avatar_preferences", "avatar_configuration", "updated_at"):
                                profile.pop(key)
                self.assertEqual(after, before)

    def test_synthetic_knight_catalog_reuses_archer_ids_with_its_own_bindings(self):
        registry = {"synthetic-knight": SYNTHETIC_KNIGHT}
        items = {**avatar.SHARED_ACCESSORIES, **SYNTHETIC_ITEMS}
        catalog = avatar.avatar_catalog(registry, default_avatar_id="synthetic-knight", accessories=items)
        knight = catalog["avatars"][0]
        self.assertEqual(avatar.avatar_options("synthetic-knight", definitions=registry), {"armor_style": ("training", "ceremonial")})
        fields = {field["key"]: field for group in knight["groups"] for field in group["fields"]}
        self.assertEqual([choice["value"] for choice in fields["left_hand"]["choices"]], ["none", "bow-greenhorn", "synthetic-shield"])
        self.assertEqual([choice["value"] for choice in fields["back"]["choices"]], ["none", "quiver-rook"])
        self.assertEqual(knight["accessory_bindings"]["left_hand"]["attachment"], "SyntheticKnightLeftHand")
        self.assertEqual(catalog["accessories"]["bow-greenhorn"]["source_pack"], "meshtint-female-archer-01")
        production = self.catalog()
        self.assertEqual([entry["id"] for entry in production["avatars"]], ["female-archer"])
        self.assertNotIn("synthetic-shield", production["accessories"])
