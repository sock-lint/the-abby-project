from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
# NOTE: register the ingest viewset BEFORE projects/ so its routes match first
# (otherwise `/projects/ingest/` would be resolved as project detail with pk=ingest).
router.register(r"projects/ingest", views.ProjectIngestViewSet, basename="project-ingest")
router.register(r"projects", views.ProjectViewSet, basename="project")
router.register(r"categories", views.SkillCategoryViewSet, basename="category")
router.register(r"notifications", views.NotificationViewSet, basename="notification")
router.register(r"templates", views.ProjectTemplateViewSet, basename="template")
router.register(r"children", views.ChildViewSet, basename="child")
router.register(r"savings-goals", views.SavingsGoalViewSet, basename="savings-goal")

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
    path(
        "projects/<int:project_pk>/steps/",
        views.ProjectStepViewSet.as_view({"get": "list", "post": "create"}),
        name="project-steps",
    ),
    path(
        "projects/<int:project_pk>/steps/reorder/",
        views.ProjectStepViewSet.as_view({"post": "reorder"}),
        name="project-steps-reorder",
    ),
    path(
        "projects/<int:project_pk>/steps/<int:pk>/",
        views.ProjectStepViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="project-step-detail",
    ),
    path(
        "projects/<int:project_pk>/steps/<int:pk>/complete/",
        views.ProjectStepViewSet.as_view({"post": "complete"}),
        name="project-step-complete",
    ),
    path(
        "projects/<int:project_pk>/steps/<int:pk>/uncomplete/",
        views.ProjectStepViewSet.as_view({"post": "uncomplete"}),
        name="project-step-uncomplete",
    ),
    path(
        "projects/<int:project_pk>/resources/",
        views.ProjectResourceViewSet.as_view({"get": "list", "post": "create"}),
        name="project-resources",
    ),
    path(
        "projects/<int:project_pk>/resources/<int:pk>/",
        views.ProjectResourceViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="project-resource-detail",
    ),
    path("instructables/preview/", views.InstructablesPreviewView.as_view(), name="instructables-preview"),
    path("projects/suggestions/", views.ProjectSuggestionsView.as_view(), name="project-suggestions"),
    path("projects/<int:pk>/qr/", views.ProjectQRCodeView.as_view(), name="project-qr"),
    path(
        "projects/<int:project_pk>/collaborators/",
        views.ProjectCollaboratorViewSet.as_view({"get": "list", "post": "create"}),
        name="project-collaborators",
    ),
    path(
        "projects/<int:project_pk>/collaborators/<int:pk>/",
        views.ProjectCollaboratorViewSet.as_view({"delete": "destroy"}),
        name="project-collaborator-detail",
    ),
    path("greenlight/import/", views.GreenlightImportView.as_view(), name="greenlight-import"),
    path("", include(router.urls)),
]
