from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CoinAdjustmentView, CoinBalanceView, ExchangeRateView, ExchangeRequestView,
    ExchangeRequestViewSet, RewardRedemptionViewSet, RewardViewSet,
)

router = DefaultRouter()
router.register(r"rewards", RewardViewSet, basename="reward")
router.register(r"redemptions", RewardRedemptionViewSet, basename="redemption")

# Wire ExchangeRequestViewSet to the legacy URL shape used by the frontend:
# - GET  /coins/exchange/list/       → list
# - POST /coins/exchange/<pk>/approve/ → approve action
# - POST /coins/exchange/<pk>/reject/  → reject action
exchange_list = ExchangeRequestViewSet.as_view({"get": "list"})
exchange_approve = ExchangeRequestViewSet.as_view({"post": "approve"})
exchange_reject = ExchangeRequestViewSet.as_view({"post": "reject"})

urlpatterns = [
    path("", include(router.urls)),
    path("coins/", CoinBalanceView.as_view(), name="coin-balance"),
    path("coins/adjust/", CoinAdjustmentView.as_view(), name="coin-adjust"),
    path("coins/exchange/", ExchangeRequestView.as_view(), name="coin-exchange"),
    path("coins/exchange/rate/", ExchangeRateView.as_view(), name="exchange-rate"),
    path("coins/exchange/list/", exchange_list, name="exchange-list"),
    path("coins/exchange/<int:pk>/approve/", exchange_approve, name="exchange-approve"),
    path("coins/exchange/<int:pk>/reject/", exchange_reject, name="exchange-reject"),
]
