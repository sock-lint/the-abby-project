from django.urls import path
from . import views

urlpatterns = [
    path("quests/active/", views.ActiveQuestView.as_view(), name="quest-active"),
    path("quests/available/", views.AvailableQuestsView.as_view(), name="quest-available"),
    path("quests/start/", views.StartQuestView.as_view(), name="quest-start"),
    path("quests/history/", views.QuestHistoryView.as_view(), name="quest-history"),
    path("quests/catalog/", views.QuestCatalogView.as_view(), name="quest-catalog"),
    path("quests/", views.CreateQuestView.as_view(), name="quest-create"),
    path("quests/<int:pk>/assign/", views.AssignQuestView.as_view(), name="quest-assign"),
]
