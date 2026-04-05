from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"photos", views.ProjectPhotoViewSet, basename="photo")

urlpatterns = [
    path("portfolio/", views.PortfolioView.as_view(), name="portfolio"),
    path("", include(router.urls)),
]
