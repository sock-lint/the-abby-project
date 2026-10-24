from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.habits.models import Habit, HabitLog
from apps.rpg.models import CharacterProfile


class HabitService:
    """Manages habit taps and daily strength decay."""

    @staticmethod
    @transaction.atomic
    def log_tap(user, habit, direction, *, usage_actor=None):
        """Log a +1 or -1 tap on a habit, update strength, return rewards."""
        if direction not in (1, -1):
            raise ValueError(f"direction must be +1 or -1, got {direction}")

        # Serialize strength updates against the daily decay worker and taps
        # arriving with an older in-memory Habit instance.
        from apps.accounts.models import User
        User.objects.select_for_update(no_key=True).get(pk=user.pk)
        Habit.objects.select_for_update().get(pk=habit.pk)
        habit.refresh_from_db()

        if not habit.is_active:
            raise ValueError("This habit is paused. Ask a parent to resume it before tapping.")

        if habit.pending_parent_review:
            raise ValueError(
                "This habit is waiting for parent approval before it can be tapped.",
            )

        # Type compatibility checks
        if habit.habit_type == "positive" and direction == -1:
            raise ValueError("Positive habits do not accept negative taps.")
        if habit.habit_type == "negative" and direction == +1:
            raise ValueError("Negative habits do not accept positive taps.")

        # Daily cap: positive taps only. Vices stay uncapped so kids can
        # honestly log every slip.
        if direction == 1:
            today = timezone.localdate()
            taps_today = HabitLog.objects.filter(
                habit=habit,
                user=user,
                direction=1,
                created_at__date=today,
            ).count()
            if taps_today >= habit.max_taps_per_day:
                raise ValueError(
                    f"Daily limit reached ({habit.max_taps_per_day} taps/day)."
                )

        # Get current streak
        profile, _created = CharacterProfile.objects.get_or_create(user=user)
        streak = profile.login_streak

        # Create log entry
        log = HabitLog.objects.create(
            habit=habit,
            user=user,
            direction=direction,
            streak_at_time=streak,
        )

        # Update strength
        habit.strength += direction
        habit.save(update_fields=["strength"])

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="habit",
            event_type="habit.tap",
            summary=(f"{'+1' if direction == 1 else '-1'} {habit.name}"),
            actor=user,
            subject=user,
            target=log,
            breakdown=[
                {"label": "direction", "value": direction, "op": "note"},
                {"label": "new strength", "value": habit.strength, "op": "="},
                {"label": "streak at time", "value": streak, "op": "note"},
            ],
            extras={
                "habit_id": habit.pk,
                "habit_name": habit.name,
                "habit_type": habit.habit_type,
                "direction": direction,
                "new_strength": habit.strength,
                "streak": streak,
            },
        )

        # Positive taps recognize habit milestones independently of XP.
        # A nonzero pool splits across tags; no tags means no skill credit.
        if direction == 1 and habit.xp_reward > 0:
            from apps.achievements.services import AwardService
            AwardService.grant(
                user,
                xp_tags=habit.skill_tags.select_related("skill"),
                xp=habit.xp_reward,
                xp_source_label=f"Habit: {habit.name}",
                created_by=user,
                # Audit H8: habit tap moves habit ladders, skill XP, and meta.
                badge_scopes={"habit", "skill_xp", "badges"},
            )
        elif direction == 1:
            from apps.achievements.services import BadgeService
            BadgeService.evaluate_badges(
                user, created_by=user, scopes={"habit", "badges"},
            )

        if direction == 1:
            from apps.rpg.services import GameLoopService
            GameLoopService.record_challenge_activity(user, "habit_log", {"habit_log_id": log.pk})
        if usage_actor is not None:
            from apps.usage.services import record_action
            record_action(
                usage_actor, "habits", "completed" if direction == 1 else "checked_in",
                source="habits.habitlog", source_id=log.pk,
            )
        return {
            "direction": direction,
            "xp_reward": habit.xp_reward if direction == 1 else 0,
            "new_strength": habit.strength,
        }

    @staticmethod
    @transaction.atomic
    def decay_all_habits(user, target_date=None):
        """Decay strength of untapped habits toward 0. Returns count decayed.

        Decay magnitude scales with ``max_taps_per_day`` so a 4x-per-day habit
        drifts roughly twice as fast as a daily one — otherwise high-frequency
        habits feel rock-solid just because each individual slip lands the same
        unit of decay.
        """
        with timezone.override(ZoneInfo(user.family.timezone)):
            if target_date is None:
                target_date = timezone.localdate() - timedelta(days=1)

            habits = Habit.objects.select_for_update().filter(user=user, is_active=True)
            decayed = 0
            for habit in habits:
                if habit.last_decay_date and habit.last_decay_date >= target_date:
                    continue
                tapped = HabitLog.objects.filter(
                    habit=habit, user=user, created_at__date=target_date,
                ).exists()

                if not tapped and habit.strength != 0:
                    step = max(1, habit.max_taps_per_day // 2)
                    if habit.strength > 0:
                        habit.strength = max(0, habit.strength - step)
                    else:
                        habit.strength = min(0, habit.strength + step)
                    decayed += 1

                # Even a tapped or zero-strength day is finished. A retried
                # delivery must not decay new strength earned afterward.
                habit.last_decay_date = target_date
                habit.save(update_fields=["strength", "last_decay_date"])
            return decayed
