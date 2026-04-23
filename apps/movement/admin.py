from django.contrib import admin

from .models import MovementSession, MovementType, MovementTypeSkillTag


class MovementTypeSkillTagInline(admin.TabularInline):
    model = MovementTypeSkillTag
    extra = 0
    autocomplete_fields = ("skill",)


@admin.register(MovementType)
class MovementTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "default_intensity", "is_active", "order")
    list_filter = ("is_active", "default_intensity")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MovementTypeSkillTagInline]


@admin.register(MovementSession)
class MovementSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "movement_type", "duration_minutes",
        "intensity", "occurred_on", "xp_awarded",
    )
    list_filter = ("intensity", "occurred_on")
    search_fields = ("user__username", "notes", "movement_type__name")
    autocomplete_fields = ("user", "movement_type")
    date_hierarchy = "occurred_on"
