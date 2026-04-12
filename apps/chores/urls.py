from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"chores", views.ChoreViewSet, basename="chore")
router.register(r"chore-completions", views.ChoreCompletionViewSet, basename="chore-completion")

urlpatterns = [
    path("", include(router.urls)),
]
