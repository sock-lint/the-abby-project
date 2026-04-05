from django.contrib import admin

from .models import Timecard, TimeEntry


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = [
        "user", "project", "clock_in", "clock_out",
        "duration_minutes", "status", "auto_clocked_out",
    ]
    list_filter = ["status", "auto_clocked_out"]
    search_fields = ["user__username", "project__title"]


@admin.register(Timecard)
class TimecardAdmin(admin.ModelAdmin):
    list_display = [
        "user", "week_start", "week_end", "total_hours",
        "total_earnings", "status",
    ]
    list_filter = ["status"]
    search_fields = ["user__username"]
