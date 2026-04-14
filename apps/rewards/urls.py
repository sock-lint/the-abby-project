from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CoinAdjustmentView, CoinBalanceView, ExchangeApprovalView,
    ExchangeRateView, ExchangeRequestListView, ExchangeRequestView,
    RewardRedemptionViewSet, RewardViewSet,
)

router = DefaultRouter()
router.register(r"rewards", RewardViewSet, basename="reward")
router.register(r"redemptions", RewardRedemptionViewSet, basename="redemption")

urlpatterns = [
    path("", include(router.urls)),
    path("coins/", CoinBalanceView.as_view(), name="coin-balance"),
    path("coins/adjust/", CoinAdjustmentView.as_view(), name="coin-adjust"),
    path("coins/exchange/", ExchangeRequestView.as_view(), name="coin-exchange"),
    path("coins/exchange/rate/", ExchangeRateView.as_view(), name="exchange-rate"),
    path("coins/exchange/list/", ExchangeRequestListView.as_view(), name="exchange-list"),
    path("coins/exchange/<int:pk>/approve/", ExchangeApprovalView.as_view(), {"action": "approve"}, name="exchange-approve"),
    path("coins/exchange/<int:pk>/reject/", ExchangeApprovalView.as_view(), {"action": "reject"}, name="exchange-reject"),
]
