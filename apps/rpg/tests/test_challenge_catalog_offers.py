"""Forecast and MCP offers must use the same canonical challenge identities."""
from unittest.mock import patch
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.mcp_server.schemas import ListRpgCatalogIn
from apps.mcp_server.tools.content_packs import list_rpg_catalog
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant
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

    def reroll_inventory(self):
        child = make_family("Enrolled reroll household", children=[{"username": "enrolled-reroll-child"}]).children[0]
        item = ItemDefinition.objects.create(
            slug="enrolled-reroll", name="Reroll", item_type="consumable",
            metadata={"effect": "quest_reroll"},
        )
        UserInventory.objects.create(user=child, item=item, quantity=1)
        return child, item

    def test_reroll_excludes_accepted_automatic_identity_and_retained_alias(self):
        child, item = self.reroll_inventory()
        canonical = self.definition("A accepted automatic ritual")
        alias = self.definition("A accepted automatic ritual", superseded_by=canonical)
        list_goals(child)
        goal = ChallengeGoal.objects.get(user=child, catalog_definition=canonical)
        goal.catalog_definition = alias
        goal.save(update_fields=["catalog_definition"])
        accepted = list(ChallengeOccurrence.objects.filter(goal=goal).values())
        manual = self.definition("Z new manual ritual")

        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]) as choose:
            result = ConsumableService.use(child, item.pk)

        self.assertEqual([row.pk for row in choose.call_args.args[0]], [manual.pk])
        self.assertEqual(result["detail"]["quest_name"], manual.name)
        self.assertEqual(list(ChallengeOccurrence.objects.filter(goal=goal).values()), accepted)
        self.assertFalse(Quest.objects.filter(definition=canonical).exists())

    def test_reroll_excludes_completed_one_time_alias_but_keeps_repeatable(self):
        child, item = self.reroll_inventory()
        finished = self.definition("A finished one-time ritual")
        alias = self.definition("A finished one-time ritual", superseded_by=finished)
        repeatable = self.definition("Z repeatable ritual", is_repeatable=True)
        for definition in (alias, repeatable):
            quest = Quest.objects.create(
                definition=definition, status="completed", end_date=timezone.now() - timedelta(days=1),
            )
            QuestParticipant.objects.create(quest=quest, user=child)

        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]) as choose:
            result = ConsumableService.use(child, item.pk)

        self.assertEqual([row.pk for row in choose.call_args.args[0]], [repeatable.pk])
        self.assertEqual(result["detail"]["quest_name"], repeatable.name)
        self.assertEqual(Quest.objects.filter(definition=finished).count(), 0)

    def test_reroll_with_only_accepted_automatic_goals_preserves_item_and_promises(self):
        child, item = self.reroll_inventory()
        self.definition("Already automatic")
        list_goals(child)
        before = list(ChallengeOccurrence.objects.values())
        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]) as choose:
            with self.assertRaisesMessage(ValueError, "No eligible quests to reroll into"):
                ConsumableService.use(child, item.pk)
        choose.assert_not_called()
        self.assertEqual(UserInventory.objects.get(user=child, item=item).quantity, 1)
        self.assertEqual(list(ChallengeOccurrence.objects.values()), before)
        self.assertFalse(Quest.objects.exists())
