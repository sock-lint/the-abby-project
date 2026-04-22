from django.conf import settings
from django.db import models

from config.base_models import TimestampedModel


class PetSpecies(TimestampedModel):
    """Base creature type — e.g., Wolf, Dragon, Fox."""

    slug = models.SlugField(max_length=60, unique=True, null=True, blank=True)
    name = models.CharField(max_length=50, unique=True)
    icon = models.CharField(max_length=10)
    sprite_key = models.CharField(
        max_length=64, blank=True,
        help_text="Optional bundled pixel-art sprite slug; falls back to icon when empty.",
    )
    description = models.TextField(blank=True)
    food_preference = models.CharField(max_length=30, blank=True)
    available_potions = models.ManyToManyField(
        "pets.PotionType",
        blank=True,
        related_name="species",
        help_text="Potion variants that can hatch this species.",
    )

    class Meta:
        verbose_name_plural = "pet species"
        ordering = ["name"]

    def __str__(self):
        return f"{self.icon} {self.name}"


class PotionType(TimestampedModel):
    """Variant modifier for pets — e.g., Fire, Ice, Shadow."""

    slug = models.SlugField(max_length=60, unique=True, null=True, blank=True)
    name = models.CharField(max_length=50, unique=True)
    sprite_key = models.CharField(
        max_length=64, blank=True,
        help_text="Optional bundled pixel-art sprite slug for the potion icon.",
    )
    color_hex = models.CharField(max_length=7, default="#8B7355")
    rarity = models.CharField(
        max_length=20,
        choices=[
            ("common", "Common"),
            ("uncommon", "Uncommon"),
            ("rare", "Rare"),
            ("epic", "Epic"),
            ("legendary", "Legendary"),
        ],
        default="common",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserPet(TimestampedModel):
    """A pet owned by a user, hatched from an egg + potion."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pets",
    )
    species = models.ForeignKey(
        PetSpecies, on_delete=models.CASCADE, related_name="user_pets"
    )
    potion = models.ForeignKey(
        PotionType, on_delete=models.CASCADE, related_name="user_pets"
    )
    name = models.CharField(max_length=50, blank=True)  # optional custom name
    growth_points = models.PositiveIntegerField(default=0)  # 0-100
    is_active = models.BooleanField(default=False)
    evolved_to_mount = models.BooleanField(default=False)
    last_fed_at = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "When this pet was last fed. Drives the ``happiness_level`` "
            "computation — see HAPPINESS_THRESHOLDS in apps/pets/services.py. "
            "Gentle-nudge intent: stale pets dim visually, never take damage."
        ),
    )
    consumable_growth_today = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Total growth this pet has received today from direct consumables "
            "(growth_surge, feast_platter). Compared against "
            "CONSUMABLE_GROWTH_DAILY_CAP in apps/pets/services.py. "
            "Resets when consumable_growth_date != today."
        ),
    )
    consumable_growth_date = models.DateField(
        null=True, blank=True,
        help_text=(
            "Local date the consumable_growth_today counter applies to. "
            "When stale, the counter is treated as 0 and reset on next apply."
        ),
    )

    class Meta:
        unique_together = ("user", "species", "potion")
        ordering = ["-is_active", "species__name"]

    def __str__(self):
        display = self.name or f"{self.potion.name} {self.species.name}"
        return f"{self.species.icon} {display} ({self.growth_points}/100)"

    @property
    def is_fully_grown(self):
        return self.growth_points >= 100

    def apply_consumable_growth(self, requested):
        """Apply ``requested`` growth points from a consumable, respecting the
        daily cap. Caller is responsible for ``save()`` — this mutates fields
        in-memory only so the surrounding handler can batch its writes.

        Returns the actual growth applied (may be 0 if the daily cap is
        already used up). Auto-resets the counter on a new local day.
        """
        from apps.pets.services import CONSUMABLE_GROWTH_DAILY_CAP
        from django.utils import timezone

        today = timezone.localdate()
        if self.consumable_growth_date != today:
            self.consumable_growth_today = 0
            self.consumable_growth_date = today

        remaining = max(0, CONSUMABLE_GROWTH_DAILY_CAP - self.consumable_growth_today)
        applied = min(requested, remaining)
        if applied <= 0:
            return 0

        self.consumable_growth_today += applied
        self.growth_points = min(100, self.growth_points + applied)
        return applied

    @property
    def happiness_level(self):
        """'happy' / 'bored' / 'stale' / 'away' based on time since last feed.

        Evolved pets (mounts) always read as 'happy' — they're past the
        feeding loop and their visual shouldn't degrade.
        """
        from apps.pets.services import happiness_for_pet
        return happiness_for_pet(self)


class UserMount(TimestampedModel):
    """Evolved form of a pet — created when pet reaches 100 growth."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mounts",
    )
    species = models.ForeignKey(
        PetSpecies, on_delete=models.CASCADE, related_name="user_mounts"
    )
    potion = models.ForeignKey(
        PotionType, on_delete=models.CASCADE, related_name="user_mounts"
    )
    is_active = models.BooleanField(default=False)
    last_bred_at = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "When this mount last participated in a breeding. Used to enforce "
            "the per-mount breeding cooldown — see MOUNT_BREEDING_COOLDOWN_DAYS "
            "in apps/pets/services.py."
        ),
    )

    class Meta:
        unique_together = ("user", "species", "potion")
        ordering = ["-is_active", "species__name"]

    def __str__(self):
        return f"{self.species.icon} {self.potion.name} {self.species.name} (Mount)"
