import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.rpg.models import CharacterProfile, HabitLog

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


class HabitService:
    """Manages habit taps and daily strength decay."""

    @staticmethod
    @transaction.atomic
    def log_tap(user, habit, direction):
        """Log a +1 or -1 tap on a habit, update strength, return rewards."""
        if direction not in (1, -1):
            raise ValueError(f"direction must be +1 or -1, got {direction}")

        # Type compatibility checks
        if habit.habit_type == "positive" and direction == -1:
            raise ValueError("Positive habits do not accept negative taps.")
        if habit.habit_type == "negative" and direction == +1:
            raise ValueError("Negative habits do not accept positive taps.")

        # Get current streak
        profile, _created = CharacterProfile.objects.get_or_create(user=user)
        streak = profile.login_streak

        # Create log entry
        HabitLog.objects.create(
            habit=habit,
            user=user,
            direction=direction,
            streak_at_time=streak,
        )

        # Update strength
        habit.strength += direction
        habit.save(update_fields=["strength"])

        return {
            "direction": direction,
            "coin_reward": habit.coin_reward if direction == 1 else 0,
            "xp_reward": habit.xp_reward if direction == 1 else 0,
            "new_strength": habit.strength,
        }

    @staticmethod
    def decay_all_habits(user, target_date=None):
        """Decay strength of untapped habits toward 0. Returns count decayed."""
        if target_date is None:
            target_date = timezone.localdate()

        from apps.rpg.models import Habit

        habits = Habit.objects.filter(user=user, is_active=True)
        decayed = 0

        for habit in habits:
            # Check if tapped today
            tapped_today = HabitLog.objects.filter(
                habit=habit,
                user=user,
                created_at__date=target_date,
            ).exists()

            if tapped_today or habit.strength == 0:
                continue

            # Decay toward 0
            if habit.strength > 0:
                habit.strength -= 1
            else:
                habit.strength += 1

            habit.save(update_fields=["strength"])
            decayed += 1

        return decayed


STREAK_MILESTONES = {3, 7, 14, 30, 60, 100}


class GameLoopService:
    """Central orchestrator called after any task completion."""

    @staticmethod
    @transaction.atomic
    def on_task_completed(user, trigger_type, context=None):
        if context is None:
            context = {}

        notifications = []

        # Step 1: record daily activity
        streak_result = StreakService.record_activity(user)

        # Step 2: award check-in bonus coins if first activity today
        bonus = streak_result["check_in_bonus_coins"]
        if streak_result["is_first_today"] and bonus > 0:
            from apps.rewards.models import CoinLedger
            from apps.rewards.services import CoinService

            CoinService.award_coins(
                user,
                bonus,
                CoinLedger.Reason.ADJUSTMENT,
                description="Daily check-in bonus",
            )

        # Step 3: streak milestone notification
        streak = streak_result["streak"]
        if streak in STREAK_MILESTONES:
            from apps.projects.notifications import notify

            msg = f"Keep it up! You've been active {streak} days in a row."
            notify(
                user,
                title=f"\U0001f525 {streak}-day streak!",
                message=msg,
                notification_type="streak_milestone",
                link="/",
            )
            notifications.append(f"{streak}-day streak milestone")

        return {
            "trigger_type": trigger_type,
            "streak": streak_result,
            "notifications": notifications,
        }
