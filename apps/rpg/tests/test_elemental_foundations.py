"""The shipped art policy enables exact earned elemental companions."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.pets.models import PetSpecies
from apps.rpg.catalog_support import pet_is_available, random_item_is_available
from apps.rpg.models import ItemDefinition
from apps.rpg.progression.catalog import snapshot_catalog


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class ElementalFoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())

    def test_prepared_challenges_are_present_in_lab_snapshot(self):
        names = {q.name for q in snapshot_catalog().quests}
        self.assertTrue({"Ember Nest", "Frost Nest", "Ember Trail", "Frost Trail"}.issubset(names))

    def test_supported_elemental_potions_are_earned_only(self):
        for species in PetSpecies.objects.filter(slug__in=["chick", "meshtint-wolf"]):
            for slug in ("fire-potion", "ice-potion"):
                potion = ItemDefinition.objects.get(slug=slug)
                self.assertTrue(pet_is_available(species, potion.potion_type))
                self.assertFalse(random_item_is_available(potion))
        self.assertTrue(random_item_is_available(ItemDefinition.objects.get(slug="base-potion")))
