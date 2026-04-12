from django.contrib import admin

from .models import CalendarEventMapping, GoogleAccount


@admin.register(GoogleAccount)
class GoogleAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "google_email", "calendar_sync_enabled", "created_at")
    list_filter = ("calendar_sync_enabled",)
    search_fields = ("user__username", "google_email")
    readonly_fields = ("google_id", "encrypted_credentials", "created_at", "updated_at")


@admin.register(CalendarEventMapping)
class CalendarEventMappingAdmin(admin.ModelAdmin):
    list_display = ("user", "content_type", "object_id", "google_event_id")
    list_filter = ("content_type",)
    search_fields = ("user__username", "google_event_id")
