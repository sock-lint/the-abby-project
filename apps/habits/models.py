from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel, TimestampedModel


class Habit(TimestampedModel):
    """A trackable habit (positive, negative, or both) assigned to a user."""

    class HabitType(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEGATIVE = "negative", "Negative"
        BOTH = "both", "Both"

    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=10, blank=True)
    habit_type = models.CharField(
        max_length=8,
        choices=HabitType.choices,
        default=HabitType.POSITIVE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="habits",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_habits",
    )
    xp_reward = models.PositiveIntegerField(default=5)
    max_taps_per_day = models.PositiveSmallIntegerField(default=1)
    strength = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    pending_parent_review = models.BooleanField(default=False, db_index=True)

    class Meta:
        # Preserve original table name so the move is a state-only migration.
        db_table = "rpg_habit"
        ordering = ["name"]

    def __str__(self):
        return f"{self.icon} {self.name}".strip()


class HabitLog(CreatedAtModel):
    """A single +1 or -1 log entry for a habit."""

    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name="logs")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="habit_logs",
    )
    direction = models.SmallIntegerField()
    streak_at_time = models.IntegerField(default=0)

    class Meta:
        # Preserve original table name so the move is a state-only migration.
        db_table = "rpg_habitlog"
        ordering = ["-created_at"]


class HabitSkillTag(models.Model):
    """Declares which skills a habit rewards on each positive tap.

    Mirrors ``ProjectSkillTag`` — XP pool from ``Habit.xp_reward`` is
    distributed proportionally by ``xp_weight`` across the linked skills
    every time ``HabitService.log_tap`` records a positive direction.
    Negative taps never award skill XP (matches the existing no-coins
    rule for rituals).
    """

    habit = models.ForeignKey(
        Habit, on_delete=models.CASCADE, related_name="skill_tags",
    )
    skill = models.ForeignKey(
        "achievements.Skill", on_delete=models.CASCADE,
    )
    xp_weight = models.IntegerField(
        default=1,
        help_text="Relative share of Habit.xp_reward this skill receives.",
    )

    class Meta:
        unique_together = [("habit", "skill")]

    def __str__(self):
        return f"{self.habit.name} — {self.skill.name} ({self.xp_weight}x)"
