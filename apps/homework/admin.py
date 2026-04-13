from django.contrib import admin

from .models import (
    HomeworkAssignment,
    HomeworkProof,
    HomeworkSkillTag,
    HomeworkSubmission,
    HomeworkTemplate,
)


class HomeworkSkillTagInline(admin.TabularInline):
    model = HomeworkSkillTag
    extra = 0


class HomeworkProofInline(admin.TabularInline):
    model = HomeworkProof
    extra = 0


@admin.register(HomeworkAssignment)
class HomeworkAssignmentAdmin(admin.ModelAdmin):
    list_display = ["title", "subject", "effort_level", "due_date", "assigned_to", "is_active"]
    list_filter = ["subject", "effort_level", "is_active"]
    search_fields = ["title"]
    inlines = [HomeworkSkillTagInline]


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ["assignment", "user", "status", "timeliness", "created_at"]
    list_filter = ["status", "timeliness"]
    inlines = [HomeworkProofInline]


@admin.register(HomeworkTemplate)
class HomeworkTemplateAdmin(admin.ModelAdmin):
    list_display = ["title", "subject", "effort_level", "created_by"]
    list_filter = ["subject"]
