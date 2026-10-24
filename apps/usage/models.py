from django.conf import settings
from django.db import models
from django.utils import timezone


class UsageCollectionState(models.Model):
    """A deployment's measurement boundary, preserved when raw events expire."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    started_at = models.DateTimeField(default=timezone.now, editable=False)


class UsageEvent(models.Model):
    """Allowlisted successful human actions, without business content."""

    class Feature(models.TextChoices):
        HOMEWORK = "homework", "Homework"
        CHORES = "chores", "Chores"
        PROJECTS = "projects", "Projects"
        READING = "reading", "Reading"
        MOVEMENT = "movement", "Movement"
        HABITS = "habits", "Habits"
        REWARDS = "rewards", "Rewards"

    class Action(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        COMPLETED = "completed", "Completed"
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        CHECKED_IN = "checked_in", "Checked in"

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    family = models.ForeignKey("families.Family", on_delete=models.CASCADE, related_name="+")
    role = models.CharField(max_length=10)
    feature = models.CharField(max_length=12, choices=Feature.choices)
    action = models.CharField(max_length=12, choices=Action.choices)
    source = models.CharField(max_length=40)
    source_id = models.PositiveBigIntegerField()
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feature", "action", "source", "source_id"], name="usage_unique_source_action"),
        ]
        indexes = [
            models.Index(fields=["family", "occurred_at"], name="usage_family_time"),
            models.Index(fields=["actor", "occurred_at"], name="usage_actor_time"),
        ]


class UsageVisit(models.Model):
    """A foreground app visit, counted once per account per UTC day."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    family = models.ForeignKey("families.Family", on_delete=models.CASCADE, related_name="+")
    role = models.CharField(max_length=10)
    occurred_on = models.DateField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["actor", "occurred_on"], name="usage_unique_daily_visit"),
        ]
        indexes = [models.Index(fields=["family", "occurred_on"], name="usage_visit_family_day")]
