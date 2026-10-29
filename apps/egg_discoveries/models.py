"""Accepted egg promises and immutable, account-owned activity receipts."""
from django.conf import settings
from django.db import models

from config.base_models import CreatedAtModel, TimestampedModel


class EggDiscovery(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="egg_discoveries")
    offer_key = models.CharField(max_length=180)
    species = models.ForeignKey("pets.PetSpecies", on_delete=models.PROTECT, related_name="egg_discoveries")
    potion_type = models.ForeignKey("pets.PotionType", on_delete=models.PROTECT, related_name="egg_discoveries")
    egg_item = models.ForeignKey("rpg.ItemDefinition", on_delete=models.PROTECT, related_name="egg_discoveries")
    potion_item = models.ForeignKey("rpg.ItemDefinition", on_delete=models.PROTECT, related_name="potion_discoveries")
    food_item = models.ForeignKey("rpg.ItemDefinition", on_delete=models.PROTECT, related_name="food_discoveries")
    snapshot = models.JSONField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    minutes = models.JSONField(default=dict)
    completed_at = models.DateTimeField(null=True, blank=True)
    reward_receipt = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["user", "offer_key"], name="egg_discovery_offer_once"),
            models.UniqueConstraint(fields=["user", "species", "potion_type"], name="egg_discovery_pair_once"),
            models.UniqueConstraint(fields=["user"], condition=models.Q(status="active"), name="one_active_egg_discovery"),
        ]


class DiscoverySearch(CreatedAtModel):
    discovery = models.ForeignKey(EggDiscovery, on_delete=models.CASCADE, related_name="searches")
    number = models.PositiveSmallIntegerField()
    found = models.BooleanField()
    guaranteed = models.BooleanField(default=False)
    # The accepted roll stays attached to its search; reads and retries never reroll.
    roll = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["discovery", "number"], name="egg_search_number_once"),
            models.CheckConstraint(condition=models.Q(number__gte=1, number__lte=5), name="egg_search_number_range"),
        ]


class DiscoveryActivityCredit(CreatedAtModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    discovery = models.ForeignKey(EggDiscovery, on_delete=models.SET_NULL, null=True, blank=True, related_name="credits")
    source_kind = models.CharField(max_length=50)
    source_key = models.CharField(max_length=100)
    category = models.CharField(max_length=12, choices=[("reading", "Reading"), ("movement", "Movement"), ("practice", "Making or practice")])
    occurred_on = models.DateField()
    minutes = models.PositiveSmallIntegerField()
    credited_minutes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "source_kind", "source_key"], name="egg_source_credit_once"),
        ]


class DiscoveryRequest(CreatedAtModel):
    """Retain command identities even after the chosen target has finished."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    client_request_id = models.UUIDField()
    action = models.CharField(max_length=16)
    payload = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "client_request_id"], name="egg_discovery_request_once"),
        ]


class PracticeSession(CreatedAtModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discovery_practice_sessions")
    client_request_id = models.UUIDField()
    name = models.CharField(max_length=100)
    minutes = models.PositiveSmallIntegerField()
    occurred_on = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "client_request_id"], name="discovery_practice_request_once"),
            models.CheckConstraint(condition=models.Q(minutes__gte=1, minutes__lte=240), name="discovery_practice_minutes_range"),
        ]
