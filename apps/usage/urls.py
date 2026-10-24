from django.urls import path

from .views import UsageDashboardView, UsageVisitView

urlpatterns = [
    path("usage/visit/", UsageVisitView.as_view(), name="usage-visit"),
    path("admin/usage/", UsageDashboardView.as_view(), name="usage-dashboard"),
]
