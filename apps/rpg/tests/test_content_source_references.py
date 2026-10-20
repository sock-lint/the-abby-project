"""Persisted source identities remain usable by dependent catalog definitions."""
from copy import deepcopy
import io

from django.test import TestCase

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.schemas import CreateSkillIn, UpdateBadgeIn, UpdateCategoryIn, UpdateSkillIn
from apps.mcp_server.tools import achievements
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.workbench import create_draft, preview_draft, publish_draft, save_draft, simulate_draft
from apps.rpg.models import RPGContentOverride
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

    def _assert_direct_category_source_cannot_be_reused(self, *, existing_override):
        parsed = {"skill_tree": {"categories": [{"name": "Original category"}, {"name": "Other category"}],
                                  "skills": [{"name": "Source skill", "category": "Original category"}]},
                  "quests": {"quests": [self.quest(xp_reward=3, skill_tags=["Original category::Source skill"])]}}
        self.load(parsed)
        original = SkillCategory.objects.get(name="Original category")
        other = SkillCategory.objects.get(name="Other category")
        skill = Skill.objects.get(name="Source skill")
        with override_user(self.parent):
            achievements.update_category(UpdateCategoryIn(category_id=original.pk, name="Authored category"))
            if existing_override:
                achievements.update_category(UpdateCategoryIn(category_id=other.pk, color="#123456"))
            before = list(RPGContentOverride.objects.order_by("pk").values())
            with self.assertRaises(MCPValidationError):
                achievements.update_category(UpdateCategoryIn(category_id=other.pk, name="Original category"))
        other.refresh_from_db()
        self.assertEqual(other.name, "Other category")
        self.assertEqual(list(RPGContentOverride.objects.order_by("pk").values()), before)
        self.load(parsed)
        self.assertEqual(list(QuestDefinition.objects.get(name="Dependent").skill_tags.values_list("skill_id", flat=True)), [skill.pk])

    def test_direct_rename_cannot_reuse_another_category_source_identity(self):
        self._assert_direct_category_source_cannot_be_reused(existing_override=False)

    def test_already_authored_category_cannot_reuse_another_source_identity(self):
        self._assert_direct_category_source_cannot_be_reused(existing_override=True)

    def test_badge_rename_cannot_reuse_another_badges_required_source(self):
        parsed = {"badges": {"badges": [
            {"name": name, "criteria_type": "projects_completed", "criteria_value": {"count": 1}}
            for name in ("Original badge", "Other badge")]},
            "quests": {"quests": [self.quest(required_badge="Original badge")]}}
        self.load(parsed)
        original = Badge.objects.get(name="Original badge")
        other = Badge.objects.get(name="Other badge")
        with override_user(self.parent):
            achievements.update_badge(UpdateBadgeIn(badge_id=original.pk, name="Authored badge"))
            with self.assertRaises(MCPValidationError):
                achievements.update_badge(UpdateBadgeIn(badge_id=other.pk, name="Original badge"))
        self.load(parsed)
        self.assertEqual(QuestDefinition.objects.get(name="Dependent").required_badge_id, original.pk)
        self.assertEqual(Badge.objects.get(pk=other.pk).name, "Other badge")

    def test_skill_rename_cannot_reuse_another_skill_source_in_the_same_category(self):
        parsed = {"skill_tree": {"categories": [{"name": "Source category"}], "skills": [
            {"name": name, "category": "Source category"} for name in ("Original skill", "Other skill")]},
            "quests": {"quests": [self.quest(xp_reward=3, skill_tags=["Source category::Original skill"])]}}
        self.load(parsed)
        original = Skill.objects.get(name="Original skill")
        other = Skill.objects.get(name="Other skill")
        with override_user(self.parent):
            achievements.update_skill(UpdateSkillIn(skill_id=original.pk, name="Authored skill"))
            with self.assertRaises(MCPValidationError):
                achievements.update_skill(UpdateSkillIn(skill_id=other.pk, name="Original skill"))
        self.load(parsed)
        self.assertEqual(list(QuestDefinition.objects.get(name="Dependent").skill_tags.values_list("skill_id", flat=True)), [original.pk])
        self.assertEqual(Skill.objects.get(pk=other.pk).name, "Other skill")

    def test_direct_renames_can_return_to_the_same_objects_own_source_identity(self):
        parsed = {"skill_tree": {"categories": [{"name": "Original category"}]}}
        self.load(parsed)
        category = SkillCategory.objects.get(name="Original category")
        with override_user(self.parent):
            for name in ("First authored name", "Another authored name", "Original category"):
                achievements.update_category(UpdateCategoryIn(category_id=category.pk, name=name))
        self.load(parsed)
        self.assertEqual(SkillCategory.objects.get(name="Original category").pk, category.pk)
        self.assertEqual(SkillCategory.objects.count(), 1)

    def test_qualified_skill_sources_do_not_reserve_the_name_in_another_category(self):
        parsed = {"skill_tree": {"categories": [{"name": "Source category"}, {"name": "Other category"}],
                                  "skills": [{"name": "Original skill", "category": "Source category"}]},
                  "quests": {"quests": [self.quest(xp_reward=3, skill_tags=["Source category::Original skill"])]}}
        self.load(parsed)
        original = Skill.objects.get(name="Original skill")
        other_category = SkillCategory.objects.get(name="Other category")
        with override_user(self.parent):
            achievements.update_skill(UpdateSkillIn(skill_id=original.pk, name="Authored skill"))
            other = achievements.create_skill(CreateSkillIn(name="Original skill", category_id=other_category.pk))
        self.load(parsed)
        self.assertEqual(list(QuestDefinition.objects.get(name="Dependent").skill_tags.values_list("skill_id", flat=True)), [original.pk])
        self.assertEqual(Skill.objects.get(pk=other["id"]).category_id, other_category.pk)

    def test_reviewed_quest_rename_cannot_reuse_another_predecessors_source_identity(self):
        parsed = {"quests": {"quests": [self.quest("Source predecessor"), self.quest("Other predecessor"),
                                         self.quest(prerequisite_quest="Source predecessor")]}}
        self.load(parsed)
        predecessor = QuestDefinition.objects.get(name="Source predecessor")
        other = QuestDefinition.objects.get(name="Other predecessor")
        self.publish_change(predecessor, {"name": "Authored predecessor"})
        with self.assertRaises(ContentPackError):
            self.publish_change(other, {"name": "Source predecessor"})
        self.load(parsed)
        self.assertEqual(QuestDefinition.objects.get(name="Dependent").prerequisite_quest_id, predecessor.pk)
        self.assertEqual(QuestDefinition.objects.get(pk=other.pk).name, "Other predecessor")

    def test_new_quest_cannot_claim_another_predecessors_retained_source_name(self):
        parsed = {"quests": {"quests": [self.quest("Source predecessor")]}}
        self.load(parsed)
        predecessor = QuestDefinition.objects.get(name="Source predecessor")
        self.publish_change(predecessor, {"name": "Authored predecessor"})
        draft = create_draft(self.parent, "Reused original source")
        with self.assertRaises(ContentPackError):
            save_draft(self.parent, draft["id"], draft["revision"], [{
                "section": "quests", "object_id": None, "key": "reused",
                "values": self.quest("Source predecessor"),
            }])
        self.assertEqual(QuestDefinition.objects.count(), 1)

    def test_reviewed_quest_can_return_to_its_own_original_source_name(self):
        parsed = {"quests": {"quests": [self.quest("Source predecessor")]}}
        self.load(parsed)
        predecessor = QuestDefinition.objects.get(name="Source predecessor")
        self.publish_change(predecessor, {"name": "Authored predecessor"})
        self.publish_change(predecessor, {"name": "Source predecessor"})
        self.load(parsed)
        self.assertEqual(QuestDefinition.objects.get(name="Source predecessor").pk, predecessor.pk)
        self.assertEqual(QuestDefinition.objects.count(), 1)

    def test_same_draft_cannot_reuse_the_source_identity_created_by_its_first_rename(self):
        parsed = {"quests": {"quests": [self.quest("Source predecessor"), self.quest("Other predecessor"),
                                         self.quest(prerequisite_quest="Source predecessor")]}}
        self.load(parsed)
        predecessor = QuestDefinition.objects.get(name="Source predecessor")
        other = QuestDefinition.objects.get(name="Other predecessor")
        draft = create_draft(self.parent, "Conflicting simultaneous renames")
        draft = save_draft(self.parent, draft["id"], draft["revision"], [{
            "section": "quests", "object_id": predecessor.pk, "key": "a-first",
            "values": {"name": "Authored predecessor"},
        }, {
            "section": "quests", "object_id": other.pk, "key": "b-second",
            "values": {"name": "Source predecessor"},
        }])
        with self.assertRaises(ContentPackError):
            preview_draft(self.parent, draft["id"], draft["revision"])
        self.assertEqual(QuestDefinition.objects.get(pk=predecessor.pk).name, "Source predecessor")
        self.assertEqual(QuestDefinition.objects.get(pk=other.pk).name, "Other predecessor")
        self.assertFalse(RPGContentOverride.objects.exists())
        self.load(parsed)
        self.assertEqual(QuestDefinition.objects.get(name="Dependent").prerequisite_quest_id, predecessor.pk)

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
