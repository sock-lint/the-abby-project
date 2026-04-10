"""Shared abstract model bases.

Abstract models don't need to live inside an installed app; they just need to
be importable wherever concrete models inherit from them.
"""
from django.db import models


class CreatedAtModel(models.Model):
    """Adds an auto-populated ``created_at`` timestamp."""

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class TimestampedModel(CreatedAtModel):
    """Adds both ``created_at`` (immutable) and ``updated_at`` (auto-updated)."""

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
