from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"categories", views.SkillCategoryViewSet, basename="category")
router.register(r"badges", views.BadgeViewSet, basename="badge")
router.register(r"badges/earned", views.UserBadgeViewSet, basename="user-badge")
router.register(r"subjects", views.SubjectViewSet, basename="subject")
router.register(r"skills", views.SkillViewSet, basename="skill")
router.register(r"skill-progress", views.SkillProgressViewSet, basename="skill-progress")

urlpatterns = [
    path("skills/tree/<int:category_id>/", views.SkillTreeView.as_view(), name="skill-tree"),
    path("achievements/summary/", views.AchievementsSummaryView.as_view(), name="achievements-summary"),
    path("", include(router.urls)),
]
