from django.contrib import admin

from .models import (
    Badge, MilestoneSkillTag, ProjectSkillTag, Skill,
    SkillPrerequisite, SkillProgress, Subject, UserBadge,
)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "category", "order"]
    list_filter = ["category"]
    search_fields = ["name"]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "category", "subject", "is_locked_by_default", "order"]
    list_filter = ["category", "subject", "is_locked_by_default"]
    search_fields = ["name"]


@admin.register(SkillPrerequisite)
class SkillPrerequisiteAdmin(admin.ModelAdmin):
    list_display = ["skill", "required_skill", "required_level"]


@admin.register(SkillProgress)
class SkillProgressAdmin(admin.ModelAdmin):
    list_display = ["user", "skill", "xp_points", "level", "unlocked"]
    list_filter = ["level", "unlocked"]


@admin.register(ProjectSkillTag)
class ProjectSkillTagAdmin(admin.ModelAdmin):
    list_display = ["project", "skill", "xp_weight"]


@admin.register(MilestoneSkillTag)
class MilestoneSkillTagAdmin(admin.ModelAdmin):
    list_display = ["milestone", "skill", "xp_amount"]


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "subject", "criteria_type", "rarity", "xp_bonus"]
    list_filter = ["rarity", "criteria_type", "subject"]
    search_fields = ["name"]


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ["user", "badge", "earned_at"]
    list_filter = ["badge"]
