from django.contrib import admin

from .models import CharacterProfile, Habit, HabitLog


@admin.register(CharacterProfile)
class CharacterProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "level", "login_streak", "longest_login_streak", "perfect_days_count", "last_active_date"]
    list_filter = ["level"]


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "habit_type", "user", "coin_reward", "xp_reward", "strength", "is_active"]
    list_filter = ["habit_type", "is_active"]
    search_fields = ["name"]


@admin.register(HabitLog)
class HabitLogAdmin(admin.ModelAdmin):
    list_display = ["habit", "user", "direction", "streak_at_time", "created_at"]
    list_filter = ["direction"]
