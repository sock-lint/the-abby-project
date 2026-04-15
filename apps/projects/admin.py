from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    MaterialItem, Project, ProjectCollaborator, ProjectMilestone,
    ProjectTemplate, SavingsGoal, SkillCategory, TemplateMaterial,
    TemplateMilestone, User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "display_name", "role", "hourly_rate", "is_active"]
    list_filter = ["role", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("The Abby Project", {"fields": ("role", "hourly_rate", "display_name", "avatar")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("The Abby Project", {"fields": ("role", "hourly_rate", "display_name")}),
    )


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "color"]
    search_fields = ["name"]


class ProjectMilestoneInline(admin.TabularInline):
    model = ProjectMilestone
    extra = 0


class MaterialItemInline(admin.TabularInline):
    model = MaterialItem
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = [
        "title", "assigned_to", "status", "difficulty", "bonus_amount", "created_at",
    ]
    list_filter = ["status", "difficulty", "category"]
    search_fields = ["title", "description"]
    inlines = [ProjectMilestoneInline, MaterialItemInline]


@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    list_display = ["title", "project", "order", "is_completed", "bonus_amount"]
    list_filter = ["is_completed"]


@admin.register(MaterialItem)
class MaterialItemAdmin(admin.ModelAdmin):
    list_display = ["name", "project", "estimated_cost", "actual_cost", "is_purchased", "reimbursed"]
    list_filter = ["is_purchased", "reimbursed"]


class TemplateMilestoneInline(admin.TabularInline):
    model = TemplateMilestone
    extra = 0


class TemplateMaterialInline(admin.TabularInline):
    model = TemplateMaterial
    extra = 0


@admin.register(ProjectTemplate)
class ProjectTemplateAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "difficulty", "is_public", "created_by", "created_at"]
    list_filter = ["is_public", "category", "difficulty"]
    search_fields = ["title"]
    inlines = [TemplateMilestoneInline, TemplateMaterialInline]


@admin.register(ProjectCollaborator)
class ProjectCollaboratorAdmin(admin.ModelAdmin):
    list_display = ["project", "user", "pay_split_percent", "joined_at"]


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ["user", "title", "target_amount", "current_amount", "is_completed"]
    list_filter = ["is_completed"]
