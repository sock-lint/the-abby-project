from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"movement-types", views.MovementTypeViewSet, basename="movement-type")
router.register(r"movement-sessions", views.MovementSessionViewSet, basename="movement-session")

urlpatterns = [
    path("", include(router.urls)),
]
