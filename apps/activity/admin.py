from django.contrib import admin

from .models import ActivityEvent


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at", "category", "event_type", "subject", "actor",
        "coins_delta", "money_delta", "xp_delta",
    )
    list_filter = ("category", "event_type")
    search_fields = ("summary", "event_type", "subject__username", "actor__username")
    readonly_fields = tuple(f.name for f in ActivityEvent._meta.fields) + ("target",)
    date_hierarchy = "occurred_at"
