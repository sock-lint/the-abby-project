from rest_framework import serializers

from apps.rpg.models import CharacterProfile, Habit, HabitLog, ItemDefinition, UserInventory, DropLog


class CharacterProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.SerializerMethodField()
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
            "active_frame",
            "active_title",
            "active_theme",
            "active_pet_accessory",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_display_name(self, obj):
        return obj.user.display_name or obj.user.username

    @staticmethod
    def _compact_item(item):
        if item is None:
            return None
        return {
            "id": item.pk,
            "name": item.name,
            "icon": item.icon,
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


class HabitSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()

    class Meta:
        model = Habit
        fields = [
            "id",
            "name",
            "icon",
            "habit_type",
            "user",
            "created_by",
            "created_by_name",
            "coin_reward",
            "xp_reward",
            "strength",
            "color",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "strength",
            "color",
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.display_name or obj.created_by.username

    def get_color(self, obj):
        s = obj.strength
        if s < -5:
            return "red-dark"
        if s < 0:
            return "red-light"
        if s == 0:
            return "yellow"
        if s <= 5:
            return "green-light"
        if s <= 10:
            return "green"
        return "blue"


class HabitWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habit
        fields = [
            "name",
            "icon",
            "habit_type",
            "user",
            "coin_reward",
            "xp_reward",
            "is_active",
        ]


class HabitLogSerializer(serializers.ModelSerializer):
    habit_name = serializers.CharField(source="habit.name", read_only=True)
    habit_icon = serializers.CharField(source="habit.icon", read_only=True)

    class Meta:
        model = HabitLog
        fields = [
            "id",
            "habit",
            "habit_name",
            "habit_icon",
            "user",
            "direction",
            "streak_at_time",
            "created_at",
        ]
        read_only_fields = fields


class ItemDefinitionSerializer(serializers.ModelSerializer):
    rarity_display = serializers.CharField(source="get_rarity_display", read_only=True)
    type_display = serializers.CharField(source="get_item_type_display", read_only=True)

    class Meta:
        model = ItemDefinition
        fields = [
            "id", "name", "description", "icon", "item_type", "type_display",
            "rarity", "rarity_display", "coin_value", "metadata",
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
    item_rarity = serializers.CharField(source="item.rarity", read_only=True)

    class Meta:
        model = DropLog
        fields = [
            "id", "item", "item_name", "item_icon", "item_rarity",
            "trigger_type", "quantity", "was_salvaged", "created_at",
        ]
        read_only_fields = fields
