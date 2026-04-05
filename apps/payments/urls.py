from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"payments", views.PaymentLedgerViewSet, basename="payment")

urlpatterns = [
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("payments/payout/", views.PayoutView.as_view(), name="payout"),
    path("", include(router.urls)),
]
