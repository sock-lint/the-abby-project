from django.contrib import admin

from .models import Chore, ChoreCompletion


@admin.register(Chore)
class ChoreAdmin(admin.ModelAdmin):
    list_display = ["title", "icon", "reward_amount", "coin_reward", "recurrence", "week_schedule", "assigned_to", "is_active"]
    list_filter = ["recurrence", "week_schedule", "is_active"]
    search_fields = ["title"]


@admin.register(ChoreCompletion)
class ChoreCompletionAdmin(admin.ModelAdmin):
    list_display = ["chore", "user", "completed_date", "status", "reward_amount_snapshot", "created_at"]
    list_filter = ["status", "completed_date"]
    search_fields = ["chore__title", "user__username"]
