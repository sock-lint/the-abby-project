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

    class Meta:
        unique_together = ("user", "species", "potion")
        ordering = ["-is_active", "species__name"]

    def __str__(self):
        display = self.name or f"{self.potion.name} {self.species.name}"
        return f"{self.species.icon} {display} ({self.growth_points}/100)"

    @property
    def is_fully_grown(self):
        return self.growth_points >= 100


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

    class Meta:
        unique_together = ("user", "species", "potion")
        ordering = ["-is_active", "species__name"]

    def __str__(self):
        return f"{self.species.icon} {self.potion.name} {self.species.name} (Mount)"
