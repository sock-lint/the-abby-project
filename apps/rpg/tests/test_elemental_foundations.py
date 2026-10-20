"""Elemental foundations remain private until their exact art is accepted."""
from copy import deepcopy
from io import StringIO
import json

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.pets.models import PetSpecies
from apps.rpg.catalog_support import POLICY_PATH, pet_is_available, random_item_is_available
from apps.rpg.models import ItemDefinition
from apps.rpg.progression.catalog import snapshot_catalog


class ElementalFoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())

    def test_unprepared_challenges_are_absent_from_lab_snapshot(self):
        names = {q.name for q in snapshot_catalog().quests}
        self.assertTrue(names.isdisjoint({"Ember Nest", "Frost Nest", "Ember Trail", "Frost Trail"}))

    def test_supported_elemental_potions_are_earned_only(self):
        policy = deepcopy(json.loads(POLICY_PATH.read_text()))
        policy["potion_slugs"].extend(["fire", "ice"])
        next(p for p in policy["pets"] if p["species_slug"] == "meshtint-wolf")["potion_slugs"].extend(["fire", "ice"])
        with override_settings(RPG_ASSET_SUPPORT_POLICY=policy):
            species = PetSpecies.objects.get(slug="meshtint-wolf")
            for slug in ("fire-potion", "ice-potion"):
                potion = ItemDefinition.objects.get(slug=slug)
                self.assertTrue(pet_is_available(species, potion.potion_type))
                self.assertFalse(random_item_is_available(potion))
            self.assertTrue(random_item_is_available(ItemDefinition.objects.get(slug="base-potion")))
