"""Content skill thresholds stay within the installed native XP curve."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.achievements.models import (
    Badge, Skill, SkillCategory, SkillPrerequisite, SkillProgress, Subject, UserBadge, XP_THRESHOLDS,
)
from apps.achievements.services import BadgeService, SkillService
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.validation import validate_badge_criteria, validate_content
from apps.rpg.models import ContentPackEntry, RPGContentOverride
from config.tests.factories import make_family


LEVEL_CRITERIA = (
    ("skill_level_reached", "level", {"count": 1}),
    ("subjects_completed", "min_level", {"count": 1}),
    ("skill_categories_breadth", "min_level", {"categories": 1}),
    ("category_mastery", "min_level", {"category": "Bounded skills"}),
)


def prerequisite_source(level=2):
    return {"skill_tree": {
        "categories": [{"name": "Bounded skills"}],
        "skills": [
            {"name": "Prerequisite", "category": "Bounded skills", "levels": {"1": "Beginner"}},
            {"name": "Locked destination", "category": "Bounded skills", "locked": True,
             "levels": {"1": "Beginner"}, "prereqs": [{"skill": "Prerequisite", "level": level}]},
        ],
    }}


class ContentRuntimeLevelValidationTests(SimpleTestCase):
    def assert_badge_level_rejected(self, criteria_type, key, other):
        for level in (max(XP_THRESHOLDS) + 1, 100, 1000000):
            with self.subTest(level=level), self.assertRaises(ValidationError):
                validate_badge_criteria(criteria_type, {**other, key: level})

    def test_skill_level_reached_cannot_exceed_runtime_curve(self):
        self.assert_badge_level_rejected(*LEVEL_CRITERIA[0])

    def test_subjects_completed_cannot_exceed_runtime_curve(self):
        self.assert_badge_level_rejected(*LEVEL_CRITERIA[1])

    def test_category_breadth_cannot_exceed_runtime_curve(self):
        self.assert_badge_level_rejected(*LEVEL_CRITERIA[2])

    def test_category_mastery_cannot_exceed_runtime_curve(self):
        self.assert_badge_level_rejected(*LEVEL_CRITERIA[3])

    def test_badges_keep_existing_minimum_one_and_integral_numeric_support(self):
        for criteria_type, key, other in LEVEL_CRITERIA:
            for level in (1, max(XP_THRESHOLDS), float(max(XP_THRESHOLDS))):
                with self.subTest(criteria_type=criteria_type, level=level):
                    validate_badge_criteria(criteria_type, {**other, key: level})
            for level in (0, -1, True, False, "6", 1.5, float("inf"), float("nan")):
                with self.subTest(criteria_type=criteria_type, level=level), self.assertRaises(ValidationError):
                    validate_badge_criteria(criteria_type, {**other, key: level})

    def test_omitted_badge_level_keeps_native_default(self):
        for criteria_type, _key, other in LEVEL_CRITERIA:
            with self.subTest(criteria_type=criteria_type):
                validate_badge_criteria(criteria_type, other)

    def test_other_badge_numbers_are_not_capped_to_skill_levels(self):
        for criteria_type, value in (
            ("skill_level_reached", {"count": 100, "level": 6}),
            ("subjects_completed", {"count": 100, "min_level": 6}),
            ("skill_categories_breadth", {"categories": 100, "min_level": 6}),
            ("total_coins_earned", {"amount": 1000000}),
            ("grade_reached", {"grade": 12}),
            ("late_night", {"hour": 23}),
        ):
            with self.subTest(criteria_type=criteria_type):
                validate_badge_criteria(criteria_type, value)

    def test_badge_ceiling_tracks_runtime_curve_instead_of_a_literal_six(self):
        with patch.dict(XP_THRESHOLDS, {7: 5000}):
            self.assertEqual(SkillService.level_for_xp(5000), 7)
            for criteria_type, key, other in LEVEL_CRITERIA:
                validate_badge_criteria(criteria_type, {**other, key: 7})
                with self.subTest(criteria_type=criteria_type), self.assertRaises(ValidationError):
                    validate_badge_criteria(criteria_type, {**other, key: 8})

    def test_badge_ceiling_also_tracks_a_shorter_runtime_curve(self):
        with patch.dict(XP_THRESHOLDS, {0: 0, 1: 100, 2: 300, 3: 600}, clear=True):
            self.assertEqual(SkillService.level_for_xp(5000), 3)
            with self.assertRaises(ValidationError):
                validate_badge_criteria("skill_level_reached", {"level": 4})

    def test_yaml_prerequisite_cannot_exceed_runtime_curve(self):
        for level in (max(XP_THRESHOLDS) + 1, 100):
            with self.subTest(level=level), self.assertRaises(ContentPackError):
                validate_content(prerequisite_source(level))

    def test_yaml_prerequisite_keeps_supported_zero_and_numeric_coercion(self):
        for level in (0, 1, 6, "6", 6.0):
            with self.subTest(level=level):
                validate_content(prerequisite_source(level))

    def test_yaml_prerequisite_still_rejects_negative_fraction_bool_and_nonfinite(self):
        for level in (-1, True, False, 1.5, float("inf"), float("nan")):
            with self.subTest(level=level), self.assertRaises(ContentPackError):
                validate_content(prerequisite_source(level))

    def test_yaml_prerequisite_ceiling_tracks_runtime_curve(self):
        with patch.dict(XP_THRESHOLDS, {7: 5000}):
            validate_content(prerequisite_source(7))
            with self.assertRaises(ContentPackError):
                validate_content(prerequisite_source(8))

    def test_reviewed_badge_yaml_rejects_out_of_curve_level(self):
        for criteria_type, key, other in LEVEL_CRITERIA:
            with self.subTest(criteria_type=criteria_type), self.assertRaises(ContentPackError):
                validate_content({"badges": {"badges": [{"name": "Unreachable new badge",
                    "criteria_type": criteria_type, "criteria_value": {**other, key: 7}}]}}, strict=True)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ContentRuntimeLevelNativeTests(TestCase):
    def setUp(self):
        family = make_family("Native content level bounds", parents=[{
            "username": "level-bounds-parent", "is_staff": True,
        }], children=[{"username": "level-bounds-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        directory = TemporaryDirectory(prefix="abby-content-level-bounds-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)

    def load(self, parsed):
        return ContentPack(self.path, parsed_content=parsed, pack_key="level-bounds",
            namespace="level-bounds-", family=self.parent.family).load(stdout=StringIO())

    def test_invalid_prerequisite_rejected_before_catalog_or_metadata_upserts(self):
        before = [model.objects.count() for model in (SkillCategory, Skill, SkillPrerequisite,
                  ContentPackEntry, RPGContentOverride)]
        with self.assertRaises(ContentPackError):
            self.load(prerequisite_source(7))
        self.assertEqual(before, [model.objects.count() for model in (SkillCategory, Skill, SkillPrerequisite,
                         ContentPackEntry, RPGContentOverride)])

    def test_maximum_valid_prerequisite_unlocks_at_actual_native_level_six(self):
        self.load(prerequisite_source(max(XP_THRESHOLDS)))
        source = Skill.objects.get(name="Prerequisite")
        destination = Skill.objects.get(name="Locked destination")
        self.assertEqual(SkillPrerequisite.objects.get(skill=destination).required_level, 6)
        maximum_xp = XP_THRESHOLDS[max(XP_THRESHOLDS)]
        self.assertEqual(SkillService.award_xp(self.child, source, maximum_xp - 1).level, 5)
        self.assertFalse(SkillProgress.objects.get(user=self.child, skill=destination).unlocked)
        self.assertEqual(SkillService.award_xp(self.child, source, 1).level, 6)
        self.assertTrue(SkillProgress.objects.get(user=self.child, skill=destination).unlocked)

    def test_level_zero_yaml_prerequisite_keeps_existing_native_progress_row_gate(self):
        self.load(prerequisite_source(0))
        source = Skill.objects.get(name="Prerequisite")
        destination = Skill.objects.get(name="Locked destination")
        SkillService.evaluate_unlocks(self.child)
        self.assertFalse(SkillProgress.objects.get(user=self.child, skill=destination).unlocked)
        self.assertEqual(SkillService.award_xp(self.child, source, 1).level, 0)
        self.assertTrue(SkillProgress.objects.get(user=self.child, skill=destination).unlocked)

    def test_shorthand_prerequisite_keeps_native_default_level_two(self):
        parsed = prerequisite_source()
        parsed["skill_tree"]["skills"][1]["prereqs"] = ["Prerequisite"]
        self.load(parsed)
        destination = Skill.objects.get(name="Locked destination")
        self.assertEqual(SkillPrerequisite.objects.get(skill=destination).required_level, 2)

    def test_valid_maximum_badges_award_through_all_native_skill_level_criteria(self):
        category = SkillCategory.objects.create(name="Bounded skills")
        subject = Subject.objects.create(name="Bounded subject", category=category)
        skill = Skill.objects.create(name="Bounded practice", category=category, subject=subject)
        badges = []
        for index, (criteria_type, key, other) in enumerate(LEVEL_CRITERIA):
            criteria = {**other, key: max(XP_THRESHOLDS)}
            validate_badge_criteria(criteria_type, criteria)
            badges.append(Badge.objects.create(name=f"Native maximum {index}", criteria_type=criteria_type,
                criteria_value=criteria, xp_bonus=0, award_coins=False))
        self.assertEqual(SkillService.award_xp(self.child, skill, 1000000).level, 6)
        BadgeService.evaluate_badges(self.child, scopes={"skill_xp", "badges"})
        self.assertEqual(set(UserBadge.objects.filter(user=self.child).values_list("badge_id", flat=True)),
                         {badge.pk for badge in badges})

    def test_new_validation_does_not_rewrite_legacy_invalid_rows_or_earned_history(self):
        category = SkillCategory.objects.create(name="Bounded skills")
        source = Skill.objects.create(name="Legacy source", category=category)
        destination = Skill.objects.create(name="Legacy destination", category=category, is_locked_by_default=True)
        prerequisite = SkillPrerequisite.objects.create(skill=destination, required_skill=source, required_level=7)
        badge = Badge.objects.create(name="Legacy earned level seven", criteria_type="skill_level_reached",
            criteria_value={"level": 7}, xp_bonus=0, award_coins=False)
        earned = UserBadge.objects.create(user=self.child, badge=badge)
        before = (list(SkillPrerequisite.objects.filter(pk=prerequisite.pk).values()),
                  list(Badge.objects.filter(pk=badge.pk).values()), list(UserBadge.objects.filter(pk=earned.pk).values()))
        with self.assertRaises(ValidationError):
            validate_badge_criteria("skill_level_reached", {"level": 7})
        with self.assertRaises(ContentPackError):
            validate_content(prerequisite_source(7))
        self.assertEqual(before, (list(SkillPrerequisite.objects.filter(pk=prerequisite.pk).values()),
            list(Badge.objects.filter(pk=badge.pk).values()), list(UserBadge.objects.filter(pk=earned.pk).values())))
