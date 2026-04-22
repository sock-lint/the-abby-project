from django.contrib import admin

from .models import ChronicleEntry


@admin.register(ChronicleEntry)
class ChronicleEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "occurred_on", "chapter_year", "title", "viewed_at")
    list_filter = ("kind", "chapter_year")
    search_fields = ("title", "summary", "event_slug", "user__username")
    raw_id_fields = ("user",)
