"""Catalog inspection uses authored rows and effective runtime rules without writes."""
import re

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError

from apps.achievements.models import (
    Badge, Skill, SkillCategory, SkillPrerequisite, SkillProgress, Subject,
)
from apps.mcp_server.context import override_user
from apps.mcp_server.catalog_schemas import CatalogPageIn
from apps.mcp_server.tools import catalog as tools
from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rpg.models import CharacterProfile, DropTable, ItemDefinition
from config.tests.factories import make_family


SYNTHETIC_POLICY = {
    "schema_version": 1,
    "pets": [{"species_slug": "audit-fox", "sprite_key": "audit-fox-art", "potion_slugs": ["audit-base"]}],
    "potion_slugs": ["audit-base"],
    "disabled_item_types": ["cosmetic_pet_accessory"],
}
SECTIONS = ("categories", "subjects", "skills", "badges", "quests", "items", "drops", "pet_species", "potion_types")


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=SYNTHETIC_POLICY,
)
class CatalogInspectionTests(TestCase):
    def setUp(self):
        family = make_family(
            "Catalog inspection family", parents=[{"username": "catalog-inspector", "is_staff": True}],
            children=[{"username": "catalog-inspector-child"}],
        )
        other = make_family("Other catalog family", parents=[{"username": "other-catalog-parent"}])
        self.parent = family.parents[0]
        self.category = SkillCategory.objects.create(name="Catalog making")
        self.subject = Subject.objects.create(name="Tools", category=self.category)
        self.skill = Skill.objects.create(name="Safe measuring", category=self.category, subject=self.subject)
        self.base = PotionType.objects.create(slug="audit-base", name="Audit base")
        self.fox = PetSpecies.objects.create(slug="audit-fox", sprite_key="audit-fox-art", name="Audit Fox", icon="F")
        self.fox.available_potions.add(self.base)
        self.unsupported = PetSpecies.objects.create(slug="audit-moth", sprite_key="audit-moth-art", name="Audit Moth", icon="M")
        self.unsupported.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(
            slug="audit-fox-egg", name="Audit Fox egg", item_type="egg", icon="E", pet_species=self.fox,
        )
        self.unavailable_egg = ItemDefinition.objects.create(
            slug="audit-moth-egg", name="Audit Moth egg", item_type="egg", icon="E", pet_species=self.unsupported,
        )
        self.frame = ItemDefinition.objects.create(
            slug="audit-frame", name="Audit frame", item_type="cosmetic_frame", icon="F", metadata={"border_color": "#abcdef"},
        )
        self.badge = Badge.objects.create(
            name="Unavailable accessory collection", criteria_type="cosmetic_full_set", criteria_value={}, xp_bonus=15,
        )
        self.quest = QuestDefinition.objects.create(
            name="Global learning quest", description="Catalog-only synthetic quest", quest_type="collection",
            target_value=2, is_system=True, xp_reward=15, required_badge=self.badge,
            trigger_filter={"allowed_triggers": ["milestone_complete"]},
        )
        QuestSkillTag.objects.create(quest_definition=self.quest, skill=self.skill, xp_weight=2)
        QuestRewardItem.objects.create(quest_definition=self.quest, item=self.egg, quantity=1)
        QuestRewardItem.objects.create(quest_definition=self.quest, item=self.unavailable_egg, quantity=2)
        self.own_custom = QuestDefinition.objects.create(
            name="Private same-family quest", description="Must not leave this family", quest_type="collection",
            target_value=1, created_by=self.parent, is_system=False,
        )
        self.other_custom = QuestDefinition.objects.create(
            name="Private foreign quest", description="Must not reach catalog inspection", quest_type="collection",
            target_value=1, created_by=other.parents[0], is_system=False,
        )
        DropTable.objects.create(trigger_type="milestone_complete", item=self.egg, weight=2)

    def read(self, section, **page):
        with override_user(self.parent):
            return tools.read_rpg_catalog(CatalogPageIn(section=section, **page))

    def audit(self, section, **page):
        with override_user(self.parent):
            return tools.audit_rpg_catalog(CatalogPageIn(section=section, **page))

    def test_all_sections_are_read_only_even_without_user_profile_or_progress(self):
        CharacterProfile.objects.all().delete()
        SkillProgress.objects.all().delete()
        with CaptureQueriesContext(connection) as queries:
            for section in SECTIONS:
                read = self.read(section)
                audit = self.audit(section)
                self.assertEqual(read["section"], section)
                self.assertGreater(read["total"], 0)
                self.assertIsInstance(read["results"], list)
                self.assertEqual(audit["checked"], len(read["results"]))
        mutations = [row["sql"] for row in queries if re.match(r"\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP)\b", row["sql"], re.I)]
        self.assertEqual(mutations, [])
        self.assertEqual(CharacterProfile.objects.count(), 0)
        self.assertEqual(SkillProgress.objects.count(), 0)

    def test_sparse_primary_key_cursor_keeps_total_and_never_repeats_rows(self):
        extra = [SkillCategory.objects.create(pk=offset, name=f"Catalog category {offset}") for offset in (20, 70, 900)]
        expected = sorted([self.category.pk, *(row.pk for row in extra)])
        first = self.read("categories", limit=2)
        self.assertEqual(first["total"], 4)
        self.assertEqual(first["after"], 0)
        self.assertEqual([row["id"] for row in first["results"]], expected[:2])
        self.assertEqual(first["next_after"], expected[1])
        second = self.read("categories", after=first["next_after"], limit=2)
        self.assertEqual(second["total"], 4)
        self.assertEqual([row["id"] for row in second["results"]], expected[2:])
        self.assertIsNone(second["next_after"])
        empty = self.read("categories", after=900, limit=2)
        self.assertEqual((empty["total"], empty["results"], empty["next_after"]), (4, [], None))
        audited = self.audit("categories", after=20, limit=1)
        self.assertEqual((audited["total"], audited["checked"], audited["next_after"]), (4, 1, 70))

    def test_catalog_quests_exclude_both_same_family_and_foreign_custom_content(self):
        page = self.read("quests")
        self.assertEqual(page["total"], 1)
        self.assertEqual([row["id"] for row in page["results"]], [self.quest.pk])
        serialized = str(page)
        self.assertNotIn(self.own_custom.name, serialized)
        self.assertNotIn(self.other_custom.name, serialized)
        self.assertEqual(self.audit("quests")["total"], 1)

    def test_runtime_support_and_authored_unavailable_rewards_are_both_visible(self):
        rows = {row["id"]: row for row in self.read("items")["results"]}
        self.assertTrue(rows[self.egg.pk]["runtime_available"])
        self.assertIsNone(rows[self.egg.pk]["unavailable_reason"])
        self.assertFalse(rows[self.unavailable_egg.pk]["runtime_available"])
        self.assertTrue(rows[self.unavailable_egg.pk]["unavailable_reason"])
        self.assertEqual(rows[self.frame.pk]["metadata"], {"border_color": "#abcdef"})
        self.assertEqual(rows[self.egg.pk]["coin_value"], 0)
        quest = self.read("quests")["results"][0]
        self.assertEqual(quest["trigger_filter"], {"allowed_triggers": ["milestone_complete"]})
        self.assertEqual(len(quest["skill_tags"]), 1)
        rewards = quest["reward_items"]
        self.assertEqual(len(rewards), 2, "Catalog inspection must retain authored rewards hidden from new acquisition")
        def item_id(reward):
            return reward.get("item_id") or (reward["item"]["id"] if isinstance(reward.get("item"), dict) else reward.get("item"))
        unavailable = next(reward for reward in rewards if item_id(reward) == self.unavailable_egg.pk)
        self.assertEqual(unavailable["quantity"], 2)
        self.assertFalse(unavailable["runtime_available"])
        self.assertFalse(self.read("badges")["results"][0]["available_for_new_user"])

    def test_audit_flags_effective_reward_and_required_badge_failures(self):
        page = self.audit("quests")
        self.assertEqual(page["checked"], 1)
        codes = {finding["code"] for finding in page["findings"]}
        self.assertTrue({"unsupported_reward_item", "unreachable_required_badge"}.issubset(codes))
        for finding in page["findings"]:
            self.assertEqual((finding["section"], finding["id"]), ("quests", self.quest.pk))
            self.assertTrue(finding["detail"])
        badge_findings = self.audit("badges")["findings"]
        self.assertIn("unreachable_badge", {finding["code"] for finding in badge_findings})

    def test_audit_reports_invalid_authored_filters_unknown_effects_and_untargeted_xp(self):
        invalid = QuestDefinition.objects.create(
            name="Malformed global quest", description="Synthetic invalid stored content", quest_type="collection",
            target_value=1, is_system=True, xp_reward=10, trigger_filter={"allowed_trigger": ["made_up"]},
        )
        consumable = ItemDefinition.objects.create(
            slug="audit-unknown-effect", name="Unknown effect", icon="?", item_type="consumable", metadata={"effect": "invented_effect"},
        )
        findings = self.audit("quests")["findings"]
        invalid_codes = {row["code"] for row in findings if row["id"] == invalid.pk}
        self.assertTrue({"invalid_trigger_filter", "xp_without_skill_targets"}.issubset(invalid_codes))
        item_findings = self.audit("items")["findings"]
        self.assertTrue(any(row["code"] == "unknown_consumable_effect" and row["id"] == consumable.pk for row in item_findings))

    def test_malformed_badge_criteria_returns_a_finding_without_crashing(self):
        malformed = Badge.objects.create(
            name="Malformed count", criteria_type="pet_species_owned", criteria_value={"count": "not-an-integer"},
        )
        page = self.audit("badges")
        self.assertTrue(any(row["id"] == malformed.pk and row["section"] == "badges" and row["code"] == "invalid_badge_criteria" and row["detail"] for row in page["findings"]))

    def test_skill_prerequisite_cycles_are_detected_without_unlocking_progress(self):
        second = Skill.objects.create(name="Circular skill", category=self.category)
        SkillPrerequisite.objects.create(skill=self.skill, required_skill=second)
        SkillPrerequisite.objects.create(skill=second, required_skill=self.skill)
        findings = self.audit("skills")["findings"]
        cycles = [row for row in findings if row["code"] == "skill_cycle"]
        self.assertTrue(cycles)
        self.assertTrue({row["id"] for row in cycles}.issubset({self.skill.pk, second.pk}))
        self.assertFalse(SkillProgress.objects.exists())

    def test_page_input_is_bounded_and_rejects_unknown_sections(self):
        for params in ({"section": "families"}, {"section": "items", "limit": 101}, {"section": "items", "limit": 0}, {"section": "items", "after": -1}):
            with self.assertRaises(ValidationError):
                CatalogPageIn(**params)

    def test_missing_typed_species_reference_and_drop_trigger_are_reported(self):
        orphan = ItemDefinition.objects.create(
            slug="audit-orphan-egg", name="Unbound egg", icon="E", item_type="egg", metadata={"species": "never-authored"},
        )
        drop = DropTable.objects.create(trigger_type="invented_trigger", item=self.unavailable_egg, weight=1)
        self.assertTrue(any(row["code"] == "orphan_reference" and row["id"] == orphan.pk for row in self.audit("items")["findings"]))
        findings = [row for row in self.audit("drops")["findings"] if row["id"] == drop.pk]
        self.assertTrue({"invalid_trigger_filter", "unsupported_reward_item"}.issubset({row["code"] for row in findings}))

    def test_registered_consumable_effect_uses_runtime_registry(self):
        item = ItemDefinition.objects.create(
            slug="audit-known-effect", name="Streak preservation", icon="S", item_type="consumable", metadata={"effect": "streak_freeze"},
        )
        findings = self.audit("items")["findings"]
        self.assertFalse(any(row["code"] == "unknown_consumable_effect" and row["id"] == item.pk for row in findings))

    def test_malformed_nested_trigger_values_report_findings_without_crashing(self):
        malformed = QuestDefinition.objects.create(
            name="Malformed nested trigger", description="A historical malformed JSON filter", quest_type="collection",
            target_value=1, is_system=True, trigger_filter={"allowed_triggers": [{"unexpected": "object"}]},
        )
        findings = self.audit("quests")["findings"]
        self.assertTrue(any(row["code"] == "invalid_trigger_filter" and row["id"] == malformed.pk for row in findings))

    def test_nonstring_consumable_effect_is_reported_without_set_membership_failure(self):
        malformed = ItemDefinition.objects.create(
            slug="audit-malformed-effect", name="Malformed effect metadata", icon="?", item_type="consumable", metadata={"effect": {"unexpected": "object"}},
        )
        self.assertTrue(any(row["code"] == "unknown_consumable_effect" and row["id"] == malformed.pk for row in self.audit("items")["findings"]))
