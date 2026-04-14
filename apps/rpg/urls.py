from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"habits", views.HabitViewSet, basename="habit")

urlpatterns = [
    path("character/", views.CharacterView.as_view(), name="character"),
    path("streaks/", views.StreakView.as_view(), name="streaks"),
    path("", include(router.urls)),
]
