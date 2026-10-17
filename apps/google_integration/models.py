from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from config.base_models import CreatedAtModel, TimestampedModel


class GoogleOAuthAdmission(models.Model):
    """Singleton row serializes the hard bound on retained OAuth transactions."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)


class GoogleAuthInvalidation(models.Model):
    """Revocations also fence anonymous flows whose Google identity is not known yet."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, primary_key=True,
                               on_delete=models.CASCADE, related_name="+")
    invalidated_at = models.DateTimeField()


class GoogleOAuthTransaction(models.Model):
    """One browser-bound authorization; never stores a plaintext bearer credential."""

    state_hash = models.CharField(max_length=64, unique=True)
    browser_challenge = models.CharField(max_length=43)
    mode = models.CharField(max_length=5)
    initiator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                 on_delete=models.CASCADE, related_name="+")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.CASCADE, related_name="+")
    initiator_family_id = models.PositiveBigIntegerField(null=True)
    target_family_id = models.PositiveBigIntegerField(null=True)
    initiator_role = models.CharField(max_length=10, blank=True)
    target_role = models.CharField(max_length=10, blank=True)
    initiator_password_hash = models.CharField(max_length=64, blank=True)
    target_password_hash = models.CharField(max_length=64, blank=True)
    initiator_token_hash = models.CharField(max_length=64, blank=True)
    client_hash = models.CharField(max_length=64, db_index=True)
    encrypted_payload = models.BinaryField(default=bytes)
    stage = models.CharField(max_length=10, default="pending")
    exchange_hash = models.CharField(max_length=64, unique=True, null=True)
    created_at = models.DateTimeField(db_default=Now())
    expires_at = models.DateTimeField(db_index=True)
    exchange_expires_at = models.DateTimeField(null=True)


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
