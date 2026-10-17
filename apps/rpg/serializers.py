from django.utils import timezone
from rest_framework import serializers
from apps.rpg.catalog_icons import item_catalog_icon
from apps.pets.lifecycle import egg_species_slug, item_lifecycle_stage

from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory, DropLog
from .avatar import (
    AVATAR_DEFAULTS, AVATAR_OPTIONS, AvatarConfigurationError, avatar_appearance,
    normalize_avatar_configuration, saved_avatar_configuration,
)
from .catalog_support import item_is_available
from .card_styles import card_style_metadata


class AvatarPreferencesUpdateSerializer(serializers.Serializer):
    """A complete appearance replacement; omitted choices use pack defaults."""

    avatar_preferences = serializers.JSONField()

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({
                    key: ["This field is not supported."] for key in sorted(unknown)
                })
        return super().to_internal_value(data)

    def validate_avatar_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Appearance choices must be an object.")
        unknown = set(value) - set(AVATAR_OPTIONS)
        if unknown:
            raise serializers.ValidationError({
                key: ["This appearance choice is not supported."] for key in sorted(unknown)
            })
        errors = {
            key: [f"Choose one of: {', '.join(AVATAR_OPTIONS[key])}."]
            for key, choice in value.items()
            if not isinstance(choice, str) or choice not in AVATAR_OPTIONS[key]
        }
        if errors:
            raise serializers.ValidationError(errors)
        return {**AVATAR_DEFAULTS, **value}


class AvatarConfigurationUpdateSerializer(serializers.Serializer):
    """Self-only generic replacement; base controls and fitted shared items."""

    avatar_configuration = serializers.JSONField()

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ["This field is not supported."] for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate_avatar_configuration(self, value):
        try:
            return normalize_avatar_configuration(value)
        except AvatarConfigurationError as error:
            raise serializers.ValidationError(error.errors) from error


class CharacterProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.CharField(source="user.display_label", read_only=True)
    total_xp = serializers.SerializerMethodField()
    xp_in_level = serializers.SerializerMethodField()
    xp_needed_for_level = serializers.SerializerMethodField()
    active_frame = serializers.SerializerMethodField()
    active_title = serializers.SerializerMethodField()
    active_theme = serializers.SerializerMethodField()
    active_pet_accessory = serializers.SerializerMethodField()
    active_trophy_badge = serializers.SerializerMethodField()
    avatar_preferences = serializers.SerializerMethodField()
    avatar_configuration = serializers.SerializerMethodField()
    # Active-boost timers — surface the seconds-remaining so the frontend
    # can render a countdown chip. Null when the boost is inactive (either
    # never used or already expired). The model still owns the absolute
    # ``*_expires_at`` timestamps for the multiplier logic; this is just
    # the display projection.
    xp_boost_seconds_remaining = serializers.SerializerMethodField()
    coin_boost_seconds_remaining = serializers.SerializerMethodField()
    drop_boost_seconds_remaining = serializers.SerializerMethodField()
    # Counter-style boost: number of doubled pet feeds left, not a timer.
    pet_growth_boost_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = CharacterProfile
        fields = [
            "id",
            "username",
            "display_name",
            "level",
            "total_xp",
            "xp_in_level",
            "xp_needed_for_level",
            "login_streak",
            "longest_login_streak",
            "last_active_date",
            "perfect_days_count",
            "streak_freeze_expires_at",
            "xp_boost_expires_at",
            "coin_boost_expires_at",
            "drop_boost_expires_at",
            "xp_boost_seconds_remaining",
            "coin_boost_seconds_remaining",
            "drop_boost_seconds_remaining",
            "pet_growth_boost_remaining",
            "active_frame",
            "active_title",
            "active_theme",
            "active_pet_accessory",
            "active_trophy_badge",
            "avatar_preferences",
            "avatar_configuration",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _xp_progress(self, obj):
        if not hasattr(self, "_xp_by_profile"):
            self._xp_by_profile = {}
        if obj.pk not in self._xp_by_profile:
            self._xp_by_profile[obj.pk] = obj.xp_progress
        return self._xp_by_profile[obj.pk]

    def get_total_xp(self, obj):
        return self._xp_progress(obj)["total_xp"]

    def get_xp_in_level(self, obj):
        return self._xp_progress(obj)["xp_in_level"]

    def get_xp_needed_for_level(self, obj):
        return self._xp_progress(obj)["xp_needed_for_level"]

    def get_avatar_preferences(self, obj):
        return avatar_appearance(obj.avatar_preferences)

    def get_avatar_configuration(self, obj):
        return saved_avatar_configuration(obj.avatar_configuration, obj.avatar_preferences)

    @staticmethod
    def _seconds_until(expires_at):
        if expires_at is None:
            return None
        delta = expires_at - timezone.now()
        seconds = int(delta.total_seconds())
        return seconds if seconds > 0 else None

    def get_xp_boost_seconds_remaining(self, obj):
        return self._seconds_until(obj.xp_boost_expires_at)

    def get_coin_boost_seconds_remaining(self, obj):
        return self._seconds_until(obj.coin_boost_expires_at)

    def get_drop_boost_seconds_remaining(self, obj):
        return self._seconds_until(obj.drop_boost_expires_at)

    @staticmethod
    def _compact_item(item):
        if item is None:
            return None
        return {
            "id": item.pk,
            "catalog_icon": item_catalog_icon(item),
            "name": item.display_name,
            "icon": item.icon,
            "sprite_key": item.sprite_key,
            "rarity": item.rarity,
            "metadata": card_style_metadata(item),
        }

    def get_active_frame(self, obj):
        return self._compact_item(obj.active_frame)

    def get_active_title(self, obj):
        return self._compact_item(obj.active_title)

    def get_active_theme(self, obj):
        return self._compact_item(obj.active_theme)

    def get_active_pet_accessory(self, obj):
        return self._compact_item(obj.active_pet_accessory)

    def get_active_trophy_badge(self, obj):
        badge = obj.active_trophy_badge
        if badge is None:
            return None
        return {
            "id": badge.pk,
            "name": badge.name,
            "icon": badge.icon,
            "rarity": badge.rarity,
            "description": badge.description,
        }


class ItemDefinitionSerializer(serializers.ModelSerializer):
    metadata = serializers.SerializerMethodField()
    name = serializers.CharField(source="display_name", read_only=True)
    catalog_icon = serializers.SerializerMethodField()
    catalog_available = serializers.SerializerMethodField()
    rarity_display = serializers.CharField(source="get_rarity_display", read_only=True)
    type_display = serializers.SerializerMethodField()
    pet_species_name = serializers.CharField(source="pet_species.name", read_only=True, default=None)
    potion_type_name = serializers.CharField(source="potion_type.name", read_only=True, default=None)
    food_species_name = serializers.CharField(source="food_species.name", read_only=True, default=None)
    lifecycle_stage = serializers.SerializerMethodField()
    pet_species_slug = serializers.SerializerMethodField()

    class Meta:
        model = ItemDefinition
        fields = [
            "id", "slug", "name", "description", "icon", "sprite_key", "catalog_icon", "item_type", "type_display",
            "rarity", "rarity_display", "coin_value", "metadata",
            "pet_species_name", "potion_type_name", "food_species_name", "catalog_available",
            "lifecycle_stage", "pet_species_slug",
        ]
        read_only_fields = fields

    def get_catalog_available(self, obj):
        return item_is_available(obj)

    def get_metadata(self, obj):
        return card_style_metadata(obj)

    def get_catalog_icon(self, obj):
        return item_catalog_icon(obj)

    def get_lifecycle_stage(self, obj):
        return item_lifecycle_stage(obj)

    def get_pet_species_slug(self, obj):
        return egg_species_slug(obj)

    def get_type_display(self, obj):
        if obj.item_type == ItemDefinition.ItemType.COSMETIC_THEME:
            return "Color theme"
        return obj.get_item_type_display()


class UserInventorySerializer(serializers.ModelSerializer):
    item = ItemDefinitionSerializer(read_only=True)
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = UserInventory
        fields = ["id", "item", "quantity", "updated_at", "available_actions"]
        read_only_fields = fields

    def get_available_actions(self, obj):
        if not item_is_available(obj.item):
            # Saved keepsakes remain readable, but do not advertise a new
            # hatch/equip action that the authoritative service rejects.
            return []
        item_type = obj.item.item_type
        item_id = obj.item_id
        action_map = {
            ItemDefinition.ItemType.CONSUMABLE: [{
                "id": "use",
                "label": "Use",
                "endpoint": f"/api/inventory/{item_id}/use/",
            }],
            ItemDefinition.ItemType.COIN_POUCH: [{
                "id": "open",
                "label": "Open",
                "endpoint": f"/api/inventory/{item_id}/open/",
            }],
            ItemDefinition.ItemType.EGG: [{
                "id": "hatch",
                "label": "Hatch a companion",
                "to": "/bestiary?tab=hatchery",
            }],
            ItemDefinition.ItemType.POTION: [{
                "id": "hatch",
                "label": "Hatch a companion",
                "to": "/bestiary?tab=hatchery",
            }],
            ItemDefinition.ItemType.FOOD: [{
                "id": "feed",
                "label": "Feed a companion",
                "to": "/bestiary?tab=companions",
            }],
            ItemDefinition.ItemType.QUEST_SCROLL: [{
                "id": "start_quest",
                "label": "View challenges",
                "to": "/quests?tab=trials",
            }],
        }
        if item_type == ItemDefinition.ItemType.COSMETIC_THEME:
            return [{
                "id": "equip",
                "label": "Change color theme",
                "to": "/settings#appearance",
            }]
        if item_type in (
            ItemDefinition.ItemType.COSMETIC_FRAME,
            ItemDefinition.ItemType.COSMETIC_TITLE,
            ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
        ):
            return [{
                "id": "equip",
                "label": "Equip in Profile",
                "to": "/sigil",
            }]
        return action_map.get(item_type, [])


class DropLogSerializer(serializers.ModelSerializer):
    item_catalog_icon = serializers.SerializerMethodField()
    item_name = serializers.CharField(source="item.display_name", read_only=True)
    item_icon = serializers.CharField(source="item.icon", read_only=True)
    item_sprite_key = serializers.CharField(source="item.sprite_key", read_only=True)
    item_rarity = serializers.CharField(source="item.rarity", read_only=True)

    class Meta:
        model = DropLog
        fields = [
            "id", "item", "item_name", "item_icon", "item_sprite_key", "item_catalog_icon", "item_rarity",
            "trigger_type", "quantity", "was_salvaged", "created_at",
        ]
        read_only_fields = fields

    def get_item_catalog_icon(self, obj):
        return item_catalog_icon(obj.item)
