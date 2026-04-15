from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
# Registered under ``projects/ingest`` so the frontend URL
# ``/api/projects/ingest/`` continues to resolve unchanged after the
# extraction. Kept BEFORE any sibling ``projects/`` router in include
# order so its routes match first.
router.register(r"projects/ingest", views.ProjectIngestViewSet, basename="project-ingest")

urlpatterns = [
    path("", include(router.urls)),
]
