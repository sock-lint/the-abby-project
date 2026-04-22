"""Tests for the 2026-04-23 trophy-shelf feature.

Pins the TrophyBadgeView contract — set, clear, and earn-gated refusal.
"""
from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Badge, UserBadge
from apps.projects.models import User
from apps.rpg.models import CharacterProfile


CACHE_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=CACHE_OVERRIDE, CELERY_TASK_ALWAYS_EAGER=True)
class TrophyBadgeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.badge = Badge.objects.create(
            name="Master Craftsman",
            description="L5 in any skill",
            icon="👑",
            criteria_type=Badge.CriteriaType.SKILL_LEVEL_REACHED,
            criteria_value={"level": 5, "count": 1},
            rarity=Badge.Rarity.LEGENDARY,
        )

    def test_setting_trophy_requires_earned_badge(self):
        # User hasn't earned the badge yet → 400.
        response = self.client.post(
            "/api/character/trophy/",
            {"badge_id": self.badge.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.active_trophy_badge)

    def test_setting_trophy_succeeds_when_earned(self):
        UserBadge.objects.create(user=self.user, badge=self.badge)
        response = self.client.post(
            "/api/character/trophy/",
            {"badge_id": self.badge.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.active_trophy_badge_id, self.badge.pk)
        self.assertEqual(response.data["badge_name"], "Master Craftsman")

    def test_clearing_trophy_with_null(self):
        UserBadge.objects.create(user=self.user, badge=self.badge)
        self.profile.active_trophy_badge = self.badge
        self.profile.save(update_fields=["active_trophy_badge"])

        response = self.client.post(
            "/api/character/trophy/",
            {"badge_id": None},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.active_trophy_badge)
