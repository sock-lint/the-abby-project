from django.contrib import admin

from .models import CharacterProfile


@admin.register(CharacterProfile)
class CharacterProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "level", "login_streak", "longest_login_streak", "perfect_days_count", "last_active_date"]
    list_filter = ["level"]
