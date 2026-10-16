"""Color-theme labels agree across inventory, drops and reward surfaces."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.pets.expeditions import ExpeditionService
from apps.quests.models import QuestDefinition, QuestRewardItem
from apps.quests.serializers import QuestRewardItemSerializer
from apps.rpg.catalog_icons import item_catalog_icon
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from apps.rpg.serializers import CharacterProfileSerializer, DropLogSerializer, ItemDefinitionSerializer
from apps.rpg.services import CosmeticService, DropService
from config.tests.factories import make_family


THEMES = (
    ("hyrule", "Hyrule Day", "Memory Meadow"),
    ("vigil", "Night Vigil", "Twilight Meadow"),
    ("sunlit", "Sunlit Field", "Honey Meadow"),
    ("snowquill", "Snowquill Tome", "Cloud Meadow"),
    ("verdant", "Verdant Pages", "Clover Meadow"),
    ("harvest", "Harvest Folio", "Peach Meadow"),
    ("summer", "Summer", "Honey Meadow"),
    ("winter", "Winter", "Cloud Meadow"),
    ("spring", "Spring", "Clover Meadow"),
    ("autumn", "Autumn", "Peach Meadow"),
)


class ThemeLabelTests(SimpleTestCase):
    def test_current_and_legacy_keys_project_current_names_without_rewriting_catalog(self):
        for key, stored_name, label in THEMES:
            with self.subTest(key=key):
                item = ItemDefinition(
                    id=1, slug=f"cover-{key}", name=stored_name, icon="T",
                    item_type="cosmetic_theme", metadata={"theme": key},
                )
                expected_icon = item_catalog_icon(item)
                serialized = ItemDefinitionSerializer(item).data
                self.assertEqual(serialized["name"], label)
                self.assertEqual(serialized["type_display"], "Color theme")
                self.assertEqual(serialized["catalog_icon"], expected_icon)
                self.assertEqual(CharacterProfileSerializer._compact_item(item)["name"], label)
                self.assertEqual(DropLogSerializer(DropLog(item=item))["item_name"].value, label)
                self.assertEqual(QuestRewardItemSerializer(QuestRewardItem(item=item))["item_name"].value, label)
                self.assertEqual(item.name, stored_name)
                self.assertEqual(item.metadata, {"theme": key})

    def test_other_catalog_names_and_unknown_theme_keepsakes_are_preserved(self):
        for item_type, metadata in (
            ("cosmetic_title", {"theme": "hyrule"}),
            ("cosmetic_theme", {"theme": "unknown"}),
            ("cosmetic_theme", {}),
        ):
            with self.subTest(item_type=item_type, metadata=metadata):
                item = ItemDefinition(name="My saved name", item_type=item_type, metadata=metadata)
                self.assertEqual(ItemDefinitionSerializer(item).data["name"], "My saved name")


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None)
class ThemeSurfaceTests(APITestCase):
    def setUp(self):
        family = make_family(
            "Theme labels", parents=[{"username": "theme-parent", "is_staff": True}],
            children=[{"username": "theme-child"}],
        )
        self.child = family.children[0]
        self.parent = family.parents[0]
        self.client.force_authenticate(self.child)
        self.cover = ItemDefinition.objects.create(
            slug="cover-vigil", name="Night Vigil", icon="T", item_type="cosmetic_theme",
            metadata={"theme": "vigil"}, coin_value=20,
        )

    def test_inventory_catalog_character_and_equip_use_the_same_current_label(self):
        UserInventory.objects.create(user=self.child, item=self.cover)
        inventory = self.client.get("/api/inventory/").json()
        self.assertEqual(inventory[0]["item"]["name"], "Twilight Meadow")
        catalog = self.client.get("/api/cosmetics/catalog/").json()
        self.assertEqual(catalog["active_theme"][0]["name"], "Twilight Meadow")
        equipped = CosmeticService.equip(self.child, self.cover.pk)
        self.assertEqual(equipped["item_name"], "Twilight Meadow")
        character = self.client.get("/api/character/").json()
        self.assertEqual(character["active_theme"]["name"], "Twilight Meadow")
        self.cover.refresh_from_db()
        self.assertEqual(self.cover.name, "Night Vigil")
        self.child.refresh_from_db()
        self.assertEqual(self.child.theme, "vigil")

    @patch("apps.rpg.services.random.random", return_value=0)
    def test_new_drop_and_salvage_receipts_keep_current_labels_and_original_art_binding(self, _roll):
        DropTable.objects.create(trigger_type="clock_out", item=self.cover, weight=1)
        for salvaged in (False, True):
            with self.subTest(salvaged=salvaged):
                result = DropService.process_drops(self.child, "clock_out")[0]
                self.assertEqual(result["item_name"], "Twilight Meadow")
                self.assertEqual(result["item_catalog_icon"], "item-cover-vigil")
                self.assertEqual(result["was_salvaged"], salvaged)
                drops = self.client.get("/api/drops/recent/").json()
                self.assertEqual(drops[0]["item_name"], "Twilight Meadow")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.cover).quantity, 1)

    def test_challenge_catalog_reward_labels_match_the_theme_picker(self):
        definition = QuestDefinition.objects.create(name="Theme prize", quest_type="collection", target_value=1)
        QuestRewardItem.objects.create(quest_definition=definition, item=self.cover, quantity=1)
        self.client.force_authenticate(self.parent)
        response = self.client.get("/api/quests/catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["reward_items"][0]["item_name"], "Twilight Meadow")

    def test_new_expedition_loot_freezes_the_current_theme_name(self):
        DropTable.objects.create(trigger_type="expedition_returned", item=self.cover, weight=1)
        loot = ExpeditionService._roll_loot(self.child, "short")
        self.assertEqual(loot["items"][0]["name"], "Twilight Meadow")
        self.assertEqual(loot["items"][0]["item_id"], self.cover.pk)

    @override_settings(DEV_TOOLS_ENABLED=True)
    def test_development_item_selector_and_drop_result_match_the_current_theme_name(self):
        self.client.force_authenticate(self.parent)
        selector = self.client.get("/api/dev/items/")
        self.assertEqual(selector.status_code, 200)
        self.assertEqual(selector.json()[0]["name"], "Twilight Meadow")
        drop = self.client.post("/api/dev/force-drop/", {
            "user_id": self.child.pk, "slug": self.cover.slug,
        }, format="json")
        self.assertEqual(drop.status_code, 200)
        self.assertEqual(drop.json()["item"]["name"], "Twilight Meadow")
