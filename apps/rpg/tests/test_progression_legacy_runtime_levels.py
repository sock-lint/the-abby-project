"""Detached Lab criteria preserve native legacy IntegerField threshold semantics."""
from collections import Counter
from copy import deepcopy

from django.test import TestCase, override_settings

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, Subject, UserBadge, XP_THRESHOLDS
from apps.achievements.services import BadgeService
from apps.rpg.progression.catalog import _record, load_catalog
from apps.rpg.progression.engine import Trial
from apps.rpg.tests.test_progression_engine import quiet_config
from config.tests.factories import make_family


LEVEL_CRITERIA = (
    ("skill_level_reached", "level", {"count": 1}),
    ("subjects_completed", "min_level", {"count": 1}),
    ("skill_categories_breadth", "min_level", {"categories": 1}),
    ("category_mastery", "min_level", {"category": "Language Arts"}),
)
LEGACY_LEVELS = ("2", " 2 ", 1.5, 0, -1, True, False, "6", 6.9)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProgressionLegacyRuntimeLevelTests(TestCase):
    def setUp(self):
        family = make_family(children=[{"username": "lab-legacy-level-child"}])
        self.child = family.children[0]
        self.category = SkillCategory.objects.create(name="Language Arts")
        self.subject = Subject.objects.create(name="Reading", category=self.category)
        self.skill = Skill.objects.create(
            name="Reading Comprehension", category=self.category, subject=self.subject,
        )
        self.catalog = load_catalog()
        self._badge_number = 0

    def badge(self, case, raw_level, *, save=False):
        kind, field, other = case
        self._badge_number += 1
        badge = Badge(
            name=f"Legacy {kind} {self._badge_number}", description="Synthetic native-compatible retained criterion",
            criteria_type=kind, criteria_value={**other, field: raw_level},
            xp_bonus=0, award_coins=False,
        )
        if save:
            badge.save()
        return badge

    def test_native_and_detached_criteria_agree_on_each_side_of_legacy_thresholds(self):
        progress = SkillProgress.objects.create(user=self.child, skill=self.skill)
        for level in (0, 1, 2, max(XP_THRESHOLDS)):
            progress.level, progress.xp_points = level, XP_THRESHOLDS[level]
            progress.save(update_fields=["level", "xp_points"])
            trial = Trial(quiet_config(reading_minutes=10), self.catalog, 1)
            trial.xp = Counter({self.skill.pk: progress.xp_points})
            trial.total_xp = progress.xp_points
            for case in LEVEL_CRITERIA:
                for raw_level in LEGACY_LEVELS:
                    with self.subTest(level=level, kind=case[0], threshold=raw_level):
                        badge = self.badge(case, raw_level)
                        expected = BadgeService._check_criteria(self.child, badge)
                        detached = _record(badge)
                        with self.assertNumQueries(0):
                            actual = trial._badge_matches(detached)
                        self.assertEqual(actual, expected)

    def test_zero_or_false_mastery_waits_for_an_actual_modeled_progress_row(self):
        for raw_level in (0, False, -1):
            with self.subTest(threshold=raw_level):
                badge = self.badge(LEVEL_CRITERIA[-1], raw_level)
                trial = Trial(quiet_config(reading_minutes=10), self.catalog, 1)
                self.assertFalse(BadgeService._check_criteria(self.child, badge))
                with self.assertNumQueries(0):
                    self.assertFalse(trial._badge_matches(_record(badge)))
                trial.daily(1)
                progress = SkillProgress.objects.create(
                    user=self.child, skill=self.skill, level=0, xp_points=15,
                )
                self.assertTrue(BadgeService._check_criteria(self.child, badge))
                with self.assertNumQueries(0):
                    self.assertTrue(trial._badge_matches(_record(badge)))
                progress.delete()

    def test_retained_string_goals_load_enter_finite_capacity_and_earn_like_native(self):
        badges = [self.badge(case, "2", save=True) for case in LEVEL_CRITERIA]
        original = {badge.pk: deepcopy(badge.criteria_value) for badge in badges}
        catalog = load_catalog()
        self.assertEqual({badge.pk for badge in catalog.badges}, set(original))
        trial = Trial(quiet_config(reading_minutes=10), catalog, 1)
        self.assertTrue({f"badge:{pk}" for pk in original} <= trial.finite_keys)
        self.assertFalse(trial.badges)
        with self.assertNumQueries(0):
            for day in range(1, 21):
                trial.daily(day)
        self.assertEqual(trial.badges, set(original))
        SkillProgress.objects.create(
            user=self.child, skill=self.skill, level=2, xp_points=XP_THRESHOLDS[2],
        )
        self.assertEqual(
            {badge.pk for badge in BadgeService.evaluate_badges(self.child, scopes={"skill_xp"})},
            trial.badges,
        )
        self.assertEqual(set(UserBadge.objects.filter(user=self.child).values_list("badge_id", flat=True)), trial.badges)
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"skill_xp"}), [])
        self.assertEqual(dict(Badge.objects.values_list("pk", "criteria_value")), original)
        self.assertEqual(
            {badge.pk: dict(badge.criteria_value) for badge in catalog.badges}, original,
        )

    def test_fractional_rounding_is_reused_by_finite_capacity_without_changing_source(self):
        badges = [self.badge(case, 6.9, save=True) for case in LEVEL_CRITERIA]
        catalog = load_catalog()
        self.assertEqual({badge.pk for badge in catalog.badges}, {badges[-1].pk})
        self.assertEqual(catalog.badges[0].criteria_value["min_level"], 6.9)
        trial = Trial(quiet_config(reading_minutes=10), catalog, 1)
        self.assertIn(f"badge:{badges[-1].pk}", trial.finite_keys)
        SkillProgress.objects.create(
            user=self.child, skill=self.skill, level=max(XP_THRESHOLDS),
            xp_points=XP_THRESHOLDS[max(XP_THRESHOLDS)],
        )
        self.assertEqual(
            [badge_goal_is_available(badge) for badge in badges], [False, False, False, True],
        )
        self.assertEqual(
            [BadgeService._check_criteria(self.child, badge) for badge in badges], [False, False, False, True],
        )
        mastery = badges[-1]
        before = catalog.fingerprint
        mastery.criteria_value = {**mastery.criteria_value, "min_level": 6}
        mastery.save(update_fields=["criteria_value"])
        self.assertNotEqual(before, load_catalog().fingerprint)
        self.assertEqual(catalog.badges[0].criteria_value["min_level"], 6.9)

    def test_unreachable_or_noncoercible_goals_do_not_enter_loaded_lab_catalog(self):
        for case in LEVEL_CRITERIA:
            for raw_level in (7, "7", None, "1.5", "bad-level", {}, []):
                with self.subTest(kind=case[0], threshold=raw_level):
                    badge = self.badge(case, raw_level, save=True)
                    self.assertFalse(badge_goal_is_available(badge))
        catalog = load_catalog()
        self.assertFalse(catalog.badges)
        trial = Trial(quiet_config(reading_minutes=10), catalog, 1)
        with self.assertNumQueries(0):
            trial.daily(1)
        self.assertEqual(trial.source_totals["reading"]["xp"], 15)
        self.assertFalse(trial.badges)
