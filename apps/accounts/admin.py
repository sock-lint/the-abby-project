from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


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
