from django.contrib import admin

from .models import Quest, QuestDefinition, QuestParticipant, QuestRewardItem


class QuestRewardItemInline(admin.TabularInline):
    model = QuestRewardItem
    extra = 1


@admin.register(QuestDefinition)
class QuestDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "quest_type",
        "target_value",
        "duration_days",
        "coin_reward",
        "is_system",
    )
    list_filter = ("quest_type", "is_system")
    inlines = [QuestRewardItemInline]


@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    list_display = (
        "definition",
        "status",
        "current_progress",
        "start_date",
        "end_date",
    )
    list_filter = ("status",)


@admin.register(QuestParticipant)
class QuestParticipantAdmin(admin.ModelAdmin):
    list_display = ("quest", "user", "contribution")
