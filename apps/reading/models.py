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
