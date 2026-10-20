"""Persisted source identities remain usable by dependent catalog definitions."""
from copy import deepcopy
import io

from django.test import TestCase

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import UpdateBadgeIn, UpdateCategoryIn, UpdateSkillIn
from apps.mcp_server.tools import achievements
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.workbench import create_draft, preview_draft, publish_draft, save_draft, simulate_draft
from apps.rpg.tests.test_progression_engine import quiet_config
from config.tests.factories import make_family


class ContentSourceReferenceTests(TestCase):
    def setUp(self):
        self.parent = make_family(parents=[{"username": "source-author", "is_staff": True}]).parents[0]

    def load(self, parsed):
        return ContentPack("content/rpg/initial", parsed_content=deepcopy(parsed)).load(stdout=io.StringIO())

    def quest(self, name="Dependent", **values):
        return {"name": name, "description": "Synthetic source reference", "quest_type": "collection", "target_value": 1,
                "trigger_filter": {"allowed_triggers": ["reading_logged"]}, **values}

    def publish_change(self, quest, values):
        draft = create_draft(self.parent, "Rename a referenced source")
        draft = save_draft(self.parent, draft["id"], draft["revision"], [{
            "section": "quests", "object_id": quest.pk, "key": "renamed", "values": values,
        }])
        plan = preview_draft(self.parent, draft["id"], draft["revision"])["preview"]
        simulate_draft(self.parent, draft["id"], draft["revision"], plan["preview_id"], quiet_config(reading_minutes=10))
        publish_draft(self.parent, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])

    def test_renamed_badge_source_keeps_existing_required_badge_identity(self):
        parsed = {"badges": {"badges": [{"name": "Source badge", "criteria_type": "projects_completed",
                                         "criteria_value": {"count": 1}}]},
                  "quests": {"quests": [self.quest(required_badge="Source badge")]}}
        self.load(parsed)
        badge = Badge.objects.get(name="Source badge")
        with override_user(self.parent):
            achievements.update_badge(UpdateBadgeIn(badge_id=badge.pk, name="Authored badge"))
        self.load(parsed)
        self.assertEqual(QuestDefinition.objects.get(name="Dependent").required_badge_id, badge.pk)
        self.assertEqual(Badge.objects.get(pk=badge.pk).name, "Authored badge")
        self.assertEqual(Badge.objects.count(), 1)

    def test_renamed_taxonomy_keeps_reward_tags_and_required_skill_identity(self):
        parsed = {"skill_tree": {"categories": [{"name": "Source category"}], "skills": [{
            "name": "Source skill", "category": "Source category", "levels": {1: "Beginner"},
        }]}, "quests": {"quests": [self.quest(
            required_skill="Source category::Source skill", required_skill_level=1,
            xp_reward=3, skill_tags=["Source category::Source skill"],
        )]}}
        self.load(parsed)
        category = SkillCategory.objects.get(name="Source category")
        skill = Skill.objects.get(name="Source skill")
        with override_user(self.parent):
            achievements.update_category(UpdateCategoryIn(category_id=category.pk, name="Authored category"))
            achievements.update_skill(UpdateSkillIn(skill_id=skill.pk, name="Authored skill"))
        self.load(parsed)
        quest = QuestDefinition.objects.get(name="Dependent")
        self.assertEqual(quest.required_skill_id, skill.pk)
        self.assertEqual(list(quest.skill_tags.values_list("skill_id", flat=True)), [skill.pk])
        self.assertEqual(Skill.objects.get(pk=skill.pk).name, "Authored skill")
        self.assertEqual(Skill.objects.count(), 1)

    def test_renamed_workbench_predecessor_keeps_its_original_yaml_reference(self):
        parsed = {"quests": {"quests": [self.quest(prerequisite_quest="Source predecessor"),
                                         self.quest("Source predecessor")]}}
        self.load(parsed)
        predecessor = QuestDefinition.objects.get(name="Source predecessor")
        self.publish_change(predecessor, {"name": "Authored predecessor"})
        self.load(parsed)
        self.assertEqual(QuestDefinition.objects.get(name="Dependent").prerequisite_quest_id, predecessor.pk)
        self.assertEqual(QuestDefinition.objects.get(pk=predecessor.pk).name, "Authored predecessor")
        self.assertEqual(QuestDefinition.objects.count(), 2)

    def test_unqualified_old_source_name_never_silently_rebinds_to_a_new_skill(self):
        parsed = {"skill_tree": {"categories": [{"name": "Source category"}], "skills": [{
            "name": "Source skill", "category": "Source category", "levels": {1: "Beginner"},
        }]}, "quests": {"quests": [self.quest(xp_reward=3, skill_tags=["Source skill"])]}}
        self.load(parsed)
        original = Skill.objects.get(name="Source skill")
        with override_user(self.parent):
            achievements.update_skill(UpdateSkillIn(skill_id=original.pk, name="Authored skill"))
        Skill.objects.create(name="Source skill", category=SkillCategory.objects.create(name="Another category"))
        with self.assertRaisesRegex(ContentPackError, "ambiguous"):
            self.load(parsed)
        quest = QuestDefinition.objects.get(name="Dependent")
        self.assertEqual(list(quest.skill_tags.values_list("skill_id", flat=True)), [original.pk])

    def test_cooperative_milestone_pack_is_rejected_without_creating_a_quest(self):
        category = SkillCategory.objects.create(name="Milestone category")
        Skill.objects.create(name="Milestone skill", category=category)
        with self.assertRaises(ContentPackError):
            self.load({"quests": {"quests": [self.quest(
                is_cooperative=True, required_skill="Milestone category::Milestone skill", required_skill_level=1,
            )]}})
        self.assertFalse(QuestDefinition.objects.exists())

    def test_cooperative_milestone_workbench_edit_is_rejected_without_saving(self):
        category = SkillCategory.objects.create(name="Milestone category")
        skill = Skill.objects.create(name="Milestone skill", category=category)
        quest = QuestDefinition.objects.create(**self.quest(is_system=True))
        draft = create_draft(self.parent, "Unsupported shared milestone")
        with self.assertRaises(ContentPackError):
            save_draft(self.parent, draft["id"], draft["revision"], [{
                "section": "quests", "object_id": quest.pk, "key": "shared",
                "values": {"is_cooperative": True, "required_skill": skill.pk, "required_skill_level": 1},
            }])
        quest.refresh_from_db()
        self.assertFalse(quest.is_cooperative)
        self.assertIsNone(quest.required_skill_id)
