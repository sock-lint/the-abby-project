from rest_framework import serializers

from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory, DropLog


class CharacterProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.CharField(source="user.display_label", read_only=True)
    active_frame = serializers.SerializerMethodField()
    active_title = serializers.SerializerMethodField()
    active_theme = serializers.SerializerMethodField()
    active_pet_accessory = serializers.SerializerMethodField()

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
            "active_frame",
            "active_title",
            "active_theme",
            "active_pet_accessory",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

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

    class Meta:
        model = UserInventory
        fields = ["id", "item", "quantity", "updated_at"]
        read_only_fields = fields


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
