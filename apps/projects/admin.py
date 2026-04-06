from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import MaterialItem, Notification, Project, ProjectMilestone, SkillCategory, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "display_name", "role", "hourly_rate", "is_active"]
    list_filter = ["role", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("SummerForge", {"fields": ("role", "hourly_rate", "display_name", "avatar")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("SummerForge", {"fields": ("role", "hourly_rate", "display_name")}),
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


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "title", "notification_type", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read"]
