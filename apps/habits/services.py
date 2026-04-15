from django.db import transaction
from django.utils import timezone

from apps.habits.models import Habit, HabitLog
from apps.rpg.models import CharacterProfile


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
