from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .greenlight_views import (
    GreenlightOverviewView, GreenlightPayoutView, GreenlightPreviewView,
    GreenlightReconcileView, GreenlightSnapshotView,
)

router = DefaultRouter()
router.register(r"payments", views.PaymentLedgerViewSet, basename="payment")

urlpatterns = [
    path("payments/greenlight/overview/", GreenlightOverviewView.as_view(), name="greenlight-overview"),
    path("payments/greenlight/payout/", GreenlightPayoutView.as_view(), name="greenlight-payout"),
    path("payments/greenlight/snapshot/", GreenlightSnapshotView.as_view(), name="greenlight-snapshot"),
    path("payments/greenlight/preview/", GreenlightPreviewView.as_view(), name="greenlight-preview"),
    path("payments/greenlight/reconcile/", GreenlightReconcileView.as_view(), name="greenlight-reconcile"),
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("payments/payout/", views.PayoutView.as_view(), name="payout"),
    path("payments/adjust/", views.PaymentAdjustmentView.as_view(), name="payment-adjust"),
    path("", include(router.urls)),
]
