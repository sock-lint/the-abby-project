from django.contrib import admin

from .models import CalendarEventMapping, GoogleAccount


@admin.register(GoogleAccount)
class GoogleAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "google_email", "calendar_sync_enabled", "created_at", "updated_at")
    list_filter = ("calendar_sync_enabled", "created_at")
    search_fields = ("user__username", "google_email", "google_id")
    readonly_fields = ("google_id", "encrypted_credentials", "created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(CalendarEventMapping)
class CalendarEventMappingAdmin(admin.ModelAdmin):
    list_display = ("user", "content_type", "object_id", "google_event_id", "created_at")
    list_filter = ("content_type", "created_at")
    search_fields = ("user__username", "google_event_id", "object_id")
    date_hierarchy = "created_at"
