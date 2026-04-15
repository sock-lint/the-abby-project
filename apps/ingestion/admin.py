from django.contrib import admin

from .models import ProjectIngestionJob


@admin.register(ProjectIngestionJob)
class ProjectIngestionJobAdmin(admin.ModelAdmin):
    list_display = ["id", "source_type", "status", "created_by", "project", "created_at"]
    list_filter = ["status", "source_type"]
    readonly_fields = ["id", "created_at", "updated_at", "result_json", "error"]
    search_fields = ["source_url", "id"]
