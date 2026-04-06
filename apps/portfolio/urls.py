from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"photos", views.ProjectPhotoViewSet, basename="photo")

urlpatterns = [
    path("portfolio/", views.PortfolioView.as_view(), name="portfolio"),
    path("export/portfolio/", views.ExportPortfolioView.as_view(), name="export-portfolio"),
    path("", include(router.urls)),
]
