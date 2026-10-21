"""Catalog acquisition hints reflect the accomplishment pools actually drawn."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.rpg.catalog_support import random_item_is_available
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class AccomplishmentAcquisitionSourceTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "accomplishment-hint-child"}]).children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def cosmetic(self, trigger, *, rarity="uncommon"):
        item = ItemDefinition.objects.create(
            name=f"{trigger} {rarity} title",
            item_type=ItemDefinition.ItemType.COSMETIC_TITLE, rarity=rarity,
        )
        DropTable.objects.create(trigger_type=trigger, item=item, weight=1)
        return item

    def catalog_row(self, item):
        response = self.client.get("/api/cosmetics/catalog/")
        self.assertEqual(response.status_code, 200)
        return next(row for row in response.data["active_title"] if row["id"] == item.pk)

    def test_common_cosmetic_does_not_advertise_the_uncommon_perfect_day_pool(self):
        item = self.cosmetic(TriggerType.PERFECT_DAY, rarity="common")

        self.assertEqual(self.catalog_row(item)["acquisition_sources"], [])

    def test_quest_completion_bonus_drop_is_advertised_as_an_acquisition_source(self):
        item = self.cosmetic(TriggerType.QUEST_COMPLETE)

        sources = self.catalog_row(item)["acquisition_sources"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["kind"], "drop")
        self.assertEqual(sources[0]["path"], "/quests?tab=trials")
        self.assertTrue(sources[0]["name"])

    def test_uncommon_perfect_day_cosmetic_keeps_its_drop_acquisition_hint(self):
        item = self.cosmetic(TriggerType.PERFECT_DAY)

        self.assertEqual(self.catalog_row(item)["acquisition_sources"], [
            {"kind": "drop", "name": "Perfect Days", "path": "/quests?tab=trials"},
        ])

    def test_earned_elemental_potions_keep_only_their_guaranteed_challenge_hints(self):
        call_command("loadrpgcontent", stdout=StringIO())
        potions = {
            element: ItemDefinition.objects.get(slug=f"{element}-potion")
            for element in ("fire", "ice")
        }
        food = ItemDefinition.objects.create(
            slug="elemental-hint-allowed-food", name="Completion snack", item_type="food",
        )
        DropTable.objects.create(trigger_type=TriggerType.QUEST_COMPLETE, item=food)
        for item in (*potions.values(), food):
            UserInventory.objects.create(user=self.child, item=item, quantity=1)

        response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 200)
        items = {row["item"]["id"]: row["item"] for row in response.data}
        for element, names in (("fire", ["Ember Nest", "Ember Trail"]),
                               ("ice", ["Frost Nest", "Frost Trail"])):
            with self.subTest(element=element):
                potion = potions[element]
                self.assertTrue(DropTable.objects.filter(item=potion, weight__gt=0).exists())
                self.assertTrue(items[potion.pk]["catalog_available"])
                self.assertFalse(random_item_is_available(potion))
                self.assertEqual(items[potion.pk]["acquisition_sources"], [
                    {"kind": "challenge", "name": name, "path": "/quests?tab=trials"}
                    for name in names
                ])
        self.assertTrue(random_item_is_available(food))
        self.assertEqual(items[food.pk]["acquisition_sources"], [
            {"kind": "drop", "name": "completed challenges", "path": "/quests?tab=trials"},
        ])
