from django.contrib import admin

from .models import Creation, CreationBonusSkillTag


class CreationBonusSkillTagInline(admin.TabularInline):
    model = CreationBonusSkillTag
    extra = 0


@admin.register(Creation)
class CreationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "primary_skill", "status", "occurred_on", "xp_awarded", "bonus_xp_awarded")
    list_filter = ("status", "occurred_on")
    search_fields = ("caption", "user__username")
    autocomplete_fields = ("user", "primary_skill", "secondary_skill", "decided_by")
    inlines = [CreationBonusSkillTagInline]
