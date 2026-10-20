"""Forecast and MCP offers must use the same canonical challenge identities."""
from unittest.mock import patch

from django.test import TestCase

from apps.mcp_server.schemas import ListRpgCatalogIn
from apps.mcp_server.tools.content_packs import list_rpg_catalog
from apps.quests.models import QuestDefinition
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.progression.catalog import snapshot_catalog
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


class ChallengeCatalogOfferTests(TestCase):
    def definition(self, name, **values):
        return QuestDefinition.objects.create(
            name=name, quest_type="collection", target_value=3,
            is_system=True, trigger_filter={"allowed_triggers": ["habit_log"]},
            **values,
        )

    def test_single_child_forecast_excludes_explicit_family_coop(self):
        individual = self.definition("Individual ritual")
        cooperative = self.definition("Family effort", is_cooperative=True)
        catalog = snapshot_catalog()
        self.assertIn(individual.pk, [quest.pk for quest in catalog.quests])
        self.assertNotIn(cooperative.pk, [quest.pk for quest in catalog.quests])

    def test_forecast_cannot_double_count_ambiguous_system_names(self):
        self.definition("Duplicate ritual")
        self.definition("Duplicate ritual")
        self.assertLessEqual(
            sum(quest.name == "Duplicate ritual" for quest in snapshot_catalog().quests), 1,
        )

    def test_mcp_offer_summary_cannot_publish_duplicate_name_twice(self):
        self.definition("Duplicate ritual")
        self.definition("Duplicate ritual")
        with patch("apps.mcp_server.tools.content_packs.require_parent"):
            summary = list_rpg_catalog(ListRpgCatalogIn())
        self.assertLessEqual(sum(quest["name"] == "Duplicate ritual" for quest in summary["quests"]), 1)
        self.assertEqual(summary["totals"]["quests"], len(summary["quests"]))

    def test_retained_alias_does_not_hide_the_canonical_forecast_or_offer(self):
        canonical = self.definition("Canonical ritual")
        alias = self.definition("Canonical ritual", superseded_by=canonical)
        self.assertEqual([quest.pk for quest in snapshot_catalog().quests], [canonical.pk])
        with patch("apps.mcp_server.tools.content_packs.require_parent"):
            summary = list_rpg_catalog(ListRpgCatalogIn())
        self.assertEqual([quest["name"] for quest in summary["quests"]], [canonical.name])
        self.assertTrue(QuestDefinition.objects.filter(pk=alias.pk).exists())

    def test_reroll_never_selects_a_retained_alias_or_shared_campaign(self):
        child = make_family("Reroll household", children=[{"username": "reroll-child"}]).children[0]
        CharacterProfile.objects.get_or_create(user=child)
        self.definition("A family campaign", is_cooperative=True)
        eligible = self.definition("Z individual ritual")
        self.definition("A retired alias", superseded_by=eligible)
        item = ItemDefinition.objects.create(
            slug="review-reroll", name="Reroll", item_type="consumable",
            metadata={"effect": "quest_reroll"},
        )
        UserInventory.objects.create(user=child, item=item, quantity=1)
        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]):
            result = ConsumableService.use(child, item.pk)
        self.assertEqual(result["detail"]["quest_name"], eligible.name)
