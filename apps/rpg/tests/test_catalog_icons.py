"""Catalog image identity stays separate from sprites, ownership and rewards."""
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from apps.pets.models import PetSpecies
from apps.pets.serializers import PetSpeciesCatalogSerializer, PetSpeciesSerializer
from apps.quests.goals import create_goal, list_goals
from apps.quests.models import QuestDefinition, QuestRewardItem
from apps.quests.serializers import QuestDefinitionSerializer, QuestRewardItemSerializer
from apps.rpg.models import DropLog, ItemDefinition
from apps.rpg.serializers import DropLogSerializer, ItemDefinitionSerializer
from config.tests.factories import make_family


class CatalogImageIdentityTests(TestCase):
    def test_items_with_shared_sprites_receive_distinct_identity_art(self):
        fish = ItemDefinition(slug="food-fish", name="Fish", item_type="food", sprite_key="fish")
        cooked = ItemDefinition(slug="food-fish-cooked", name="Cooked Fish", item_type="food", sprite_key="fish")
        self.assertEqual(ItemDefinitionSerializer(fish).data.get("catalog_icon"), "item-fish")
        self.assertEqual(ItemDefinitionSerializer(cooked).data.get("catalog_icon"), "item-fish-cooked")
        for updates in ({"slug": "custom-fish"}, {"name": "Different fish"}, {"item_type": "coin_pouch"}):
            changed = ItemDefinition(slug="food-fish", name="Fish", item_type="food")
            for key, value in updates.items():
                setattr(changed, key, value)
            self.assertIsNone(ItemDefinitionSerializer(changed).data.get("catalog_icon"))

    def test_hidden_consumables_fail_closed_for_wrong_receiving_identity(self):
        for name, kind, expected in [
            ("Scholar's Draught II", "consumable", "item-scholar-draught-ii"),
            ("Scholar's Draught", "consumable", None),
            ("Scholar's Draught II", "food", None),
        ]:
            item = ItemDefinition(slug="scholar-draught-ii", name=name, item_type=kind)
            with self.subTest(name=name, kind=kind):
                self.assertEqual(ItemDefinitionSerializer(item).data.get("catalog_icon"), expected)

    def test_challenge_requires_exact_system_definition_and_type(self):
        definition = QuestDefinition.objects.create(name="Dragon Slayer", quest_type="boss", target_value=1, is_system=True)
        self.assertEqual(QuestDefinitionSerializer(definition).data.get("catalog_icon"), "challenge-dragon-slayer")
        definition.is_system = False
        self.assertIsNone(QuestDefinitionSerializer(definition).data.get("catalog_icon"))
        definition.is_system, definition.quest_type = True, "collection"
        self.assertIsNone(QuestDefinitionSerializer(definition).data.get("catalog_icon"))

    def test_only_exact_chick_identity_has_catalog_portraits(self):
        chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        for cls in (PetSpeciesSerializer, PetSpeciesCatalogSerializer):
            chick.sprite_key = "cute-chick"
            self.assertEqual(cls(chick).data.get("catalog_icon"), "portrait-chick")
            self.assertEqual(cls(chick).data.get("grown_catalog_icon"), "portrait-chick-grown")
            chick.sprite_key = "other-chick"
            self.assertIsNone(cls(chick).data.get("catalog_icon"))
            self.assertIsNone(cls(chick).data.get("grown_catalog_icon"))

    def test_drop_and_quest_rewards_preserve_verified_item_icon(self):
        child = make_family("Catalog icon family", children=[{"username": "catalog-icon-child"}]).children[0]
        item = ItemDefinition.objects.create(slug="food-meat", name="Meat", item_type="food")
        drop = DropLog.objects.create(user=child, item=item, trigger_type="clock_out")
        definition = QuestDefinition.objects.create(name="Reward fixture", quest_type="collection", target_value=1)
        reward = QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=1)
        self.assertEqual(DropLogSerializer(drop).data.get("item_catalog_icon"), "item-meat")
        self.assertEqual(QuestRewardItemSerializer(reward).data.get("item_catalog_icon"), "item-meat")

    def test_automatic_goal_does_not_infer_art_from_parent_or_retired_name(self):
        family = make_family("Challenge image family", parents=[{"username": "catalog-icon-parent"}],
                             children=[{"username": "catalog-goal-child"}])
        parent, child = family.parents[0], family.children[0]
        definition = QuestDefinition.objects.create(
            name="Feather Collector", quest_type="collection", target_value=3,
            duration_days=7, is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        item = ItemDefinition.objects.create(slug="food-meat", name="Meat", item_type="food")
        QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=1)
        create_goal(parent, child, {"name": definition.name, "metric": "count", "target": 3, "unit": "actions",
                                    "trigger_type": "chore_complete", "period": "this_week", "coin_reward": 0,
                                    "xp_reward": 0, "skill_tags": []})
        goals = list_goals(child)["results"]
        self.assertEqual(next(row for row in goals if row["origin"] == "catalog").get("catalog_icon"), "challenge-feather-collector")
        self.assertIsNone(next(row for row in goals if row["origin"] == "parent").get("catalog_icon"))
        rewards = next(row for row in goals if row["origin"] == "catalog")["rewards"]["items"]
        self.assertEqual(rewards[0].get("item_catalog_icon"), "item-meat")
        definition.delete()
        retired = next(row for row in list_goals(child)["results"] if row["origin"] == "catalog")
        self.assertIsNone(retired.get("catalog_icon"))


class AuthoredCatalogImageIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        output = StringIO()
        call_command("loadrpgcontent", stdout=output)
        for name in ("hs-prep-2026", "sleep-prep-2026", "spring-2026", "summer-2026", "birthday-pack", "year-in-review-pack"):
            call_command("loadrpgcontent", pack=str(Path(settings.BASE_DIR) / "content/rpg/packs" / name), namespace=f"{name}-", stdout=output)

    def test_every_approved_item_and_challenge_resolves_actual_loader_created_record(self):
        from apps.rpg.catalog_icons import bindings, item_catalog_icon, challenge_catalog_icon
        registry = bindings()
        self.assertEqual(len(registry["items"]), 109)
        self.assertEqual(len(registry["challenges"]), 49)
        for slug, entry in registry["items"].items():
            with self.subTest(slug=slug):
                item = ItemDefinition.objects.get(slug=slug)
                self.assertEqual(item_catalog_icon(item), entry["asset_id"])
        for name, entry in registry["challenges"].items():
            with self.subTest(challenge=name):
                definition = QuestDefinition.objects.get(name=name, is_system=True)
                self.assertEqual(challenge_catalog_icon(definition), entry["asset_id"])
        hidden = {slug: row for slug, row in registry["items"].items() if row["requires_confirmation"]}
        self.assertEqual(len(hidden), 16)
        for slug in hidden:
            item = ItemDefinition.objects.get(slug=slug)
            with self.subTest(consumable=slug):
                self.assertEqual(item.item_type, "consumable")
                self.assertEqual(item.name, hidden[slug]["name"])
                self.assertTrue(item.metadata.get("effect"))
        species = PetSpecies.objects.get(slug="chick")
        self.assertEqual(PetSpeciesSerializer(species).data["catalog_icon"], "portrait-chick")
        self.assertEqual(PetSpeciesSerializer(species).data["grown_catalog_icon"], "portrait-chick-grown")
