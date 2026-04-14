from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel, TimestampedModel


class CharacterProfile(TimestampedModel):
    """RPG character profile auto-created for every user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="character_profile",
    )
    level = models.PositiveIntegerField(default=0)
    login_streak = models.PositiveIntegerField(default=0)
    longest_login_streak = models.PositiveIntegerField(default=0)
    last_active_date = models.DateField(null=True, blank=True)
    perfect_days_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-level"]

    def __str__(self):
        name = self.user.display_name or self.user.username
        return f"{name} (Level {self.level})"
