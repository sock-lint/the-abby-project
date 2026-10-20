"""MCP forecasts and explanations follow installed domain calculations."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.mcp_server.catalog import catalog_row
from apps.mcp_server.economy import _drop_pools, economy_rules
from apps.rpg import rarity


class EffectiveRulesTests(SimpleTestCase):
    def pool(self, trigger):
        entries = [SimpleNamespace(
            pk=index, trigger_type=trigger, weight=1,
            item=SimpleNamespace(pk=index, slug=tier, rarity=tier, item_type="food"),
        ) for index, tier in enumerate(("common", "rare"), 1)]
        with patch("apps.mcp_server.economy.DropTable.objects") as manager, patch(
            "apps.mcp_server.economy.item_is_available", return_value=True,
        ):
            manager.filter.return_value.select_related.return_value.order_by.return_value.__getitem__.return_value = entries
            return _drop_pools(0, {trigger})[trigger]["outcomes"]

    def test_ordinary_and_accomplishment_forecasts_use_runtime_tier_budgets(self):
        for trigger, common in (("reading_logged", 6 / 7), ("project_complete", 2 / 3)):
            with self.subTest(trigger=trigger):
                rows = self.pool(trigger)
                self.assertAlmostEqual(rows[0]["conditional_probability"], common)
                self.assertAlmostEqual(rows[1]["conditional_probability"], 1 - common)

    def test_fingerprint_changes_with_installed_rarity_policy(self):
        original = economy_rules()["rules_fingerprint"]
        with patch.dict(rarity.BASE_TIER_WEIGHTS, {"common": 1}):
            self.assertNotEqual(economy_rules()["rules_fingerprint"], original)

    def test_catalog_explains_effective_food_growth_without_player_state(self):
        item = SimpleNamespace(pk=1, slug="rare-food", name="Food", description="", icon="F",
            sprite_key="", item_type="food", rarity="rare", coin_value=1, metadata={"growth": 1},
            pet_species_id=None, potion_type_id=None, food_species_id=None)
        with patch("apps.mcp_server.catalog._item_availability", return_value={}):
            row = catalog_row("items", item)
        self.assertIn("10 growth", row["effect_summary"])


class RuleInspectionPrivacyTests(TestCase):
    def test_milestone_dependency_explanations_include_only_global_successors(self):
        from apps.achievements.models import Skill, SkillCategory
        from apps.mcp_server.context import override_user
        from apps.mcp_server.rpg_rule_schemas import ExplainCatalogEntryIn
        from apps.mcp_server.tools.rpg_rules import explain_rpg_catalog_entry
        from apps.quests.models import QuestDefinition
        from config.tests.factories import make_family

        actor = make_family("Milestone references", parents=[{"username": "gate-reference-parent"}]).parents[0]
        skill = Skill.objects.create(name="Reading", category=SkillCategory.objects.create(name="Practice"))
        predecessor = QuestDefinition.objects.create(name="First chapter", is_system=True,
            quest_type="collection", target_value=1)
        successor = QuestDefinition.objects.create(name="Next chapter", is_system=True,
            quest_type="collection", target_value=2, prerequisite_quest=predecessor,
            required_skill=skill, required_skill_level=1,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        QuestDefinition.objects.create(name="Private family plan", created_by=actor,
            quest_type="collection", target_value=2, prerequisite_quest=predecessor,
            required_skill=skill, required_skill_level=1)
        expected = [{"section": "quests", "id": successor.pk, "name": successor.name}]
        with override_user(actor):
            for section, object_id in (("quests", predecessor.pk), ("skills", skill.pk)):
                with self.subTest(section=section):
                    result = explain_rpg_catalog_entry(ExplainCatalogEntryIn(section=section, object_id=object_id))
                    self.assertEqual(result["references"], expected)
                    self.assertFalse(result["references_truncated"])

    def test_rule_manifest_uses_no_household_queries_and_binds_effective_food_rules(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.rpg_rule_schemas import GetRpgRulesIn, RpgRulesResult
        from apps.mcp_server.tools.rpg_rules import get_rpg_rules
        from apps.rpg.item_effects import FOOD_GROWTH_BY_RARITY
        from config.tests.factories import make_family

        actor = make_family("Rule inspection", parents=[{"username": "rule-parent", "is_staff": True}]).parents[0]
        with override_user(actor), self.assertNumQueries(0):
            result = get_rpg_rules(GetRpgRulesIn())
        RpgRulesResult.model_validate(result)
        self.assertIn("XP thresholds", result["authoring"]["installed_mechanics"])
        with override_user(actor), patch.dict(FOOD_GROWTH_BY_RARITY, {"rare": 11}):
            changed = get_rpg_rules(GetRpgRulesIn())
        self.assertNotEqual(changed["fingerprint"], result["fingerprint"])

    def test_entry_references_are_bounded_and_exclude_private_quest_definitions(self):
        import json
        from apps.mcp_server.context import override_user
        from apps.mcp_server.rpg_rule_schemas import ExplainCatalogEntryIn, CatalogExplanationResult
        from apps.mcp_server.tools.rpg_rules import explain_rpg_catalog_entry
        from apps.quests.models import QuestDefinition, QuestRewardItem
        from apps.rpg.models import DropTable, ItemDefinition
        from config.tests.factories import make_family

        actor = make_family("Reference inspection", parents=[{"username": "reference-parent", "is_staff": True}]).parents[0]
        item = ItemDefinition.objects.create(slug="reference-food", name="Food", item_type="food", metadata={"growth": 1})
        global_id = None
        for name, system in (("Global quest", True), ("Private synthetic family quest", False)):
            quest = QuestDefinition.objects.create(name=name, quest_type="collection", target_value=1,
                is_system=system, created_by=None if system else actor)
            QuestRewardItem.objects.create(quest_definition=quest, item=item)
            if system:
                global_id = quest.pk
        DropTable.objects.create(item=item, trigger_type="reading_logged", weight=1)
        with override_user(actor):
            result = explain_rpg_catalog_entry(ExplainCatalogEntryIn(section="items", object_id=item.pk, limit=1))
        CatalogExplanationResult.model_validate(result)
        self.assertEqual(result["references"], [{"section": "quests", "id": global_id, "name": "Global quest"}])
        self.assertTrue(result["references_truncated"])
        self.assertNotIn("Private synthetic family quest", json.dumps(result))
