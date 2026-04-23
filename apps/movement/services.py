"""MovementSessionService — self-reported physical-activity logging.

Pipeline per ``log_session`` call:

1. Bump the per-user per-day counter (read-modify-write under
   ``select_for_update``). Returns the PRE-increment count so callers can
   gate on the old value (first log returns 0, second returns 1, etc.).
2. Write the ``MovementSession`` row.
3. If the prior count was below ``DAILY_REWARD_LIMIT``: distribute the
   XP pool via the MovementType's parent-authored skill tags, then call
   ``GameLoopService.on_task_completed`` so streak / drops / quest
   progress all count.

The counter survives ``MovementSession.delete()`` so a log → delete → log
cycle on the same day cannot re-arm the reward window — matches the
soft-farm doctrine used by ``CreationService``.
"""
from __future__ import annotations

import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.movement.models import (
    MovementDailyCounter,
    MovementSession,
    MovementType,
)

logger = logging.getLogger(__name__)


class MovementSessionError(Exception):
    """Raised when a session cannot be logged (bad type, bad inputs, etc.)."""


class MovementSessionService:
    DAILY_REWARD_LIMIT = 3
    INTENSITY_MULTIPLIER = {
        MovementSession.Intensity.LOW: 0.5,
        MovementSession.Intensity.MEDIUM: 1.0,
        MovementSession.Intensity.HIGH: 1.5,
    }
    XP_PER_10_MIN = 5
    # Hard cap to bound any single-session XP regardless of input. 4h covers
    # every realistic continuous activity (a marathon, a tournament game).
    MAX_DURATION_MINUTES = 240
    MIN_DURATION_MINUTES = 1

    @classmethod
    def compute_xp_pool(cls, duration_minutes: int, intensity: str) -> int:
        """Return the XP pool for a given duration + intensity.

        Pool = ``floor(duration_minutes / 10) × XP_PER_10_MIN × intensity_mult``.
        Anything under 10 minutes earns zero XP — the floor is deliberate so
        a 5-minute warm-up isn't equivalent to a real session.
        """
        clamped = max(0, min(int(duration_minutes), cls.MAX_DURATION_MINUTES))
        ten_minute_blocks = clamped // 10
        mult = cls.INTENSITY_MULTIPLIER.get(intensity, 1.0)
        return int(ten_minute_blocks * cls.XP_PER_10_MIN * mult)

    @classmethod
    def _bump_counter(cls, user, day: date) -> int:
        """Read-modify-write the per-user per-day counter under a row lock.

        Returns the PRE-increment count. The lock is required so two
        concurrent logs from the same user can't both read 0 and both
        award XP past the cap.
        """
        counter, _ = MovementDailyCounter.objects.select_for_update().get_or_create(
            user=user, occurred_on=day, defaults={"count": 0},
        )
        prior = counter.count
        counter.count = prior + 1
        counter.save(update_fields=["count"])
        return prior

    @classmethod
    @transaction.atomic
    def log_session(
        cls,
        user,
        *,
        movement_type: MovementType,
        duration_minutes: int,
        intensity: str = MovementSession.Intensity.MEDIUM,
        occurred_at=None,
        notes: str = "",
    ) -> MovementSession:
        """Log a session, conditionally distribute XP + drop + quest progress.

        Raises ``MovementSessionError`` for invalid inputs. Always writes
        the session row — only the reward path is gated by the daily cap.
        """
        if not movement_type.is_active:
            raise MovementSessionError(
                f"Movement type '{movement_type.name}' is no longer active.",
            )
        if duration_minutes < cls.MIN_DURATION_MINUTES:
            raise MovementSessionError(
                f"Duration must be at least {cls.MIN_DURATION_MINUTES} minute.",
            )
        if intensity not in cls.INTENSITY_MULTIPLIER:
            raise MovementSessionError(
                f"Unknown intensity '{intensity}'. Use low / medium / high.",
            )

        clamped_minutes = min(int(duration_minutes), cls.MAX_DURATION_MINUTES)
        day = (occurred_at or timezone.now()).date() if occurred_at else timezone.localdate()

        prior_count = cls._bump_counter(user, day)
        is_xp_eligible = prior_count < cls.DAILY_REWARD_LIMIT

        session = MovementSession.objects.create(
            user=user,
            movement_type=movement_type,
            duration_minutes=clamped_minutes,
            intensity=intensity,
            occurred_on=day,
            notes=(notes or "")[:200],
        )

        if is_xp_eligible:
            cls._award_session(user, session)

        return session

    @classmethod
    def _award_session(cls, user, session: MovementSession) -> None:
        """Distribute XP + fire game loop for a within-cap session."""
        from apps.achievements.services import AwardService
        from apps.rpg.constants import TriggerType
        from apps.rpg.services import GameLoopService

        xp_pool = cls.compute_xp_pool(session.duration_minutes, session.intensity)
        if xp_pool > 0:
            tags = session.movement_type.skill_tags.select_related("skill")
            try:
                AwardService.grant(
                    user,
                    xp_tags=tags,
                    xp=xp_pool,
                    xp_source_label=f"Movement: {session.movement_type.name}",
                )
            except Exception:
                logger.exception(
                    "Movement XP award failed for user %s, session %s",
                    user.pk, session.pk,
                )
            session.xp_awarded = xp_pool
            session.save(update_fields=["xp_awarded"])

        try:
            GameLoopService.on_task_completed(
                user,
                TriggerType.MOVEMENT_SESSION,
                {
                    "session_id": session.id,
                    "movement_type_id": session.movement_type_id,
                    "duration_minutes": session.duration_minutes,
                    "intensity": session.intensity,
                },
            )
        except Exception:
            logger.exception(
                "Movement game loop failed for user %s, session %s",
                user.pk, session.pk,
            )
