from django.urls import path

from .views import WellbeingGratitudeView, WellbeingTodayView


urlpatterns = [
    path("wellbeing/today/", WellbeingTodayView.as_view(), name="wellbeing-today"),
    path(
        "wellbeing/today/gratitude/",
        WellbeingGratitudeView.as_view(),
        name="wellbeing-gratitude",
    ),
]
