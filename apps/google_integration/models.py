from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel, TimestampedModel


class GoogleAccount(TimestampedModel):
    """Stores Google OAuth2 credentials linked to a user.

    One-to-one with User. Parents can link accounts on behalf of children.
    OAuth tokens are Fernet-encrypted at rest (see GoogleAuthService).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_account",
    )
    google_id = models.CharField(max_length=255, unique=True)
    google_email = models.EmailField()
    encrypted_credentials = models.BinaryField(
        help_text="Fernet-encrypted JSON of access_token, refresh_token, expiry, scopes.",
    )
    calendar_sync_enabled = models.BooleanField(default=False)
    calendar_id = models.CharField(
        max_length=255,
        default="primary",
        help_text="Google Calendar ID to sync events to.",
    )
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_google_accounts",
        help_text="Parent who linked this account (for child accounts).",
    )

    class Meta:
        verbose_name = "Google account"

    def __str__(self):
        return f"{self.user} — {self.google_email}"


class CalendarEventMapping(CreatedAtModel):
    """Maps an app object to a Google Calendar event for update/delete."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_mappings",
    )
    content_type = models.CharField(
        max_length=50,
        help_text='Discriminator, e.g. "project_due", "chore", "time_entry".',
    )
    object_id = models.PositiveIntegerField()
    google_event_id = models.CharField(max_length=255)

    class Meta:
        unique_together = [("user", "content_type", "object_id")]
        verbose_name = "Calendar event mapping"

    def __str__(self):
        return f"{self.content_type}:{self.object_id} → {self.google_event_id}"
