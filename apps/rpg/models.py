from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.rpg.constants import TriggerType
from apps.rpg.storage import sprite_storage
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
    streak_freeze_expires_at = models.DateField(
        null=True, blank=True,
        help_text=(
            "While set to today or later, a missed day doesn't reset the "
            "login streak. Consumed on use by the streak-freeze consumable."
        ),
    )
    streak_freezes_used = models.PositiveIntegerField(
        default=0,
        help_text="Lifetime count of streak-freeze consumables used.",
    )
    xp_boost_expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="While in the future, Scholar's Draught multiplies XP gains.",
    )
    coin_boost_expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="While in the future, Lucky Coin multiplies coin drops.",
    )
    drop_boost_expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="While in the future, Drop Charm increases drop rates.",
    )
    pet_growth_boost_remaining = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of pet feeds that still get Growth Tonic's 2x multiplier.",
    )
    consumable_effects_used = models.JSONField(
        default=list, blank=True,
        help_text="Distinct consumable effect slugs ever used (for Alchemist-style badges).",
    )
    active_frame = models.ForeignKey(
        "rpg.ItemDefinition", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="equipped_as_frame",
        limit_choices_to={"item_type": "cosmetic_frame"},
    )
    active_title = models.ForeignKey(
        "rpg.ItemDefinition", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="equipped_as_title",
        limit_choices_to={"item_type": "cosmetic_title"},
    )
    active_theme = models.ForeignKey(
        "rpg.ItemDefinition", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="equipped_as_theme",
        limit_choices_to={"item_type": "cosmetic_theme"},
    )
    active_pet_accessory = models.ForeignKey(
        "rpg.ItemDefinition", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="equipped_as_pet_accessory",
        limit_choices_to={"item_type": "cosmetic_pet_accessory"},
    )
    active_trophy_badge = models.ForeignKey(
        "achievements.Badge", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="equipped_as_trophy",
        help_text=(
            "Optional hero badge the user has elected to display on their "
            "profile and in notifications. Must be a badge they've earned; "
            "enforcement lives in the trophy endpoint, not the schema, so the "
            "FK can stay loose if badges are archived later."
        ),
    )
    unlocks = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-level"]

    def __str__(self):
        return f"{self.user.display_label} (Level {self.level})"

    def is_unlocked(self, slug: str) -> bool:
        entry = self.unlocks.get(slug) or {}
        return bool(entry.get("enabled"))

    def unlock(self, slug: str, *, save: bool = False) -> None:
        from datetime import date
        self.unlocks[slug] = {"enabled": True, "enabled_at": date.today().isoformat()}
        if save:
            self.save(update_fields=["unlocks"])

    def lock(self, slug: str, *, save: bool = False) -> None:
        entry = self.unlocks.get(slug) or {}
        entry["enabled"] = False
        self.unlocks[slug] = entry
        if save:
            self.save(update_fields=["unlocks"])


class ItemDefinition(TimestampedModel):
    """Master catalog of all droppable/ownable items."""

    class ItemType(models.TextChoices):
        EGG = "egg", "Pet Egg"
        POTION = "potion", "Hatching Potion"
        FOOD = "food", "Pet Food"
        COSMETIC_FRAME = "cosmetic_frame", "Avatar Frame"
        COSMETIC_TITLE = "cosmetic_title", "Title"
        COSMETIC_THEME = "cosmetic_theme", "Dashboard Theme"
        COSMETIC_PET_ACCESSORY = "cosmetic_pet_accessory", "Pet Accessory"
        QUEST_SCROLL = "quest_scroll", "Quest Scroll"
        COIN_POUCH = "coin_pouch", "Coin Pouch"
        CONSUMABLE = "consumable", "Consumable"

    class Rarity(models.TextChoices):
        COMMON = "common", "Common"
        UNCOMMON = "uncommon", "Uncommon"
        RARE = "rare", "Rare"
        EPIC = "epic", "Epic"
        LEGENDARY = "legendary", "Legendary"

    slug = models.SlugField(max_length=100, unique=True, null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50)
    sprite_key = models.CharField(
        max_length=64, blank=True,
        help_text="Optional bundled pixel-art sprite slug; falls back to icon when empty.",
    )
    item_type = models.CharField(max_length=30, choices=ItemType.choices)
    rarity = models.CharField(max_length=20, choices=Rarity.choices, default=Rarity.COMMON)
    coin_value = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    # Typed references replace stringly-typed metadata["species"]/["variant"]/["food_type"].
    # metadata stays for genuinely free-form fields (border_color, title text, pouch coins).
    pet_species = models.ForeignKey(
        "pets.PetSpecies",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="eggs",
        help_text="For eggs: the species that hatches from this egg.",
    )
    potion_type = models.ForeignKey(
        "pets.PotionType",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="item_variants",
        help_text="For potions: the variant this item represents.",
    )
    food_species = models.ForeignKey(
        "pets.PetSpecies",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="foods",
        help_text="For food: the species that prefers this food (matches food_preference).",
    )

    class Meta:
        ordering = ["item_type", "rarity", "name"]

    def __str__(self):
        return f"{self.icon} {self.name} ({self.get_rarity_display()})"


class UserInventory(TimestampedModel):
    """Tracks quantity of each item a user owns."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inventory",
    )
    item = models.ForeignKey(
        ItemDefinition, on_delete=models.CASCADE, related_name="inventory_entries",
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("user", "item")
        ordering = ["item__item_type", "item__name"]

    def __str__(self):
        return f"{self.user} x{self.quantity} {self.item.name}"


class DropTable(TimestampedModel):
    """Configurable drop table linking triggers to items with weights."""

    TriggerType = TriggerType

    trigger_type = models.CharField(max_length=30, choices=TriggerType.choices)
    item = models.ForeignKey(
        ItemDefinition, on_delete=models.CASCADE, related_name="drop_table_entries",
    )
    weight = models.PositiveIntegerField(default=1)
    min_level = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["trigger_type", "-weight"]

    def __str__(self):
        return f"{self.get_trigger_type_display()} -> {self.item.name} (w={self.weight})"


class DropLog(CreatedAtModel):
    """Audit trail of items dropped for users."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="drop_logs",
    )
    item = models.ForeignKey(
        ItemDefinition, on_delete=models.CASCADE, related_name="drop_log_entries",
    )
    trigger_type = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField(default=1)
    was_salvaged = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]


class SpriteAsset(TimestampedModel):
    """Runtime-authored sprite (static or animated strip) stored on Ceph.

    Replaces the build-time scripts/sprite_manifest.yaml + Vite bundle flow.
    One row per registered sprite; the ``image`` FieldFile points at a
    public-read Ceph object under the ``abby-sprites`` bucket. Content YAML
    and model rows reference sprites by ``slug`` via ``sprite_key`` fields
    (unchanged — just resolved through DB now).
    """

    SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"

    class FrameLayout(models.TextChoices):
        HORIZONTAL = "horizontal", "Horizontal strip"
        VERTICAL = "vertical", "Vertical strip"

    slug = models.CharField(
        max_length=64,
        unique=True,
        validators=[RegexValidator(SLUG_PATTERN, "Slug must be lowercase a-z0-9 and hyphens.")],
    )
    image = models.ImageField(upload_to="rpg-sprites/", storage=sprite_storage, blank=True)
    pack = models.CharField(max_length=40, db_index=True, default="user-authored")
    frame_count = models.PositiveSmallIntegerField(default=1)
    fps = models.PositiveSmallIntegerField(default=0)
    frame_width_px = models.PositiveSmallIntegerField()
    frame_height_px = models.PositiveSmallIntegerField()
    frame_layout = models.CharField(
        max_length=12,
        choices=FrameLayout.choices,
        default=FrameLayout.HORIZONTAL,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sprites_authored",
    )

    class Meta:
        indexes = [models.Index(fields=["pack", "slug"])]

    def clean(self):
        super().clean()
        if self.frame_count < 1:
            raise ValidationError({"frame_count": "frame_count must be >= 1"})
        if self.frame_count == 1 and self.fps != 0:
            raise ValidationError({"fps": "static sprite (frame_count=1) must have fps=0"})
        if self.frame_count > 1 and self.fps < 1:
            raise ValidationError({"fps": "animated sprite (frame_count>1) requires fps >= 1"})

    def __str__(self):
        tag = "animated" if self.frame_count > 1 else "static"
        return f"{self.slug} ({tag}, {self.pack})"
