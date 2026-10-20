"""Actual authoring responses consumed by the React content workspace."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rpg.models import DropTable, ItemDefinition
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared
from config.tests.test_progression_api_contract_fixtures import INCUBATION_POLICY


@override_settings(ALLOWED_HOSTS=["testserver"], SOURCE_COMMIT="", RPG_ASSET_SUPPORT_POLICY=None)
class ContentWorkbenchResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        family = make_family(
            "Synthetic content studio", family_id=47,
            parents=[{"id": 71, "username": "fixture-content-designer", "is_staff": True}],
        )
        self.designer = family.parents[0]
        self.client.force_authenticate(self.designer)
        category = SkillCategory.objects.create(id=901, name="Life Skills")
        skill = Skill.objects.create(id=902, name="Persistence", category=category)
        prerequisite = QuestDefinition.objects.create(
            id=908, name="Starter practice", description="Complete one approved chore.",
            quest_type="collection", target_value=1, duration_days=7, is_system=True,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        self.item = ItemDefinition.objects.create(
            id=903, slug="fixture-studio-food", name="Practice snack", icon="🍎",
            item_type="food", rarity="common", coin_value=2,
            metadata={"growth": 5},
        )
        quest = QuestDefinition.objects.create(
            id=904, name="Practice challenge", description="Complete two daily Reading Adventures.",
            quest_type="collection", target_value=2, duration_days=7,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
            coin_reward=10, xp_reward=15, is_system=True,
            prerequisite_quest=prerequisite, required_skill=skill, required_skill_level=1,
        )
        QuestSkillTag.objects.create(id=905, quest_definition=quest, skill=skill, xp_weight=1)
        QuestRewardItem.objects.create(id=906, quest_definition=quest, item=self.item, quantity=1)
        DropTable.objects.create(id=907, trigger_type="chore_complete", item=self.item, weight=10)

    def test_catalog_rewards_and_references_match_the_shared_wire_contract(self):
        body = self.assert_response_fixture(
            self.client.get("/api/rpg/content-workbench/"), "content-workbench-catalog.json",
        )
        self.assertEqual(len(body["catalog"]["items"]), 1)
        self.assertEqual(len(body["catalog"]["quests"]), 2)
        target = next(row for row in body["catalog"]["quests"] if row["id"] == 904)
        self.assertEqual((target["prerequisite_quest"], target["required_skill"], target["required_skill_level"]), (908, 902, 1))
        self.assertEqual(body["drafts"], [])
        self.assertEqual(body["simulation"]["pet_incubation_policy"], INCUBATION_POLICY)

    def test_regular_parents_cannot_inspect_the_authoring_workspace(self):
        self.designer.is_staff = False
        self.designer.save(update_fields=["is_staff"])
        self.assert_response_fixture(
            self.client.get("/api/rpg/content-workbench/"), "content-workbench-denied.json", status=403,
        )
