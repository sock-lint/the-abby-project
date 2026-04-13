from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"homework", views.HomeworkAssignmentViewSet, basename="homework-assignment")
router.register(r"homework-submissions", views.HomeworkSubmissionViewSet, basename="homework-submission")
router.register(r"homework-templates", views.HomeworkTemplateViewSet, basename="homework-template")

urlpatterns = [
    path("homework/dashboard/", views.HomeworkDashboardView.as_view(), name="homework-dashboard"),
    path("", include(router.urls)),
]
