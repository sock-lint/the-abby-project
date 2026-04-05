from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"projects", views.ProjectViewSet, basename="project")
router.register(r"categories", views.SkillCategoryViewSet, basename="category")

urlpatterns = [
    path("auth/", views.AuthView.as_view(), name="auth"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "projects/<int:project_pk>/milestones/",
        views.ProjectMilestoneViewSet.as_view({"get": "list", "post": "create"}),
        name="project-milestones",
    ),
    path(
        "projects/<int:project_pk>/milestones/<int:pk>/",
        views.ProjectMilestoneViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="project-milestone-detail",
    ),
    path(
        "projects/<int:project_pk>/milestones/<int:pk>/complete/",
        views.ProjectMilestoneViewSet.as_view({"post": "complete"}),
        name="project-milestone-complete",
    ),
    path(
        "projects/<int:project_pk>/materials/",
        views.MaterialItemViewSet.as_view({"get": "list", "post": "create"}),
        name="project-materials",
    ),
    path(
        "projects/<int:project_pk>/materials/<int:pk>/",
        views.MaterialItemViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="project-material-detail",
    ),
    path(
        "projects/<int:project_pk>/materials/<int:pk>/mark-purchased/",
        views.MaterialItemViewSet.as_view({"post": "mark_purchased"}),
        name="project-material-purchased",
    ),
    path("", include(router.urls)),
]
