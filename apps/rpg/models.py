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

    class Meta:
        ordering = ["-level"]

    def __str__(self):
        return f"{self.user.display_label} (Level {self.level})"


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

    class TriggerType(models.TextChoices):
        CLOCK_OUT = "clock_out", "Clock Out"
        CHORE_COMPLETE = "chore_complete", "Chore Complete"
        HOMEWORK_COMPLETE = "homework_complete", "Homework Complete"
        MILESTONE_COMPLETE = "milestone_complete", "Milestone Complete"
        BADGE_EARNED = "badge_earned", "Badge Earned"
        QUEST_COMPLETE = "quest_complete", "Quest Complete"
        PERFECT_DAY = "perfect_day", "Perfect Day"
        HABIT_LOG = "habit_log", "Habit Log"

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
