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
    is_cooperative = models.BooleanField(
        default=False,
        help_text="A parent assigns this shared challenge to at least two children.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_quests",
    )
    superseded_by = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, editable=False,
        related_name="retained_aliases",
        help_text="Retained duplicate identity; only its canonical definition is offered for new acceptance.",
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
    reward_items_snapshot = models.JSONField(
        null=True, blank=True, editable=False,
        help_text="Server-owned accepted item IDs/quantities; null retains pre-cutover definition links.",
    )

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


class DailyChallenge(TimestampedModel):
    """A lightweight once-a-day micro-quest — separate slot from Quest.

    Rotated by the ``rotate_daily_challenges`` Celery task at 00:30 local.
    Progress is recorded in GameLoopService.on_task_completed alongside the
    regular quest progress flow, but DailyChallenge is intentionally
    decoupled from QuestDefinition — its template list is a small enum
    rather than a CRUD'able catalog, so the daily slot stays small and
    doesn't compete with the real quest system for attention.
    """

    # quests.0004 created an integer primary key; retain it independently of
    # the app's BigAutoField default so existing tables and IDs stay intact.
    id = models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")

    class ChallengeType(models.TextChoices):
        CLOCK_HOUR = "clock_hour", "Clock an hour today"
        CHORES = "chores", "Finish N chores today"
        HABITS = "habits", "Log N habits today"
        HOMEWORK = "homework", "Finish N homework today"
        MILESTONE = "milestone", "Clear a milestone today"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_challenges",
    )
    challenge_type = models.CharField(max_length=20, choices=ChallengeType.choices)
    target_value = models.PositiveIntegerField(default=1)
    current_progress = models.PositiveIntegerField(default=0)
    date = models.DateField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    coin_reward = models.PositiveIntegerField(default=10)
    xp_reward = models.PositiveIntegerField(default=20)

    class Meta:
        unique_together = [("user", "date")]
        ordering = ["-date"]

    def __str__(self):
        return (
            f"{self.user} · {self.get_challenge_type_display()} "
            f"({self.current_progress}/{self.target_value})"
        )

    @property
    def is_complete(self):
        return self.current_progress >= self.target_value

    @property
    def progress_percent(self):
        if self.target_value == 0:
            return 100
        return min(100, int(self.current_progress / self.target_value * 100))


class ChallengeEnrollment(models.Model):
    """First automatic tracking boundary; pins never change this date."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    starts_at = models.DateTimeField(default=timezone.now)
    timezone_name = models.CharField(max_length=64, default="America/Phoenix")
    discovery_tracking_started_at = models.DateTimeField(
        null=True, blank=True, editable=False,
        help_text="Set only on new enrollment; null preserves unknown historical detail openings.",
    )


class ChallengeGoal(TimestampedModel):
    """An immutable personal goal, from the catalog or a family assignment."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    family = models.ForeignKey("families.Family", on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="authored_challenge_goals",
    )
    catalog_definition = models.ForeignKey(
        QuestDefinition, on_delete=models.SET_NULL, null=True, blank=True,
    )
    is_catalog = models.BooleanField(default=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    metric = models.CharField(max_length=12, choices=[
        ("count", "Actions"), ("minutes", "Minutes"),
        ("distance", "Distance"), ("damage", "Boss damage"),
    ])
    target = models.DecimalField(max_digits=16, decimal_places=3)
    unit = models.CharField(max_length=12, default="actions")
    trigger_filter = models.JSONField(default=dict)
    movement_type = models.ForeignKey(
        "movement.MovementType", on_delete=models.PROTECT, null=True, blank=True,
    )
    timezone_name = models.CharField(max_length=64)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    repeat_weekly = models.BooleanField(default=False)
    repeat_days = models.PositiveIntegerField(default=0)
    coin_reward = models.PositiveIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(default=0)
    skill_tags = models.JSONField(default=list)
    reward_items = models.JSONField(default=list)
    request_id = models.UUIDField(null=True, blank=True)
    request_fingerprint = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "catalog_definition"], name="unique_personal_catalog_goal"),
            models.UniqueConstraint(fields=["created_by", "request_id"], name="unique_parent_goal_request"),
        ]


class ChallengeOccurrence(TimestampedModel):
    """One fixed window and one possible payout, including weekly repeats."""

    goal = models.ForeignKey(ChallengeGoal, on_delete=models.CASCADE, related_name="occurrences")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    snapshot = models.JSONField(default=dict)
    progress = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    status = models.CharField(max_length=12, default="active", choices=[
        ("active", "Active"), ("completed", "Completed"), ("expired", "Expired"),
    ])
    completed_at = models.DateTimeField(null=True, blank=True)
    first_details_opened_at = models.DateTimeField(null=True, blank=True, editable=False)
    awarded_at = models.DateTimeField(null=True, blank=True)
    reward_receipt = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["goal", "starts_at"], name="unique_challenge_window",
        )]
        ordering = ["-starts_at", "pk"]


class ChallengeActivity(TimestampedModel):
    """A fact survives retries and deletions; never contains private journal prose."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    source_type = models.CharField(max_length=64)
    source_id = models.CharField(max_length=100)
    trigger_type = models.CharField(max_length=32)
    occurred_at = models.DateTimeField()
    occurred_on = models.DateField()
    context = models.JSONField(default=dict)
    voided = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "source_type", "source_id", "trigger_type"],
            name="unique_challenge_activity",
        )]
        indexes = [models.Index(fields=["user", "occurred_on"])]


class ChallengeContribution(models.Model):
    occurrence = models.ForeignKey(
        ChallengeOccurrence, on_delete=models.CASCADE, related_name="contributions",
    )
    activity = models.ForeignKey(ChallengeActivity, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=16, decimal_places=3)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["occurrence", "activity"], name="unique_challenge_contribution",
        )]


class ChallengePin(TimestampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    occurrence = models.ForeignKey(ChallengeOccurrence, on_delete=models.SET_NULL, null=True)
    legacy_quest = models.ForeignKey(Quest, on_delete=models.SET_NULL, null=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=~(models.Q(occurrence__isnull=False) & models.Q(legacy_quest__isnull=False)),
            name="one_challenge_pin_target",
        )]


class DailyBonus(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
    timezone_name = models.CharField(max_length=64, default="America/Phoenix")
    completed_at = models.DateTimeField(null=True, blank=True)
    awarded_at = models.DateTimeField(null=True, blank=True)
    coin_reward = models.PositiveIntegerField(default=10)
    xp_reward = models.PositiveIntegerField(default=20)
    coins_awarded = models.PositiveIntegerField(default=0)
    xp_awarded = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "date"], name="unique_daily_bonus",
        )]
