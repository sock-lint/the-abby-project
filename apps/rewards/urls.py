from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CoinAdjustmentView, CoinBalanceView, RewardRedemptionViewSet, RewardViewSet

router = DefaultRouter()
router.register(r"rewards", RewardViewSet, basename="reward")
router.register(r"redemptions", RewardRedemptionViewSet, basename="redemption")

urlpatterns = [
    path("", include(router.urls)),
    path("coins/", CoinBalanceView.as_view(), name="coin-balance"),
    path("coins/adjust/", CoinAdjustmentView.as_view(), name="coin-adjust"),
]
