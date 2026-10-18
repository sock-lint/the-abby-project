from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ReadingBookViewSet, ReadingRecommendationsView, ReadingSessionViewSet, ReadingSummaryView
from .discovery_views import ReadingDiscoveryFeedbackView, ReadingFamilySuggestionViewSet

router = DefaultRouter()
router.register("reading-books", ReadingBookViewSet, basename="reading-book")
router.register("reading-sessions", ReadingSessionViewSet, basename="reading-session")
router.register("reading-family-suggestions", ReadingFamilySuggestionViewSet, basename="reading-family-suggestion")

urlpatterns = [
    path("reading/summary/", ReadingSummaryView.as_view(), name="reading-summary"),
    path("reading/recommendations/", ReadingRecommendationsView.as_view(), name="reading-recommendations"),
    path("reading/discovery-feedback/", ReadingDiscoveryFeedbackView.as_view(), name="reading-discovery-feedback"),
    path("", include(router.urls)),
]
