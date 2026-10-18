"""Artwork is a read-only, exact semantic projection of existing content."""
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from apps.achievements.models import Badge, Skill, SkillCategory, Subject
from apps.achievements.serializers import (
    BadgeSerializer, SkillCategorySerializer, SkillSerializer, SubjectSerializer,
)
from apps.quests.models import QuestDefinition
from apps.rpg.catalog_icons import challenge_catalog_icon, item_catalog_icon
from apps.rpg.catalog_support import item_is_available
from apps.rpg.models import ItemDefinition


class ArtworkImageIdentityTests(TestCase):
    def test_badge_uses_exact_final_criterion_and_preserves_authored_glyph(self):
        badge = Badge(name="10-Hour Club", icon="TEN", criteria_type="hours_worked", criteria_value={"hours": 10})
        result = BadgeSerializer(badge).data
        self.assertEqual(result.get("catalog_icon"), "badge-10-hour-club")
        self.assertEqual(result["icon"], "TEN")
        for changes in ({"criteria_type": "days_worked"}, {"criteria_value": {"hours": 1}}, {"name": "Custom 10-Hour Club"}):
            other = Badge(name=badge.name, criteria_type=badge.criteria_type, criteria_value=badge.criteria_value)
            for key, value in changes.items():
                setattr(other, key, value)
            self.assertIsNone(BadgeSerializer(other).data.get("catalog_icon"))

    def test_skill_and_subject_require_category_and_authored_parent(self):
        coding = SkillCategory.objects.create(name="Coding", icon="CODE")
        languages = Subject.objects.create(category=coding, name="Languages & Apps", icon="APPS")
        skill = Skill.objects.create(category=coding, subject=languages, name="Python", icon="PYTHON")
        self.assertEqual(SkillCategorySerializer(coding).data.get("catalog_icon"), "category-coding")
        self.assertEqual(SubjectSerializer(languages).data.get("catalog_icon"), "subject-coding-languages-apps")
        self.assertEqual(SkillSerializer(skill).data.get("catalog_icon"), "skill-coding-python")
        other = SkillCategory.objects.create(name="Custom Coding")
        wrong_parent = Subject.objects.create(category=other, name=languages.name)
        skill.subject = wrong_parent
        self.assertIsNone(SkillSerializer(skill).data.get("catalog_icon"))
        self.assertIsNone(SubjectSerializer(wrong_parent).data.get("catalog_icon"))
        skill.subject = None
        self.assertIsNone(SkillSerializer(skill).data.get("catalog_icon"))
        skill.subject = languages
        skill.category = other
        self.assertIsNone(SkillSerializer(skill).data.get("catalog_icon"))

    def test_item_and_challenge_art_does_not_enable_content_or_match_custom_names(self):
        crown = ItemDefinition(slug="accessory-crown", name="Crown", item_type="cosmetic_pet_accessory")
        self.assertEqual(item_catalog_icon(crown), "item-accessory-crown")
        self.assertFalse(item_is_available(crown))
        for slug, name, kind in [("custom-crown", "Crown", "cosmetic_pet_accessory"),
                                 ("accessory-crown", "Other", "cosmetic_pet_accessory"),
                                 ("accessory-crown", "Crown", "food")]:
            self.assertIsNone(item_catalog_icon(ItemDefinition(slug=slug, name=name, item_type=kind)))
        birthday = QuestDefinition(name="Birthday Week", quest_type="collection", is_system=True)
        self.assertEqual(challenge_catalog_icon(birthday), "challenge-birthday-week")
        birthday.is_system = False
        self.assertIsNone(challenge_catalog_icon(birthday))
        birthday.is_system, birthday.quest_type = True, "boss"
        self.assertIsNone(challenge_catalog_icon(birthday))


class AuthoredArtworkImageIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        for pack in ("hs-prep-2026", "sleep-prep-2026", "spring-2026", "summer-2026", "birthday-pack", "year-in-review-pack"):
            call_command("loadrpgcontent", pack=str(Path(settings.BASE_DIR) / "content/rpg/packs" / pack),
                         namespace=f"{pack}-", stdout=StringIO())

    def test_every_new_record_binding_matches_the_actual_final_authored_catalog(self):
        from apps.rpg.catalog_icons import artwork_bindings, badge_catalog_icon, category_catalog_icon, skill_catalog_icon, subject_catalog_icon

        registry = artwork_bindings()
        self.assertEqual({group: len(registry[group]) for group in ("badges", "categories", "items", "challenges")},
                         {"badges": 182, "categories": 14, "items": 33, "challenges": 5})
        self.assertEqual(sum(map(len, registry["subjects"].values())), 34)
        self.assertEqual(sum(map(len, registry["skills"].values())), 96)
        for name, row in registry["badges"].items():
            with self.subTest(badge=name):
                self.assertEqual(badge_catalog_icon(Badge.objects.get(name=name)), row["asset_id"])
        for name, row in registry["categories"].items():
            self.assertEqual(category_catalog_icon(SkillCategory.objects.get(name=name)), row["asset_id"])
        for group, model, resolver in (("subjects", Subject, subject_catalog_icon), ("skills", Skill, skill_catalog_icon)):
            for category, rows in registry[group].items():
                for name, row in rows.items():
                    with self.subTest(group=group, category=category, name=name):
                        self.assertEqual(resolver(model.objects.get(category__name=category, name=name)), row["asset_id"])
        for slug, row in registry["items"].items():
            with self.subTest(item=slug):
                self.assertEqual(item_catalog_icon(ItemDefinition.objects.get(slug=slug)), row["asset_id"])
        for name, row in registry["challenges"].items():
            with self.subTest(challenge=name):
                self.assertEqual(challenge_catalog_icon(QuestDefinition.objects.get(name=name, is_system=True)), row["asset_id"])

    def test_final_same_name_updates_match_the_existing_badges_without_awards(self):
        from apps.rpg.catalog_icons import badge_catalog_icon

        for name in ("Polymath", "Hour One", "First Spark", "Spring Bloom Collector"):
            self.assertIsNotNone(badge_catalog_icon(Badge.objects.get(name=name)))
        self.assertEqual(Badge.objects.get(name="Polymath").criteria_type, "creation_skill_breadth")
        self.assertEqual(Badge.objects.get(name="Hour One").criteria_value, {"minutes": 60})
