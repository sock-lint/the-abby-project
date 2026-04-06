from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"time-entries", views.TimeEntryViewSet, basename="time-entry")
router.register(r"timecards", views.TimecardViewSet, basename="timecard")

urlpatterns = [
    path("clock/", views.ClockView.as_view(), name="clock"),
    path("export/timecards/", views.ExportTimecardsView.as_view(), name="export-timecards"),
    path("export/time-entries/", views.ExportTimeEntriesView.as_view(), name="export-time-entries"),
    path("", include(router.urls)),
]
