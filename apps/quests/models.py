from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.quests.validators import validate_trigger_filter
from config.base_models import TimestampedModel


class QuestDefinition(TimestampedModel):
    """Template for a quest -- can be system-curated or parent-created."""

    class QuestType(models.TextChoices):
        BOSS = "boss", "Boss Fight"
        COLLECTION = "collection", "Collection Quest"

    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, default="\u2694\ufe0f")
    sprite_key = models.CharField(
        max_length=64, blank=True,
        help_text="Optional bundled pixel-art sprite slug; falls back to icon when empty.",
    )
    quest_type = models.CharField(max_length=20, choices=QuestType.choices)
    target_value = models.PositiveIntegerField()  # HP for boss, count for collection
    duration_days = models.PositiveIntegerField(default=7)
    trigger_filter = models.JSONField(default=dict, blank=True)
    required_badge = models.ForeignKey(
        "achievements.Badge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gated_quests",
    )
    coin_reward = models.PositiveIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(default=0)
    is_repeatable = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_quests",
    )

    class Meta:
        ordering = ["-is_system", "name"]

    def clean(self):
        super().clean()
        validate_trigger_filter(self.trigger_filter)

    def __str__(self):
        return f"{self.icon} {self.name} ({self.get_quest_type_display()})"


class QuestRewardItem(TimestampedModel):
    """Item reward for completing a quest."""

    quest_definition = models.ForeignKey(
        QuestDefinition,
        on_delete=models.CASCADE,
        related_name="reward_items",
    )
    item = models.ForeignKey(
        "rpg.ItemDefinition",
        on_delete=models.CASCADE,
        related_name="quest_rewards",
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["quest_definition", "item"]

    def __str__(self):
        return f"{self.quest_definition.name} \u2192 {self.item.name} x{self.quantity}"


class QuestSkillTag(models.Model):
    """Declares which skills a quest rewards when completed.

    Mirrors ``ProjectSkillTag`` — XP pool from ``QuestDefinition.xp_reward``
    is distributed proportionally by ``xp_weight`` across the linked
    skills in ``QuestService._complete_quest``, replacing the previous
    "dilute XP evenly across every active skill" behaviour that
    ``AwardService.grant(xp=...)`` fell back to for untagged callers.
    """

    quest_definition = models.ForeignKey(
        QuestDefinition,
        on_delete=models.CASCADE,
        related_name="skill_tags",
    )
    skill = models.ForeignKey(
        "achievements.Skill", on_delete=models.CASCADE,
    )
    xp_weight = models.IntegerField(
        default=1,
        help_text="Relative share of QuestDefinition.xp_reward this skill receives.",
    )

    class Meta:
        unique_together = [("quest_definition", "skill")]

    def __str__(self):
        return f"{self.quest_definition.name} — {self.skill.name} ({self.xp_weight}x)"


class Quest(TimestampedModel):
    """An active quest instance for a user."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    definition = models.ForeignKey(
        QuestDefinition,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    current_progress = models.PositiveIntegerField(default=0)
    rage_shield = models.PositiveIntegerField(default=0)  # boss rage mechanic

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.definition.name} ({self.get_status_display()})"

    @property
    def is_expired(self):
        return timezone.now() > self.end_date and self.status == self.Status.ACTIVE

    @property
    def effective_target(self):
        """Target value including any rage shield."""
        return self.definition.target_value + self.rage_shield

    @property
    def progress_percent(self):
        if self.effective_target == 0:
            return 100
        return min(int(self.current_progress / self.effective_target * 100), 100)


class QuestParticipant(TimestampedModel):
    """Tracks per-user contribution to a quest."""

    quest = models.ForeignKey(
        Quest, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quest_participations",
    )
    contribution = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("quest", "user")
        ordering = ["-contribution"]

    def __str__(self):
        return f"{self.user} \u2192 {self.quest.definition.name} ({self.contribution})"
