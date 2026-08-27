from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"print-requests", views.PrintRequestViewSet, basename="print-request")
router.register(r"print-jobs", views.PrintJobViewSet, basename="print-job")
router.register(r"print-budgets", views.PrintBudgetViewSet, basename="print-budget")
router.register(r"printers", views.PrinterProfileViewSet, basename="printer")

urlpatterns = [
    path("", include(router.urls)),
]
