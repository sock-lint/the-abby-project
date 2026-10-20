from django.urls import path
from . import views
from . import goal_views

urlpatterns = [
    path("challenges/", goal_views.ChallengesView.as_view(), name="challenges"),
    path("challenges/goals/", goal_views.CreateGoalView.as_view(), name="challenge-create"),
    path("challenges/discovery/", goal_views.ChallengeDiscoveryView.as_view(), name="challenge-discovery"),
    path("challenges/voyager-feedback/", goal_views.VoyagerFeedbackView.as_view(), name="voyager-feedback"),
    path("challenges/<str:goal_id>/opened/", goal_views.ChallengeOpenedView.as_view(), name="challenge-opened"),
    path("challenges/<str:goal_id>/pin/", goal_views.ChallengePinView.as_view(), name="challenge-pin"),
    path("quests/active/", views.ActiveQuestView.as_view(), name="quest-active"),
    path("quests/available/", views.AvailableQuestsView.as_view(), name="quest-available"),
    path("quests/start/", views.StartQuestView.as_view(), name="quest-start"),
    path("quests/history/", views.QuestHistoryView.as_view(), name="quest-history"),
    path("quests/catalog/", views.QuestCatalogView.as_view(), name="quest-catalog"),
    path("quests/family/", views.FamilyActiveQuestsView.as_view(), name="quest-family"),
    path("quests/", views.CreateQuestView.as_view(), name="quest-create"),
    path("quests/<int:pk>/assign/", views.AssignQuestView.as_view(), name="quest-assign"),
    path("quests/<int:pk>/co-op/", views.StartCoOpQuestView.as_view(), name="quest-coop-start"),
    path("challenges/daily/", views.DailyChallengeView.as_view(), name="daily-challenge"),
    path("challenges/daily/claim/", views.ClaimDailyChallengeView.as_view(), name="daily-challenge-claim"),
]
