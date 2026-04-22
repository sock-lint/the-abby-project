from django.conf import settings
from django.db import models
from django.db.models import Index, Q, UniqueConstraint

from config.base_models import CreatedAtModel


class ChronicleEntry(CreatedAtModel):
    class Kind(models.TextChoices):
        BIRTHDAY      = "birthday", "Birthday"
        CHAPTER_START = "chapter_start", "Chapter start"
        CHAPTER_END   = "chapter_end", "Chapter end"
        FIRST_EVER    = "first_ever", "First ever"
        MILESTONE     = "milestone", "Milestone"
        RECAP         = "recap", "Recap"
        MANUAL        = "manual", "Manual"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chronicle_entries",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    occurred_on = models.DateField()
    chapter_year = models.PositiveIntegerField(
        help_text="August-starting year the chapter covers (e.g. 2025 = Aug 2025–Jul 2026)."
    )
    title = models.CharField(max_length=160)
    summary = models.TextField(blank=True)
    icon_slug = models.CharField(max_length=80, blank=True)
    event_slug = models.CharField(max_length=80, blank=True)
    related_object_type = models.CharField(max_length=40, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            Index(fields=["user", "chapter_year"]),
            Index(fields=["user", "event_slug"]),
            Index(fields=["user", "viewed_at"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["user", "event_slug"],
                condition=Q(kind="first_ever"),
                name="unique_first_ever_per_user",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — string form
        return f"{self.user_id}·{self.kind}·{self.title}"
