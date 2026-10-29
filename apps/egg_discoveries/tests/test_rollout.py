"""Activation readiness and honest forecasts use only synthetic/global data."""
from io import StringIO
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.egg_discoveries.catalog import offers_for
from apps.egg_discoveries.models import EggDiscovery
from apps.egg_discoveries.rollout import readiness
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import UserInventory
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import audit_catalog, coverage, rules_fingerprint, simulate_progression
from apps.rpg.tests.test_progression_engine import quiet_config

from .factories import ASSET_POLICY, make_catalog


@override_settings(EGG_DISCOVERY_ENABLED=False, EGG_DISCOVERY_SEASONS={}, RPG_ASSET_SUPPORT_POLICY=ASSET_POLICY)
class RolloutReadinessTests(TestCase):
    def setUp(self):
        self.catalog = make_catalog()

    def test_inspection_uses_no_household_models_or_reward_writers(self):
        with patch.object(EggDiscovery.objects, "filter", side_effect=AssertionError("No household reads")), \
                patch.object(UserInventory.objects, "filter", side_effect=AssertionError("No inventory reads")), \
                patch("apps.rpg.inventory.grant_item", side_effect=AssertionError("No grants")):
            output = StringIO()
            call_command("check_egg_discovery_rollout", "--json", stdout=output)
        report = json.loads(output.getvalue())
        self.assertTrue(report["catalog_ready"])
        self.assertFalse(report["enabled"])
        self.assertEqual((report["ordinary_species_startable"], report["rare_pairs"]), (2, 1))
        self.assertFalse(EggDiscovery.objects.exists())
        self.assertFalse(UserInventory.objects.exists())

    def test_missing_food_and_seasonally_blocked_second_species_refuse_readiness(self):
        with override_settings(EGG_DISCOVERY_SEASONS={self.catalog.other.key: {"starts_on": "2000-01-01", "ends_on": "2000-01-02"}}):
            self.assertEqual(readiness()["ordinary_species_startable"], 1)
            with self.assertRaises(CommandError):
                call_command("check_egg_discovery_rollout", stdout=StringIO())
        self.catalog.food.delete()
        report = readiness()
        self.assertFalse(report["catalog_ready"])
        self.assertTrue(any("supplies" in problem for problem in report["problems"]))

    def test_unknown_or_malformed_season_configuration_is_not_readiness(self):
        for seasons in ([], {"missing:base": {}}, {self.catalog.ordinary.key: {"starts_on": "bad"}}):
            with self.subTest(seasons=seasons), override_settings(EGG_DISCOVERY_SEASONS=seasons):
                self.assertFalse(readiness()["catalog_ready"])

    def test_discovery_mode_invalidates_saved_forecast_rules_even_with_no_catalog_change(self):
        before = rules_fingerprint()
        legacy = load_catalog()
        with override_settings(EGG_DISCOVERY_ENABLED=True):
            self.assertNotEqual(before, rules_fingerprint())
            current = load_catalog()
        self.assertNotEqual(legacy.fingerprint, current.fingerprint)
        # Detached snapshots keep their captured mode after settings change.
        self.assertNotIn("companion_acquisition_mode", coverage(legacy))
        self.assertEqual(coverage(current)["companion_acquisition_mode"], "discovery_unmodeled")
        messages = audit_catalog(current)
        self.assertIn("discovery_forecast_unmodeled", {row["code"] for row in messages})
        self.assertNotIn("random_first_hatch", {row["code"] for row in messages})
        report = simulate_progression(quiet_config(), catalog=current)
        self.assertEqual(report["coverage"]["companion_acquisition_mode"], "discovery_unmodeled")


@override_settings(EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={}, RPG_ASSET_SUPPORT_POLICY=None)
class InstalledRosterReadinessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def test_real_supported_roster_has_a_reachable_starter_and_rare_gate(self):
        report = readiness()
        self.assertTrue(report["catalog_ready"], report)
        self.assertEqual(report["ordinary_species_startable"], 10)
        self.assertEqual(report["ordinary_pairs"] + report["rare_pairs"], 35)
        self.assertTrue(any(offer.egg.pet_species.slug == "chick" and offer.tier == "ordinary" for offer in offers_for(None)))
        self.assertFalse(EggDiscovery.objects.exists())
