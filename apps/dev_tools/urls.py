"""URL config for ``/api/dev/*`` — included from ``config/urls.py``
only when ``apps.dev_tools.gate.is_enabled()`` returns True at startup.
The view-level permission re-checks the gate so toggling
``DEV_TOOLS_ENABLED`` mid-process still locks down endpoints.
"""
from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("ping/", views.PingView.as_view()),
    path("children/", views.ChildSelectView.as_view()),
    path("rewards/", views.RewardSelectView.as_view()),
    path("items/", views.ItemSelectView.as_view()),
    path("pet-species/", views.PetSpeciesSelectView.as_view()),
    path("potion-types/", views.PotionTypeSelectView.as_view()),
    path("checklist/", views.ChecklistView.as_view()),
    path("force-drop/", views.ForceDropView.as_view()),
    path("force-celebration/", views.ForceCelebrationView.as_view()),
    path("set-streak/", views.SetStreakView.as_view()),
    path("set-reward-stock/", views.SetRewardStockView.as_view()),
    path("expire-journal/", views.ExpireJournalView.as_view()),
    path("tick-perfect-day/", views.TickPerfectDayView.as_view()),
    path("set-pet-happiness/", views.SetPetHappinessView.as_view()),
    path("reset-day-counters/", views.ResetDayCountersView.as_view()),
    path("force-approval-notification/", views.ForceApprovalNotificationView.as_view()),
    path("force-quest-progress/", views.ForceQuestProgressView.as_view()),
    path("mark-daily-challenge-ready/", views.MarkDailyChallengeReadyView.as_view()),
    path("set-pet-growth/", views.SetPetGrowthView.as_view()),
    path("grant-hatch-ingredients/", views.GrantHatchIngredientsView.as_view()),
    path("clear-breed-cooldowns/", views.ClearBreedCooldownsView.as_view()),
    path("seed-companion-growth/", views.SeedCompanionGrowthView.as_view()),
    path("mark-expedition-ready/", views.MarkExpeditionReadyView.as_view()),
]
