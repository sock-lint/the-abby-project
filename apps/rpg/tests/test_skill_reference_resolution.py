"""Bare author references reject ambiguity; explicit taxonomy identities stay exact."""
from copy import deepcopy
import io

from django.core.management import call_command
from django.test import TestCase

from apps.achievements.models import Skill, SkillCategory, SkillPrerequisite
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import CreateSkillIn
from apps.mcp_server.tools import achievements
from apps.quests.models import QuestDefinition
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPack, ContentPackError
from config.tests.factories import make_family


class SkillReferenceResolutionTests(TestCase):
    def load(self, parsed):
        return ContentPack("content/rpg/initial", parsed_content=deepcopy(parsed)).load(stdout=io.StringIO())

    def tree(self, categories, skills):
        return {"skill_tree": {"categories": [{"name": name} for name in categories], "skills": skills}}

    def test_subject_identity_cannot_collide_with_another_category_subject_pair(self):
        parsed = self.tree(["A", "A::B"], [{"name": "Assigned skill", "category": "A", "subject": "B::C"}])
        parsed["skill_tree"]["subjects"] = [
            {"name": "B::C", "category": "A"}, {"name": "C", "category": "A::B"},
        ]
        self.load(parsed)
        skill = Skill.objects.select_related("subject").get(name="Assigned skill")
        self.assertEqual(skill.subject.name, "B::C")
        self.assertEqual(skill.subject.category_id, skill.category_id)

    def test_literal_bare_alias_cannot_override_a_same_category_prerequisite(self):
        self.load(self.tree(["Physical", "ZZ other"], [
            {"name": "Endurance", "category": "Physical"},
            {"name": "Physical::Endurance", "category": "ZZ other"},
            {"name": "Advanced", "category": "Physical", "prereqs": ["Endurance"]},
        ]))
        canonical = Skill.objects.get(name="Endurance", category__name="Physical")
        self.assertEqual(SkillPrerequisite.objects.get(skill__name="Advanced").required_skill_id, canonical.pk)

    def test_ambiguous_qualified_prerequisite_spelling_rejects_atomically(self):
        with self.assertRaisesRegex(ContentPackError, "ambiguous"):
            self.load(self.tree(["A", "A::B"], [
                {"name": "B::C", "category": "A"}, {"name": "C", "category": "A::B"},
                {"name": "Advanced", "category": "A", "prereqs": ["A::B::C"]},
            ]))
        self.assertFalse(Skill.objects.exists())
        self.assertFalse(SkillCategory.objects.exists())
        self.assertFalse(SkillPrerequisite.objects.exists())

    def test_unambiguous_qualified_prerequisite_can_contain_a_delimiter_in_its_skill_name(self):
        self.load(self.tree(["A", "Z"], [
            {"name": "B::C", "category": "A"},
            {"name": "Advanced", "category": "Z", "prereqs": ["A::B::C"]},
        ]))
        self.assertEqual(SkillPrerequisite.objects.get(skill__name="Advanced").required_skill.name, "B::C")

    def test_ambiguous_qualified_quest_spelling_rejects_for_tags_and_gates(self):
        self.load(self.tree(["A", "A::B"], [
            {"name": "B::C", "category": "A"}, {"name": "C", "category": "A::B"},
        ]))
        base = {"name": "Ambiguous qualified reading", "description": "Synthetic", "quest_type": "collection",
                "target_value": 1, "trigger_filter": {"allowed_triggers": ["reading_logged"]}}
        for changes in ({"skill_tags": ["A::B::C"]}, {"required_skill": "A::B::C", "required_skill_level": 1}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ContentPackError, "ambiguous"):
                self.load({"quests": {"quests": [{**base, **changes}]}})
        self.assertFalse(QuestDefinition.objects.exists())

    def test_bare_prerequisites_remain_local_and_qualified_prerequisites_can_cross_categories(self):
        self.load(self.tree(["A", "B"], [
            {"name": "Twin", "category": "A"}, {"name": "Twin", "category": "B"},
            {"name": "Local advanced", "category": "A", "prereqs": ["Twin"]},
            {"name": "Cross advanced", "category": "B", "prereqs": ["A::Twin"]},
        ]))
        canonical = Skill.objects.get(name="Twin", category__name="A")
        self.assertEqual(set(SkillPrerequisite.objects.values_list("required_skill_id", flat=True)), {canonical.pk})

    def test_ambiguous_bare_quest_references_reject_but_qualified_names_resolve(self):
        self.load(self.tree(["A", "B"], [{"name": "Twin", "category": category} for category in ("A", "B")]))
        base = {"name": "Exact reading", "description": "Synthetic", "quest_type": "collection", "target_value": 1,
                "trigger_filter": {"allowed_triggers": ["reading_logged"]}}
        for changes in ({"skill_tags": ["Twin"]}, {"required_skill": "Twin", "required_skill_level": 1}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ContentPackError, "ambiguous"):
                self.load({"quests": {"quests": [{**base, **changes}]}})
        self.assertFalse(QuestDefinition.objects.exists())
        self.load({"quests": {"quests": [{**base, "skill_tags": ["A::Twin"],
                                          "required_skill": "B::Twin", "required_skill_level": 1}]}})
        quest = QuestDefinition.objects.get(name=base["name"])
        self.assertEqual(quest.required_skill.category.name, "B")
        self.assertEqual(quest.skill_tags.get().skill.category.name, "A")

    def test_actual_default_reload_keeps_qualified_persistence_after_duplicate_mcp_creation(self):
        parent = make_family(parents=[{"username": "qualified-default-author", "is_staff": True}]).parents[0]
        call_command("loadrpgcontent", stdout=io.StringIO(), stderr=io.StringIO())
        canonical = Skill.objects.get(name="Persistence", category__name="Life Skills")
        other = SkillCategory.objects.create(name="A other category")
        with override_user(parent):
            duplicate = achievements.create_skill(CreateSkillIn(name="Persistence", category_id=other.pk))
        expected_quests = QuestDefinition.objects.count()
        before_ledger = list(CoinLedger.objects.values())
        call_command("loadrpgcontent", stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(QuestDefinition.objects.count(), expected_quests)
        self.assertFalse(QuestDefinition.objects.filter(skill_tags__skill_id=duplicate["id"]).exists())
        self.assertTrue(QuestDefinition.objects.filter(skill_tags__skill=canonical).exists())
        self.assertEqual(list(CoinLedger.objects.values()), before_ledger)
