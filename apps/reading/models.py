from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from config.base_models import TimestampedModel


class ReadingBook(TimestampedModel):
    class Status(models.TextChoices):
        WANT_TO_READ = "want_to_read", "Want to read"
        READING = "reading", "Reading"
        FINISHED = "finished", "Finished"
        PAUSED = "paused", "Paused"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_books")
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.READING)
    interests = models.JSONField(default=list, blank=True)
    client_request_id = models.UUIDField(editable=False)
    create_payload = models.JSONField(editable=False)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_request_id"], name="reading_book_user_request_once"),
        ]


class ReadingSession(TimestampedModel):
    class Format(models.TextChoices):
        PRINT = "print", "Print"
        EBOOK = "ebook", "Ebook"
        AUDIOBOOK = "audiobook", "Audiobook"

    class Reaction(models.TextChoices):
        LOVED = "loved", "Loved it"
        LIKED = "liked", "Liked it"
        OKAY = "okay", "It was okay"
        NOT_FOR_ME = "not_for_me", "Not for me"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_sessions")
    # RESTRICT protects a shelf book while still permitting account deletion to
    # cascade through that account's books and sessions in the same operation.
    book = models.ForeignKey(ReadingBook, on_delete=models.RESTRICT, related_name="sessions")
    occurred_on = models.DateField()
    duration_minutes = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(600)])
    pages_read = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(2000)])
    section = models.CharField(max_length=120, blank=True)
    reflection = models.TextField(max_length=3000, blank=True)
    format = models.CharField(max_length=9, choices=Format.choices, default=Format.PRINT)
    reaction = models.CharField(max_length=10, choices=Reaction.choices, blank=True)
    client_request_id = models.UUIDField(editable=False)
    create_payload = models.JSONField(editable=False)

    class Meta:
        ordering = ["-occurred_on", "-created_at", "-id"]
        indexes = [models.Index(fields=["user", "occurred_on"], name="reading_session_user_day")]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_request_id"], name="reading_session_user_request_once"),
            models.CheckConstraint(condition=models.Q(duration_minutes__lte=600), name="reading_minutes_at_most_600"),
            models.CheckConstraint(condition=models.Q(pages_read__lte=2000), name="reading_pages_at_most_2000"),
        ]


class ReadingDailyReward(TimestampedModel):
    """Durable daily credit; deleting or correcting a log cannot rearm it."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_daily_rewards")
    day = models.DateField()
    minutes_credited = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(10)])
    awarded_at = models.DateTimeField(null=True, blank=True)
    xp_awarded = models.PositiveIntegerField(default=0)
    coins_awarded = models.PositiveIntegerField(default=0)
    source_session = models.OneToOneField(
        ReadingSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="reading_daily_reward",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "day"], name="reading_daily_reward_user_day"),
            models.CheckConstraint(condition=models.Q(minutes_credited__lte=10), name="reading_daily_minutes_at_most_10"),
        ]


class ReadingRewardCredit(models.Model):
    """Keep request eligibility fixed after the original log is deleted."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    client_request_id = models.UUIDField(editable=False)
    day = models.DateField()
    minutes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "client_request_id"], name="reading_credit_user_request_once"),
            models.CheckConstraint(condition=models.Q(minutes__lte=10), name="reading_credit_minutes_at_most_10"),
        ]


class ReadingDiscoveryFeedback(TimestampedModel):
    """An explicit discovery preference, never a reading log or reward."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_discovery_feedback")
    catalog_id = models.CharField(max_length=80)
    choice = models.CharField(max_length=20, choices=[
        ("not_interested", "Not interested"), ("already_read", "Already read"),
    ])

    class Meta:
        ordering = ["catalog_id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "catalog_id"], name="reading_feedback_user_catalog_once"),
        ]


class ReadingFamilySuggestion(TimestampedModel):
    """A parent's invitation; saving the book remains the reader's choice."""

    class Status(models.TextChoices):
        PENDING = "pending", "Suggested"
        DISMISSED = "dismissed", "Dismissed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_family_suggestions")
    suggested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="sent_reading_suggestions",
    )
    author_name = models.CharField(max_length=150)
    catalog_id = models.CharField(max_length=80)
    message = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    client_request_id = models.UUIDField(editable=False)
    create_payload = models.JSONField(editable=False)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_request_id"], name="reading_suggestion_user_request_once"),
        ]
