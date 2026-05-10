from django.contrib import admin

from .models import DailyWellbeingEntry


@admin.register(DailyWellbeingEntry)
class DailyWellbeingEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "affirmation_slug", "coin_paid_at")
    list_filter = ("date",)
    search_fields = ("user__username", "affirmation_slug")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "updated_at", "coin_paid_at")
