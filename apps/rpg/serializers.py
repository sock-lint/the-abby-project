from django.utils import timezone
from rest_framework import serializers

from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory, DropLog


class CharacterProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.CharField(source="user.display_label", read_only=True)
    active_frame = serializers.SerializerMethodField()
    active_title = serializers.SerializerMethodField()
    active_theme = serializers.SerializerMethodField()
    active_pet_accessory = serializers.SerializerMethodField()
    active_trophy_badge = serializers.SerializerMethodField()
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
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

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
            "name": item.name,
            "icon": item.icon,
            "sprite_key": item.sprite_key,
            "rarity": item.rarity,
            "metadata": item.metadata,
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
    rarity_display = serializers.CharField(source="get_rarity_display", read_only=True)
    type_display = serializers.CharField(source="get_item_type_display", read_only=True)
    pet_species_name = serializers.CharField(source="pet_species.name", read_only=True, default=None)
    potion_type_name = serializers.CharField(source="potion_type.name", read_only=True, default=None)
    food_species_name = serializers.CharField(source="food_species.name", read_only=True, default=None)

    class Meta:
        model = ItemDefinition
        fields = [
            "id", "name", "description", "icon", "sprite_key", "item_type", "type_display",
            "rarity", "rarity_display", "coin_value", "metadata",
            "pet_species_name", "potion_type_name", "food_species_name",
        ]
        read_only_fields = fields


class UserInventorySerializer(serializers.ModelSerializer):
    item = ItemDefinitionSerializer(read_only=True)
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = UserInventory
        fields = ["id", "item", "quantity", "updated_at", "available_actions"]
        read_only_fields = fields

    def get_available_actions(self, obj):
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
                "label": "Hatch in Hatchery",
                "to": "/bestiary?tab=hatchery",
            }],
            ItemDefinition.ItemType.POTION: [{
                "id": "hatch",
                "label": "Hatch in Hatchery",
                "to": "/bestiary?tab=hatchery",
            }],
            ItemDefinition.ItemType.FOOD: [{
                "id": "feed",
                "label": "Feed a companion",
                "to": "/bestiary?tab=companions",
            }],
            ItemDefinition.ItemType.QUEST_SCROLL: [{
                "id": "start_quest",
                "label": "Start trial",
                "to": f"/trials?scroll_item={item_id}",
            }],
        }
        if item_type in (
            ItemDefinition.ItemType.COSMETIC_FRAME,
            ItemDefinition.ItemType.COSMETIC_TITLE,
            ItemDefinition.ItemType.COSMETIC_THEME,
            ItemDefinition.ItemType.COSMETIC_PET_ACCESSORY,
        ):
            return [{
                "id": "equip",
                "label": "Equip in Sigil",
                "to": "/sigil",
            }]
        return action_map.get(item_type, [])


class DropLogSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_icon = serializers.CharField(source="item.icon", read_only=True)
    item_sprite_key = serializers.CharField(source="item.sprite_key", read_only=True)
    item_rarity = serializers.CharField(source="item.rarity", read_only=True)

    class Meta:
        model = DropLog
        fields = [
            "id", "item", "item_name", "item_icon", "item_sprite_key", "item_rarity",
            "trigger_type", "quantity", "was_salvaged", "created_at",
        ]
        read_only_fields = fields
