"""Tests for the three @criterion checkers added with movement sessions."""
from __future__ import annotations

from django.test import TestCase

from apps.achievements.criteria import check
from apps.achievements.models import Badge, Skill, SkillCategory
from apps.movement.models import MovementSession, MovementType
from apps.projects.models import User


class _BadgeFixture(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        cat = SkillCategory.objects.create(name="Physical", icon="💪")
        self.skill = Skill.objects.create(category=cat, name="Endurance", icon="🏃")
        self.run = MovementType.objects.create(slug="run", name="Run")
        self.cycle = MovementType.objects.create(slug="cycle", name="Cycle")
        self.swim = MovementType.objects.create(slug="swim", name="Swim")

    def _make_badge(self, criteria_type, value):
        return Badge.objects.create(
            name=f"Test {criteria_type} {value}",
            description="…",
            criteria_type=criteria_type,
            criteria_value=value,
        )

    def _log(self, mt, minutes=30):
        MovementSession.objects.create(
            user=self.child,
            movement_type=mt,
            duration_minutes=minutes,
            intensity="medium",
            occurred_on="2026-04-23",
        )


class CountBadgeTests(_BadgeFixture):
    def test_first_session_badge_unlocks_at_count_1(self):
        b = self._make_badge(
            Badge.CriteriaType.MOVEMENT_SESSIONS_LOGGED, {"count": 1},
        )
        self.assertFalse(check(self.child, b))
        self._log(self.run)
        self.assertTrue(check(self.child, b))

    def test_count_uses_lifetime_total(self):
        b = self._make_badge(
            Badge.CriteriaType.MOVEMENT_SESSIONS_LOGGED, {"count": 3},
        )
        for _ in range(2):
            self._log(self.run)
        self.assertFalse(check(self.child, b))
        self._log(self.run)
        self.assertTrue(check(self.child, b))


class TotalMinutesBadgeTests(_BadgeFixture):
    def test_minutes_aggregate_across_sessions(self):
        b = self._make_badge(
            Badge.CriteriaType.MOVEMENT_TOTAL_MINUTES, {"minutes": 60},
        )
        self._log(self.run, minutes=30)
        self.assertFalse(check(self.child, b))
        self._log(self.cycle, minutes=30)
        self.assertTrue(check(self.child, b))


class TypeBreadthBadgeTests(_BadgeFixture):
    def test_breadth_counts_distinct_types(self):
        b = self._make_badge(
            Badge.CriteriaType.MOVEMENT_TYPE_BREADTH, {"count": 3},
        )
        # Three sessions of the same type — still breadth = 1.
        for _ in range(3):
            self._log(self.run)
        self.assertFalse(check(self.child, b))
        self._log(self.cycle)
        self.assertFalse(check(self.child, b))
        self._log(self.swim)
        self.assertTrue(check(self.child, b))
