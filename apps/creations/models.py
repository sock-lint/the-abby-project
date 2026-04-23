from django.conf import settings
from django.db import models

from config.base_models import TimestampedModel


class Creation(TimestampedModel):
    """A child-authored "I made a thing" entry.

    Past-tense, artifact-first: the child logs a photo (+ optional audio + caption)
    of something they already made. Baseline self-credit XP fires immediately on
    the first 2 per local day; parent bonus approval is an optional top-up.
    """

    class Status(models.TextChoices):
        LOGGED = "logged", "Logged"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="creations",
    )
    image = models.ImageField(upload_to="creations/")
    audio = models.FileField(upload_to="creations/audio/", blank=True, null=True)
    caption = models.CharField(max_length=200, blank=True)
    occurred_on = models.DateField(
        help_text="Local-day bucket used by the anti-farm gate and chapter_year."
    )
    primary_skill = models.ForeignKey(
        "achievements.Skill",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Required. Must be in a creative category (see apps.creations.constants).",
    )
    secondary_skill = models.ForeignKey(
        "achievements.Skill",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.LOGGED,
    )
    xp_awarded = models.PositiveIntegerField(
        default=0,
        help_text="Baseline self-credit XP pool distributed on log (0 if over daily cap).",
    )
    bonus_xp_awarded = models.PositiveIntegerField(
        default=0,
        help_text="Additional XP pool granted by parent on approve.",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    chronicle_entry = models.ForeignKey(
        "chronicle.ChronicleEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "occurred_on"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id}·creation·{self.caption[:40] or self.primary_skill_id}"


class CreationDailyCounter(models.Model):
    """Persistent per-user per-day counter used by the anti-farm gate.

    Incremented on every ``log_creation`` call. Survives ``Creation.delete()``
    — that's the whole point. Without this, a child + cooperating parent
    could create → delete → create to re-arm the 2-per-day XP window.
    See ``CreationAntifarmTests.test_create_two_then_delete_one_then_create_still_skips_xp``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="creation_daily_counters",
    )
    occurred_on = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("user", "occurred_on")]
        indexes = [models.Index(fields=["user", "occurred_on"])]


class CreationBonusSkillTag(models.Model):
    """Parent-authored skill fan-out for the *bonus* XP pool only.

    Mirrors the shape of ``ProjectSkillTag`` / ``ChoreSkillTag``: a (skill,
    weight) row per tag. Weights combine via ``SkillService.distribute_tagged_xp``.
    The child-selected primary/secondary skills drive the baseline pool and do
    NOT appear here — the two pools are independent.
    """

    creation = models.ForeignKey(
        Creation,
        on_delete=models.CASCADE,
        related_name="bonus_skill_tags",
    )
    skill = models.ForeignKey(
        "achievements.Skill",
        on_delete=models.PROTECT,
    )
    xp_weight = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [("creation", "skill")]

    def __str__(self) -> str:  # pragma: no cover
        return f"CreationBonusSkillTag(creation={self.creation_id}, skill={self.skill_id})"
