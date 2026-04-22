"""Shared RPG constants — importable without triggering model loading."""

from django.db import models


class TriggerType(models.TextChoices):
    """Canonical vocabulary for RPG game-loop triggers.

    Any event that fires ``GameLoopService.on_task_completed(user, trigger, ...)``
    must use one of these values. ``BASE_DROP_RATES`` (apps/rpg/services.py) and
    ``TRIGGER_DAMAGE`` (apps/quests/services.py) are keyed by these strings, and
    the content-pack loader validates ``drops.yaml`` against them.
    """

    CLOCK_OUT = "clock_out", "Clock Out"
    CHORE_COMPLETE = "chore_complete", "Chore Complete"
    HOMEWORK_COMPLETE = "homework_complete", "Homework Complete"
    HOMEWORK_CREATED = "homework_created", "Homework Created"
    MILESTONE_COMPLETE = "milestone_complete", "Milestone Complete"
    PROJECT_COMPLETE = "project_complete", "Project Complete"
    BADGE_EARNED = "badge_earned", "Badge Earned"
    QUEST_COMPLETE = "quest_complete", "Quest Complete"
    PERFECT_DAY = "perfect_day", "Perfect Day"
    HABIT_LOG = "habit_log", "Habit Log"
    DAILY_CHECK_IN = "daily_check_in", "Daily Check-In"
