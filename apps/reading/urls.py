from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ReadingBookViewSet, ReadingRecommendationsView, ReadingSessionViewSet, ReadingSummaryView

router = DefaultRouter()
router.register("reading-books", ReadingBookViewSet, basename="reading-book")
router.register("reading-sessions", ReadingSessionViewSet, basename="reading-session")

urlpatterns = [
    path("reading/summary/", ReadingSummaryView.as_view(), name="reading-summary"),
    path("reading/recommendations/", ReadingRecommendationsView.as_view(), name="reading-recommendations"),
    path("", include(router.urls)),
]
