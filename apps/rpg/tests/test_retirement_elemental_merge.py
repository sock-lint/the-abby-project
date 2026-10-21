"""Retirement and elemental availability compose only for new opportunities."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Skill, SkillCategory
from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.quests.services import QuestService
from apps.rpg.acquisition import sources_for_request
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.progression.catalog import snapshot_catalog
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class RetirementElementalMergeTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "retirement-elemental-child"}]).children[0]
        self.category = SkillCategory.objects.create(name="Saved practice")
        self.skill = Skill.objects.create(name="Saved skill", category=self.category)
        self.active = self.definition("Z available challenge")
        self.active_food = self.food("Available snack")
        QuestRewardItem.objects.create(quest_definition=self.active, item=self.active_food)

    @staticmethod
    def definition(name, **values):
        return QuestDefinition.objects.create(
            name=name, quest_type="collection", target_value=3, is_system=True,
            trigger_filter={"allowed_triggers": ["habit_log"]}, coin_reward=0, xp_reward=0,
            **values,
        )

    @staticmethod
    def food(name):
        return ItemDefinition.objects.create(name=name, item_type="food")

    def retired_definition(self):
        definition = self.definition("A retired challenge")
        QuestSkillTag.objects.create(quest_definition=definition, skill=self.skill)
        SkillCategory.objects.filter(pk=self.category.pk).update(is_retired=True)
        item = self.food("Retired opportunity snack")
        QuestRewardItem.objects.create(quest_definition=definition, item=item)
        return definition, item

    def unavailable_elemental_definition(self):
        definition = self.definition("An unavailable elemental challenge")
        species = PetSpecies.objects.create(slug="unsupported-merge-fox", name="Unsupported fox", sprite_key="fox")
        fire = PotionType.objects.create(slug="fire", name="Fire")
        egg = ItemDefinition.objects.create(name="Unsupported fox egg", item_type="egg", pet_species=species)
        potion = ItemDefinition.objects.create(slug="fire-potion", name="Fire potion", item_type="potion", potion_type=fire)
        for item in (egg, potion):
            QuestRewardItem.objects.create(quest_definition=definition, item=item)
        return definition, potion

    def hints(self):
        return sources_for_request(SimpleNamespace(user=self.child))

    def test_new_acquisition_hints_exclude_retired_taxonomy_but_keep_active_alternative(self):
        _, item = self.retired_definition()
        hints = self.hints()
        self.assertEqual(hints[self.active_food.pk], [
            {"kind": "challenge", "name": self.active.name, "path": "/quests?tab=trials"},
        ])
        self.assertNotIn(item.pk, hints)

    def test_new_acquisition_hints_exclude_unavailable_elemental_bundle(self):
        _, potion = self.unavailable_elemental_definition()
        hints = self.hints()
        self.assertIn(self.active_food.pk, hints)
        self.assertNotIn(potion.pk, hints)

    def test_reroll_selects_active_alternative_instead_of_retired_taxonomy(self):
        self.retired_definition()
        self.unavailable_elemental_definition()
        reroll = ItemDefinition.objects.create(
            name="Merge reroll", item_type="consumable", metadata={"effect": "quest_reroll"},
        )
        UserInventory.objects.create(user=self.child, item=reroll, quantity=1)
        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: min(rows, key=lambda row: row.name)):
            result = ConsumableService.use(self.child, reroll.pk)
        self.assertEqual(result["detail"]["quest_name"], self.active.name)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=reroll).exists())

    def test_detached_forecast_applies_both_gates_and_preserves_archived_skill_identity(self):
        retired, _ = self.retired_definition()
        elemental, _ = self.unavailable_elemental_definition()
        alias = self.definition("Saved alias", superseded_by=self.active)
        shared = self.definition("Shared campaign", is_cooperative=True)
        catalog = snapshot_catalog()
        self.assertEqual([row.pk for row in catalog.quests], [self.active.pk])
        self.assertIn(self.skill.pk, catalog.skills)
        self.assertFalse(catalog.skills[self.skill.pk].available_for_new_choices)
        self.assertEqual(QuestDefinition.objects.filter(pk__in=[retired.pk, elemental.pk, alias.pk, shared.pk]).count(), 4)

    def test_accepted_hint_retains_frozen_reward_after_taxonomy_and_definition_changes(self):
        QuestSkillTag.objects.create(quest_definition=self.active, skill=self.skill)
        accepted = QuestService.start_quest(self.child, self.active.pk)
        snapshot = accepted.reward_items_snapshot
        SkillCategory.objects.filter(pk=self.category.pk).update(is_retired=True)
        replacement = self.food("Later catalog reward")
        QuestRewardItem.objects.filter(quest_definition=self.active).update(item=replacement)
        hints = self.hints()
        self.assertEqual(hints[self.active_food.pk], [
            {"kind": "challenge", "name": self.active.name, "path": "/quests?tab=trials"},
        ])
        self.assertNotIn(replacement.pk, hints)
        accepted.refresh_from_db()
        self.assertEqual(accepted.reward_items_snapshot, snapshot)
