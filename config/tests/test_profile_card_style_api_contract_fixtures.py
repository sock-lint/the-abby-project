"""Real cosmetic and character responses share server-bound card presentation."""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None)
class ProfileCardStyleApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        # Prior account history must not determine the fixture's profile ID.
        previous = make_family("Prior profile", children=[{"username": "prior-card-style-child"}]).children[0]
        previous.delete()
        self.child = make_family(
            "Profile card fixture family", family_id=81,
            children=[{"id": 7, "username": "card-style-fixture-child"}],
        ).children[0]
        self.nature = ItemDefinition.objects.create(
            id=401, slug="frame-robin-hood", name="Ranger's Cap Frame", icon="🪖", sprite_key="robin-hood-hat",
            item_type="cosmetic_frame", rarity="rare", coin_value=35,
            metadata={"border_color": "#3A8B3A", "card_asset_id": "card-front-legendary"},
        )
        self.light = ItemDefinition.objects.create(
            id=402, slug="frame-scholar", name="Scholar Frame", icon="📖",
            item_type="cosmetic_frame", rarity="rare", coin_value=35,
            metadata={"border_color": "#8B5A2B"},
        )
        self.unbound = ItemDefinition.objects.create(
            id=403, slug="frame-gold", name="Gold Frame", icon="🟨",
            item_type="cosmetic_frame", rarity="rare", coin_value=30,
            metadata={"border_color": "#FFD700", "card_asset_id": "card-front-fire"},
        )
        UserInventory.objects.create(id=501, user=self.child, item=self.nature, quantity=1)
        CharacterProfile.objects.filter(user=self.child).update(id=1, active_frame=self.nature)
        self.client.force_authenticate(self.child)

    def test_catalog_owned_and_selected_card_styles_are_real_read_only_responses(self):
        before_inventory = list(UserInventory.objects.order_by("pk").values())
        before_profile = CharacterProfile.objects.values().get(user=self.child)
        before_items = list(ItemDefinition.objects.order_by("pk").values())
        catalog = self.assert_response_fixture(
            self.client.get("/api/cosmetics/catalog/"), "profile-card-styles-catalog.json",
        )
        owned = self.assert_response_fixture(
            self.client.get("/api/cosmetics/"), "profile-card-styles-owned.json",
        )
        character = self.assert_response_fixture(
            self.client.get("/api/character/"), "profile-card-style-character.json",
        )
        self.assertEqual({item["id"]: item["metadata"].get("card_asset_id") for item in catalog["active_frame"]}, {
            401: "card-front-nature", 402: "card-front-light", 403: None,
        })
        self.assertEqual([item["id"] for item in owned["active_frame"]], [401])
        self.assertEqual(owned["active_frame"][0]["metadata"], character["active_frame"]["metadata"])
        self.assertEqual(list(UserInventory.objects.order_by("pk").values()), before_inventory)
        self.assertEqual(CharacterProfile.objects.values().get(user=self.child), before_profile)
        self.assertEqual(list(ItemDefinition.objects.order_by("pk").values()), before_items)
