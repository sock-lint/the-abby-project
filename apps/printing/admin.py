from django.contrib import admin

from .models import (
    PrintBudget,
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintJobEvent,
    PrintRequest,
)


class PrintJobEventInline(admin.TabularInline):
    model = PrintJobEvent
    extra = 0
    fields = ("created_at", "kind", "message", "code", "severity", "percent_complete")
    readonly_fields = fields
    ordering = ("created_at", "id")


@admin.register(PrinterProfile)
class PrinterProfileAdmin(admin.ModelAdmin):
    list_display = (
        "name", "serial", "family", "transport", "is_active",
        "last_gcode_state", "last_report_at",
    )
    list_filter = ("transport", "is_active", "model_name")
    search_fields = ("name", "serial", "family__name")
    autocomplete_fields = ("family", "created_by")
    # Credentials are Fernet-encrypted; the raw column is meaningless in the
    # admin and rendering it would be a needless place for a secret to leak.
    exclude = ("encrypted_secret",)
    readonly_fields = ("last_report_at", "last_gcode_state", "last_error")


@admin.register(PrintRequest)
class PrintRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "user", "status", "slug", "plate_filename",
        "estimated_grams", "needed_by", "created_at",
    )
    list_filter = ("status", "source_kind", "needed_by")
    search_fields = ("title", "slug", "user__username", "source_url")
    autocomplete_fields = ("user", "decided_by")
    date_hierarchy = "created_at"
    readonly_fields = ("slug", "plate_filename", "print_count")


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "subtask_name", "printer", "request", "state",
        "percent_complete", "started_at", "finished_at",
    )
    list_filter = ("state", "link_source", "printer")
    search_fields = ("subtask_name", "normalized_name", "task_id", "failure_code")
    autocomplete_fields = ("printer", "request", "user")
    date_hierarchy = "started_at"
    inlines = [PrintJobEventInline]


@admin.register(PrintBudget)
class PrintBudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "grams_per_month", "minutes_per_month", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__username",)
    autocomplete_fields = ("user",)


@admin.register(PrintBudgetLedger)
class PrintBudgetLedgerAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "period_month", "grams", "minutes", "reason", "created_at",
    )
    list_filter = ("reason", "period_month")
    search_fields = ("user__username", "note")
    autocomplete_fields = ("user", "request", "job", "recorded_by")
    date_hierarchy = "created_at"
