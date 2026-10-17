"""Card presentation follows exact catalog identity, never authored metadata."""
from copy import deepcopy

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, DropLog, ItemDefinition, UserInventory
from apps.rpg.serializers import CharacterProfileSerializer, ItemDefinitionSerializer
from config.tests.factories import make_family


class CardStyleProjectionTests(SimpleTestCase):
    def test_registered_frames_replace_stale_artwork_without_mutating_metadata(self):
        for slug, name, asset_id in (
            ("frame-robin-hood", "Ranger's Cap Frame", "card-front-nature"),
            ("frame-scholar", "Scholar Frame", "card-front-light"),
        ):
            with self.subTest(slug=slug):
                metadata = {
                    "border_color": "#3A8B3A", "card_asset_id": "card-front-legendary",
                    "saved_detail": {"label": "A retained custom note"},
                }
                original = deepcopy(metadata)
                item = ItemDefinition(slug=slug, name=name, item_type="cosmetic_frame", metadata=metadata)
                expected = {**original, "card_asset_id": asset_id}
                self.assertEqual(ItemDefinitionSerializer(item).data["metadata"], expected)
                self.assertEqual(CharacterProfileSerializer._compact_item(item)["metadata"], expected)
                self.assertEqual(item.metadata, original)

    def test_unregistered_or_changed_identities_cannot_select_a_card(self):
        for slug, name, kind in (
            ("custom-frame", "Ranger's Cap Frame", "cosmetic_frame"),
            ("frame-robin-hood", "A renamed custom frame", "cosmetic_frame"),
            ("frame-robin-hood", "Ranger's Cap Frame", "cosmetic_title"),
            ("frame-scholar", "Scholar Frame", "food"),
        ):
            with self.subTest(slug=slug, name=name, kind=kind):
                metadata = {"border_color": "#abcdef", "card_asset_id": "card-front-nature", "retained": True}
                item = ItemDefinition(slug=slug, name=name, item_type=kind, metadata=metadata)
                expected = {"border_color": "#abcdef", "retained": True}
                self.assertEqual(ItemDefinitionSerializer(item).data["metadata"], expected)
                self.assertEqual(CharacterProfileSerializer._compact_item(item)["metadata"], expected)
                self.assertIn("card_asset_id", item.metadata)

    def test_older_unbound_frames_keep_their_existing_metadata(self):
        metadata = {"border_color": "#FFD700", "retained": {"label": "Gold"}}
        item = ItemDefinition(slug="frame-gold", name="Gold Frame", item_type="cosmetic_frame", metadata=metadata)
        self.assertEqual(ItemDefinitionSerializer(item).data["metadata"], metadata)
        self.assertEqual(CharacterProfileSerializer._compact_item(item)["metadata"], metadata)

    def test_legacy_nonobject_metadata_is_preserved_without_an_artwork_binding(self):
        for metadata in (None, "legacy", ["legacy"], [{"card_asset_id": "card-front-light"}]):
            with self.subTest(metadata=metadata):
                item = ItemDefinition(slug="frame-scholar", name="Scholar Frame", item_type="cosmetic_frame", metadata=metadata)
                self.assertEqual(ItemDefinitionSerializer(item).data["metadata"], metadata)
                self.assertEqual(CharacterProfileSerializer._compact_item(item)["metadata"], metadata)


@override_settings(ALLOWED_HOSTS=["testserver"])
class CardStyleApiTests(APITestCase):
    def setUp(self):
        self.child = make_family("Card styles", children=[{"username": "card-style-child"}]).children[0]
        self.other = make_family("Other card styles", children=[{"username": "other-style-child"}]).children[0]
        self.nature = ItemDefinition.objects.create(
            slug="frame-robin-hood", name="Ranger's Cap Frame", icon="🪖", item_type="cosmetic_frame",
            rarity="rare", metadata={"border_color": "#3A8B3A", "card_asset_id": "card-front-fire"},
        )
        self.light = ItemDefinition.objects.create(
            slug="frame-scholar", name="Scholar Frame", icon="📖", item_type="cosmetic_frame",
            rarity="rare", metadata={"border_color": "#8B5A2B"},
        )
        UserInventory.objects.create(user=self.child, item=self.nature, quantity=1)
        UserInventory.objects.create(user=self.other, item=self.light, quantity=1)
        self.client.force_authenticate(self.child)

    def test_catalog_and_owned_reads_project_styles_without_granting_or_equipping(self):
        before_inventory = list(UserInventory.objects.order_by("pk").values())
        before_profile = CharacterProfile.objects.values().get(user=self.child)
        catalog = self.client.get("/api/cosmetics/catalog/")
        owned = self.client.get("/api/cosmetics/")
        self.assertEqual((catalog.status_code, owned.status_code), (200, 200))
        self.assertEqual({item["id"]: item["metadata"]["card_asset_id"] for item in catalog.json()["active_frame"]}, {
            self.nature.pk: "card-front-nature", self.light.pk: "card-front-light",
        })
        self.assertEqual([item["id"] for item in owned.json()["active_frame"]], [self.nature.pk])
        self.assertEqual(owned.json()["active_frame"][0]["metadata"]["card_asset_id"], "card-front-nature")
        self.assertEqual(list(UserInventory.objects.order_by("pk").values()), before_inventory)
        self.assertEqual(CharacterProfile.objects.values().get(user=self.child), before_profile)
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(DropLog.objects.exists())
        self.nature.refresh_from_db()
        self.assertEqual(self.nature.metadata["card_asset_id"], "card-front-fire")

    def test_owned_style_equip_and_unequip_keep_inventory_and_existing_border(self):
        response = self.client.post("/api/character/equip/", {"item_id": self.nature.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        profile = self.client.get("/api/character/").json()
        self.assertEqual(profile["active_frame"]["id"], self.nature.pk)
        self.assertEqual(profile["active_frame"]["metadata"], {
            "border_color": "#3A8B3A", "card_asset_id": "card-front-nature",
        })
        self.assertEqual(self.client.post("/api/character/unequip/", {"slot": "active_frame"}, format="json").status_code, 200)
        self.assertIsNone(self.client.get("/api/character/").json()["active_frame"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.nature).quantity, 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_visible_style_owned_by_another_family_cannot_be_equipped(self):
        self.assertEqual(self.client.get("/api/cosmetics/catalog/").status_code, 200)
        response = self.client.post("/api/character/equip/", {"item_id": self.light.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "You don't own that item"})
        self.assertIsNone(CharacterProfile.objects.get(user=self.child).active_frame_id)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.light).exists())
        self.assertEqual(UserInventory.objects.get(user=self.other, item=self.light).quantity, 1)
