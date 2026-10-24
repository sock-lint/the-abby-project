"""A Base companion bundle keeps its egg until the Base appearance is owned."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.pets.models import PetSpecies, PotionType, UserMount
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeOccurrence, QuestDefinition
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BaseBundleSalvageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())

    def setUp(self):
        family = make_family("Base bundle salvage", children=[{"username": "base-bundle-child"}])
        self.child = family.children[0]
        QuestDefinition.objects.exclude(name="Wolf Trail").update(is_system=False)
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)
        self.wolf = PetSpecies.objects.get(slug="meshtint-wolf")

    def complete_wolf_trail(self):
        list_goals(self.child)
        for index in range(20):
            ingest_activity(self.child, "chore_complete", f"wolf-trail-{index}", "chore_complete")
        return ChallengeOccurrence.objects.get(
            goal__user=self.child, goal__catalog_definition__name="Wolf Trail",
        ).reward_receipt

    def test_fire_wolf_owner_keeps_the_egg_promised_for_the_base_form(self):
        UserMount.objects.create(user=self.child, species=self.wolf, potion=PotionType.objects.get(slug="fire"))
        receipt = self.complete_wolf_trail()
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="meshtint-wolf-egg").quantity, 1)
        self.assertEqual(receipt["coins"], 0)
        self.assertTrue(all("salvaged_to_coins" not in row for row in receipt["items"]))

    def test_base_wolf_owner_still_salvages_the_duplicate_egg(self):
        UserMount.objects.create(user=self.child, species=self.wolf, potion=PotionType.objects.get(slug="base"))
        receipt = self.complete_wolf_trail()
        self.assertFalse(UserInventory.objects.filter(user=self.child, item__slug="meshtint-wolf-egg").exists())
        self.assertEqual(receipt["coins"], ItemDefinition.objects.get(slug="meshtint-wolf-egg").coin_value)
