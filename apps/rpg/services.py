import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.rpg.models import CharacterProfile

logger = logging.getLogger(__name__)

BASE_CHECK_IN_COINS = 3
STREAK_MULTIPLIER_PER_DAY = 0.07
STREAK_MULTIPLIER_CAP = 2.0


class StreakService:
    """Manages daily login streaks and check-in bonuses."""

    @staticmethod
    @transaction.atomic
    def record_activity(user, activity_date=None):
        """Record daily activity, update streak, and return check-in info."""
        if activity_date is None:
            activity_date = timezone.localdate()

        profile, _created = CharacterProfile.objects.select_for_update().get_or_create(
            user=user
        )

        # Already active today — no bonus
        if profile.last_active_date == activity_date:
            return {
                "is_first_today": False,
                "check_in_bonus_coins": 0,
                "streak": profile.login_streak,
            }

        # Streak logic
        if (
            profile.last_active_date is not None
            and (activity_date - profile.last_active_date) == timedelta(days=1)
        ):
            profile.login_streak += 1
        else:
            profile.login_streak = 1

        profile.last_active_date = activity_date

        # Track all-time record
        if profile.login_streak > profile.longest_login_streak:
            profile.longest_login_streak = profile.login_streak

        profile.save(
            update_fields=[
                "login_streak",
                "longest_login_streak",
                "last_active_date",
            ]
        )

        # Calculate bonus coins
        multiplier = min(
            1 + profile.login_streak * STREAK_MULTIPLIER_PER_DAY,
            STREAK_MULTIPLIER_CAP,
        )
        bonus_coins = int(BASE_CHECK_IN_COINS * multiplier)

        return {
            "is_first_today": True,
            "check_in_bonus_coins": bonus_coins,
            "streak": profile.login_streak,
        }
