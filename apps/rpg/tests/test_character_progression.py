from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, XP_THRESHOLDS
from apps.achievements.services import BadgeService, SkillService
from apps.notifications.models import Notification
from apps.rpg.models import CharacterProfile
from apps.rpg.services import GameLoopService
from config.tests.factories import make_family


class CharacterProgressionTests(TestCase):
    def setUp(self):
        household = make_family(children=[{"username": "progression-child"}])
        self.child = household.children[0]
        category = SkillCategory.objects.create(name="Overall progression")
        self.skill = Skill.objects.create(name="Reading", category=category)
        self.other = Skill.objects.create(name="Drawing", category=category)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def character(self):
        response = self.client.get("/api/character/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_new_character_has_empty_readonly_progress(self):
        payload = self.character()
        self.assertEqual(payload["total_xp"], 0)
        self.assertEqual(payload["xp_in_level"], 0)
        self.assertEqual(payload["xp_needed_for_level"], 100)
        from apps.rpg.serializers import CharacterProfileSerializer
        serializer = CharacterProfileSerializer()
        for field in ("total_xp", "xp_in_level", "xp_needed_for_level", "level"):
            self.assertTrue(serializer.fields[field].read_only)

    def test_actual_skill_awards_persist_overall_level_and_api_progress(self):
        SkillService.award_xp(self.child, self.skill, 125)
        self.child.character_profile.refresh_from_db()
        self.assertEqual(self.child.character_profile.level, 1)
        payload = self.character()
        self.assertEqual((payload["level"], payload["total_xp"], payload["xp_in_level"], payload["xp_needed_for_level"]), (1, 125, 25, 200))

    def test_credit_across_skills_uses_total_saved_xp(self):
        SkillService.award_xp(self.child, self.skill, 60)
        SkillService.award_xp(self.child, self.other, 60)
        payload = self.character()
        self.assertEqual(payload["level"], 1)
        self.assertEqual(payload["total_xp"], 120)
        self.assertEqual(payload["xp_in_level"], 20)
        self.assertEqual(payload["xp_needed_for_level"], 200)
        self.assertEqual(list(SkillProgress.objects.filter(user=self.child).values_list("xp_points", flat=True)), [60, 60])

    def test_existing_thresholds_and_max_level_are_shared(self):
        for level, threshold in sorted(XP_THRESHOLDS.items()):
            with self.subTest(level=level):
                SkillProgress.objects.filter(user=self.child).delete()
                SkillService.award_xp(self.child, self.skill, threshold)
                payload = self.character()
                self.assertEqual(payload["level"], level)
                self.assertEqual(payload["total_xp"], threshold)
                self.assertEqual(payload["xp_in_level"], 0)
                width = XP_THRESHOLDS.get(level + 1, threshold) - threshold
                self.assertEqual(payload["xp_needed_for_level"], width)
        SkillService.award_xp(self.child, self.skill, 10000)
        payload = self.character()
        self.assertEqual((payload["level"], payload["total_xp"], payload["xp_in_level"], payload["xp_needed_for_level"]), (6, 12500, 0, 0))

    def test_locked_skill_award_does_not_invent_character_xp(self):
        self.skill.is_locked_by_default = True
        self.skill.save(update_fields=["is_locked_by_default"])
        SkillService.award_xp(self.child, self.skill, 2500)
        payload = self.character()
        self.assertEqual((payload["level"], payload["total_xp"]), (0, 0))

    def test_negative_legacy_adjustment_keeps_saved_total_and_level_floor(self):
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=-10, level=0)
        SkillService.award_xp(self.child, self.other, 5)
        payload = self.character()
        self.assertEqual((payload["level"], payload["total_xp"], payload["xp_in_level"]), (0, -5, 0))

    def test_badge_bonus_synchronizes_the_aggregate_level(self):
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=100, level=1)
        SkillProgress.objects.create(user=self.child, skill=self.other, xp_points=100, level=1)
        badge = Badge.objects.create(name="Overall bonus", criteria_type="skill_level_reached", xp_bonus=101)
        BadgeService._award_badge_xp(self.child, badge)
        payload = self.character()
        self.assertEqual((payload["level"], payload["total_xp"]), (2, 300))
        self.assertEqual(list(SkillProgress.objects.filter(user=self.child).values_list("xp_points", flat=True)), [150, 150])

    def test_character_sync_failure_rolls_back_skill_xp(self):
        save = CharacterProfile.save

        def fail_level_save(profile, *args, **kwargs):
            if "level" in kwargs.get("update_fields", []):
                save(profile, *args, **kwargs)
                raise RuntimeError("profile failure")
            return save(profile, *args, **kwargs)

        with patch.object(CharacterProfile, "save", fail_level_save):
            with self.assertRaisesMessage(RuntimeError, "profile failure"):
                SkillService.award_xp(self.child, self.skill, 125)
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())
        self.child.character_profile.refresh_from_db()
        self.assertEqual(self.child.character_profile.level, 0)

    def test_reading_character_preserves_manual_legacy_level(self):
        profile = self.child.character_profile
        profile.level = 4
        profile.save(update_fields=["level"])
        self.assertEqual(self.character()["level"], 4)
        profile.refresh_from_db()
        self.assertEqual(profile.level, 4)

    def test_character_sync_failure_rolls_back_badge_xp(self):
        progress = SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=100, level=1)
        badge = Badge.objects.create(name="Retryable overall bonus", criteria_type="skill_level_reached", xp_bonus=250)
        with patch.object(CharacterProfile, "save", side_effect=RuntimeError("profile failure")):
            with self.assertRaisesMessage(RuntimeError, "profile failure"):
                BadgeService._award_badge_xp(self.child, badge)
        progress.refresh_from_db()
        self.assertEqual((progress.xp_points, progress.level), (100, 1))
        self.child.character_profile.refresh_from_db()
        self.assertEqual(self.child.character_profile.level, 0)


class StreakMilestoneOnceTests(TestCase):
    def test_repeated_activities_only_notify_when_milestone_is_reached(self):
        child = make_family(children=[{"username": "once-streak-child"}]).children[0]
        profile = child.character_profile
        profile.login_streak = 2
        profile.last_active_date = timezone.localdate() - timedelta(days=1)
        profile.save(update_fields=["login_streak", "last_active_date"])
        first = GameLoopService.on_task_completed(child, "habit_log", {"drops_allowed": False})
        second = GameLoopService.on_task_completed(child, "habit_log", {"drops_allowed": False})
        self.assertEqual(Notification.objects.filter(user=child, notification_type="streak_milestone").count(), 1)
        self.assertIn("3-day streak milestone", first["notifications"])
        self.assertNotIn("3-day streak milestone", second["notifications"])


class CharacterLevelBackfillTests(TestCase):
    def test_historical_sync_uses_frozen_curve_and_preserves_all_awards(self):
        household = make_family(children=[{"username": "historical-level-child"}, {"username": "empty-level-child"}, {"username": "negative-level-child"}])
        child, empty, negative = household.children
        category = SkillCategory.objects.create(name="Historical character")
        for name in ("Read", "Draw"):
            skill = Skill.objects.create(name=name, category=category)
            SkillProgress.objects.create(user=child, skill=skill, xp_points=75, level=0)
        SkillProgress.objects.create(user=negative, skill=skill, xp_points=-1, level=0)
        CharacterProfile.objects.filter(user=negative).update(level=4)
        CharacterProfile.objects.filter(user=child).update(level=0, perfect_days_count=2)
        CharacterProfile.objects.filter(user=empty).update(level=5)
        from apps.rewards.models import CoinLedger
        CoinLedger.objects.create(user=child, amount=17, reason="adjustment")
        snapshots = list(SkillProgress.objects.filter(user=child).values_list("pk", "xp_points", "level"))
        migration = import_module("apps.rpg.migrations.0028_sync_character_levels")
        # A later runtime curve edit must not change this historical upgrade.
        with patch("apps.achievements.models.XP_THRESHOLDS", {0: 0, 1: 1, 2: 2}):
            migration.sync_character_levels(apps, SimpleNamespace(connection=connection))
            migration.sync_character_levels(apps, SimpleNamespace(connection=connection))
        self.assertEqual(CharacterProfile.objects.get(user=child).level, 1)
        self.assertEqual(CharacterProfile.objects.get(user=empty).level, 0)
        self.assertEqual(CharacterProfile.objects.get(user=negative).level, 0)
        self.assertEqual(SkillProgress.objects.get(user=negative).xp_points, -1)
        self.assertEqual(CharacterProfile.objects.get(user=child).perfect_days_count, 2)
        self.assertEqual(list(SkillProgress.objects.filter(user=child).values_list("pk", "xp_points", "level")), snapshots)
        self.assertEqual(list(CoinLedger.objects.filter(user=child).values_list("amount", flat=True)), [17])
