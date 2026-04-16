from django.contrib import admin

from .models import Habit, HabitLog


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "habit_type", "user", "xp_reward", "max_taps_per_day", "strength", "is_active"]
    list_filter = ["habit_type", "is_active"]
    search_fields = ["name"]


@admin.register(HabitLog)
class HabitLogAdmin(admin.ModelAdmin):
    list_display = ["habit", "user", "direction", "streak_at_time", "created_at"]
    list_filter = ["direction"]
