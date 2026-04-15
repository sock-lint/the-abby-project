from django.contrib import admin

from .models import (
    CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory,
)


@admin.register(CharacterProfile)
class CharacterProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "level", "login_streak", "longest_login_streak", "perfect_days_count", "last_active_date"]
    list_filter = ["level"]


@admin.register(ItemDefinition)
class ItemDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "item_type", "rarity", "coin_value"]
    list_filter = ["item_type", "rarity"]
    search_fields = ["name"]


@admin.register(UserInventory)
class UserInventoryAdmin(admin.ModelAdmin):
    list_display = ["user", "item", "quantity"]
    list_filter = ["item__item_type"]
    search_fields = ["user__username", "item__name"]


@admin.register(DropTable)
class DropTableAdmin(admin.ModelAdmin):
    list_display = ["trigger_type", "item", "weight", "min_level"]
    list_filter = ["trigger_type"]


@admin.register(DropLog)
class DropLogAdmin(admin.ModelAdmin):
    list_display = ["user", "item", "trigger_type", "quantity", "was_salvaged", "created_at"]
    list_filter = ["trigger_type", "was_salvaged"]
