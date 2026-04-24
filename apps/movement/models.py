"""Self-reported physical-activity sessions.

A `MovementSession` is a child-logged record of a workout, practice, run,
class, or other physical activity. Distinct from:

  - Habits — tap-count + decay, capped at one per day, no duration.
  - Chores — binary did/didn't with parent approval and money/coin payout.
  - Homework — submit-then-approve with proof and timeliness scoring.
  - Project clock-in — duration tracking but expects a completion lifecycle.

Sessions are self-reported (no approval flow) and pay XP scaled by
``duration_minutes × intensity`` against parent-authored
``MovementTypeSkillTag`` rows. The first ``DAILY_REWARD_LIMIT`` sessions
per local day fire XP + drop roll + game loop; subsequent sessions still
write the row (the Movement tab is the audit trail) but skip the reward
path entirely. The counter survives ``MovementSession.delete()`` so a
log → delete → log cycle on the same day cannot re-arm rewards.
"""
from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel


class MovementType(models.Model):
    """Catalog of sessionable activity kinds.

    Parent-extensible later; seeded with ~10 rows covering the Sports +
    Body Work subjects of the Physical skill category. Each row owns a
    default skill-tag fan-out via ``MovementTypeSkillTag`` so brand-new
    sessions distribute XP without per-session parent setup.
    """

    class Intensity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=64, unique=True)
    icon = models.CharField(max_length=10, blank=True, help_text="Emoji shown on the picker.")
    default_intensity = models.CharField(
        max_length=8,
        choices=Intensity.choices,
        default=Intensity.MEDIUM,
        help_text="Pre-selected intensity in the log modal.",
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_movement_types",
        help_text="Null for seed data; set for user-authored types.",
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.icon} {self.name}".strip()


class MovementTypeSkillTag(models.Model):
    """Default skill fan-out for a MovementType.

    Mirrors ``ChoreSkillTag`` / ``HabitSkillTag``. The XP pool computed by
    ``MovementSessionService`` is split proportionally by ``xp_weight``
    across the linked Skills via ``SkillService.distribute_tagged_xp``.
    """

    movement_type = models.ForeignKey(
        MovementType, on_delete=models.CASCADE, related_name="skill_tags",
    )
    skill = models.ForeignKey(
        "achievements.Skill", on_delete=models.CASCADE,
    )
    xp_weight = models.IntegerField(
        default=1,
        help_text="Relative share of the session's XP pool this skill receives.",
    )

    class Meta:
        unique_together = [("movement_type", "skill")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.movement_type.name} — {self.skill.name} ({self.xp_weight}x)"


class MovementSession(CreatedAtModel):
    """A single child-logged activity session."""

    class Intensity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="movement_sessions",
    )
    movement_type = models.ForeignKey(
        MovementType,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    duration_minutes = models.PositiveIntegerField(
        help_text="Capped to MovementSessionService.MAX_DURATION_MINUTES at log time.",
    )
    intensity = models.CharField(
        max_length=8,
        choices=Intensity.choices,
        default=Intensity.MEDIUM,
    )
    occurred_on = models.DateField(
        help_text="Local-day bucket used by the anti-farm gate.",
    )
    notes = models.CharField(max_length=200, blank=True)
    xp_awarded = models.PositiveIntegerField(
        default=0,
        help_text="XP pool actually distributed (0 if over the daily reward cap).",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "occurred_on"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id}·{self.movement_type.name}·{self.duration_minutes}min"


class MovementDailyCounter(models.Model):
    """Per-user per-day session counter for the anti-farm gate.

    Bumped on every ``log_session`` call. Survives
    ``MovementSession.delete()`` — that's the whole point. Without this,
    a child + cooperating parent could log → delete → log to re-arm the
    daily XP window.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="movement_daily_counters",
    )
    occurred_on = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("user", "occurred_on")]
        indexes = [models.Index(fields=["user", "occurred_on"])]
