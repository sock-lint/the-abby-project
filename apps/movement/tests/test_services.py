"""Tests for MovementSessionService.

Pinned invariants:

1. XP pool scales with duration × intensity (10-min blocks × 5 XP × mult).
2. The first 3 sessions per user per local day fire XP + game loop.
3. The 4th+ session writes the row but skips both XP and the game-loop call.
4. Soft-farm prevention: deleting a session does NOT decrement the daily
   counter — log → delete → log on the same day still hits the cap.
5. XP is split across MovementType.skill_tags by xp_weight.
6. duration_minutes is clamped to MAX_DURATION_MINUTES (4h).
7. Sub-10-minute sessions earn zero XP (block floor) but still write.
8. inactive types are rejected.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.movement.models import (
    MovementDailyCounter,
    MovementSession,
    MovementType,
    MovementTypeSkillTag,
)
from apps.movement.services import MovementSessionError, MovementSessionService
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.cat = SkillCategory.objects.create(name="Physical", icon="💪")
        self.subj = Subject.objects.create(category=self.cat, name="Sports", icon="⚽")
        self.endurance = Skill.objects.create(
            category=self.cat, subject=self.subj, name="Endurance", icon="🏃",
        )
        self.running = Skill.objects.create(
            category=self.cat, subject=self.subj, name="Running", icon="🏃",
        )
        self.run_type = MovementType.objects.create(
            slug="run", name="Run", icon="🏃",
            default_intensity=MovementType.Intensity.MEDIUM,
        )
        # Default 60/40 split — Running 3, Endurance 2.
        MovementTypeSkillTag.objects.create(
            movement_type=self.run_type, skill=self.running, xp_weight=3,
        )
        MovementTypeSkillTag.objects.create(
            movement_type=self.run_type, skill=self.endurance, xp_weight=2,
        )


class XPPoolTests(_Fixture):
    """Direct unit tests on the pure XP-pool formula."""

    def test_zero_minutes_returns_zero(self):
        self.assertEqual(
            MovementSessionService.compute_xp_pool(0, MovementSession.Intensity.MEDIUM),
            0,
        )

    def test_under_ten_minutes_returns_zero(self):
        # 9 min // 10 = 0 blocks → 0 XP regardless of intensity.
        self.assertEqual(
            MovementSessionService.compute_xp_pool(9, MovementSession.Intensity.HIGH),
            0,
        )

    def test_thirty_minutes_medium_intensity(self):
        # 30 // 10 = 3 blocks × 5 XP × 1.0 = 15.
        self.assertEqual(
            MovementSessionService.compute_xp_pool(30, MovementSession.Intensity.MEDIUM),
            15,
        )

    def test_high_intensity_multiplies_pool(self):
        # 40 // 10 = 4 blocks × 5 XP × 1.5 = 30.
        self.assertEqual(
            MovementSessionService.compute_xp_pool(40, MovementSession.Intensity.HIGH),
            30,
        )

    def test_low_intensity_halves_pool(self):
        # 60 // 10 = 6 blocks × 5 XP × 0.5 = 15.
        self.assertEqual(
            MovementSessionService.compute_xp_pool(60, MovementSession.Intensity.LOW),
            15,
        )

    def test_duration_capped_at_max(self):
        # 9999 min clamps to 240 → 24 blocks × 5 × 1.0 = 120.
        self.assertEqual(
            MovementSessionService.compute_xp_pool(9999, MovementSession.Intensity.MEDIUM),
            120,
        )


class LogSessionXPTests(_Fixture):
    def test_first_session_distributes_pool_by_skill_weight(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            with patch(
                "apps.achievements.services.SkillService.award_xp",
            ) as award:
                MovementSessionService.log_session(
                    self.child,
                    movement_type=self.run_type,
                    duration_minutes=30,
                    intensity=MovementSession.Intensity.MEDIUM,
                )
        # 30 min × medium = 15 XP pool. Weights 3 + 2 over 5 → 9 + 6.
        awarded = {call.args[1].id: call.args[2] for call in award.call_args_list}
        self.assertEqual(awarded[self.running.id], 9)
        self.assertEqual(awarded[self.endurance.id], 6)

    def test_session_xp_awarded_field_set(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            session = MovementSessionService.log_session(
                self.child,
                movement_type=self.run_type,
                duration_minutes=30,
                intensity=MovementSession.Intensity.MEDIUM,
            )
        self.assertEqual(session.xp_awarded, 15)

    def test_clamps_duration_minutes_to_max(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            session = MovementSessionService.log_session(
                self.child,
                movement_type=self.run_type,
                duration_minutes=600,  # 10h — way over MAX
                intensity=MovementSession.Intensity.MEDIUM,
            )
        self.assertEqual(session.duration_minutes, 240)
        self.assertEqual(session.xp_awarded, 120)  # 24 × 5 × 1.0

    def test_under_ten_min_session_writes_but_xp_zero(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            session = MovementSessionService.log_session(
                self.child,
                movement_type=self.run_type,
                duration_minutes=5,
                intensity=MovementSession.Intensity.HIGH,
            )
        self.assertEqual(session.xp_awarded, 0)
        # Game loop still fires — short stints still feed streaks/quests.
        gl.assert_called_once()


class AntifarmTests(_Fixture):
    def test_first_three_sessions_fire_loop_fourth_skips(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            for _ in range(3):
                MovementSessionService.log_session(
                    self.child, movement_type=self.run_type,
                    duration_minutes=30,
                )
            fourth = MovementSessionService.log_session(
                self.child, movement_type=self.run_type,
                duration_minutes=30,
            )
        self.assertEqual(gl.call_count, 3)
        self.assertEqual(fourth.xp_awarded, 0)
        # All 4 rows written (audit trail).
        self.assertEqual(MovementSession.objects.filter(user=self.child).count(), 4)

    def test_delete_does_not_reset_counter(self):
        """Soft-farm prevention: log → delete → log on same day still skips."""
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            s1 = MovementSessionService.log_session(
                self.child, movement_type=self.run_type, duration_minutes=30,
            )
            MovementSessionService.log_session(
                self.child, movement_type=self.run_type, duration_minutes=30,
            )
            MovementSessionService.log_session(
                self.child, movement_type=self.run_type, duration_minutes=30,
            )
            # Delete the first — counter should NOT decrement.
            s1.delete()
            fourth = MovementSessionService.log_session(
                self.child, movement_type=self.run_type, duration_minutes=30,
            )
        self.assertEqual(gl.call_count, 3)
        self.assertEqual(fourth.xp_awarded, 0)
        # Counter sits at 4 even though only 3 rows survive.
        counter = MovementDailyCounter.objects.get(
            user=self.child, occurred_on=timezone.localdate(),
        )
        self.assertEqual(counter.count, 4)

    def test_next_day_resets_reward_window(self):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            for _ in range(3):
                MovementSessionService.log_session(
                    self.child, movement_type=self.run_type, duration_minutes=30,
                )
            with patch(
                "apps.movement.services.timezone.localdate",
                return_value=tomorrow,
            ):
                s_next = MovementSessionService.log_session(
                    self.child, movement_type=self.run_type, duration_minutes=30,
                )
        self.assertEqual(gl.call_count, 4)  # 3 today + 1 tomorrow
        self.assertEqual(s_next.xp_awarded, 15)


class ValidationTests(_Fixture):
    def test_inactive_type_rejected(self):
        self.run_type.is_active = False
        self.run_type.save()
        with self.assertRaises(MovementSessionError):
            MovementSessionService.log_session(
                self.child, movement_type=self.run_type, duration_minutes=30,
            )
        self.assertEqual(MovementSession.objects.count(), 0)

    def test_zero_duration_rejected(self):
        with self.assertRaises(MovementSessionError):
            MovementSessionService.log_session(
                self.child, movement_type=self.run_type, duration_minutes=0,
            )

    def test_unknown_intensity_rejected(self):
        with self.assertRaises(MovementSessionError):
            MovementSessionService.log_session(
                self.child, movement_type=self.run_type,
                duration_minutes=30, intensity="extreme",
            )


class GameLoopHookTests(_Fixture):
    def test_game_loop_called_with_movement_session_trigger(self):
        from apps.rpg.constants import TriggerType

        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            MovementSessionService.log_session(
                self.child, movement_type=self.run_type,
                duration_minutes=45, intensity=MovementSession.Intensity.HIGH,
            )
        gl.assert_called_once()
        args, _kwargs = gl.call_args
        self.assertEqual(args[0], self.child)
        self.assertEqual(args[1], TriggerType.MOVEMENT_SESSION)
        self.assertEqual(args[2]["duration_minutes"], 45)
        self.assertEqual(args[2]["intensity"], MovementSession.Intensity.HIGH)
