from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CoinLedger, Reward, RewardRedemption
from .serializers import (
    CoinLedgerSerializer, RewardRedemptionSerializer, RewardSerializer,
)
from .services import (
    CoinService, InsufficientCoinsError, RewardService, RewardUnavailableError,
)


def _is_parent(user):
    return getattr(user, "role", None) == "parent"


class RewardViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RewardSerializer
    queryset = Reward.objects.filter(is_active=True)

    @action(detail=True, methods=["post"])
    def redeem(self, request, pk=None):
        reward = self.get_object()
        try:
            redemption = RewardService.request_redemption(request.user, reward)
        except InsufficientCoinsError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RewardUnavailableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            RewardRedemptionSerializer(redemption).data,
            status=status.HTTP_201_CREATED,
        )


class RewardRedemptionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RewardRedemptionSerializer

    def get_queryset(self):
        qs = RewardRedemption.objects.select_related("reward", "user")
        if _is_parent(self.request.user):
            return qs
        return qs.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if not _is_parent(request.user):
            return Response({"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN)
        redemption = self.get_object()
        RewardService.approve(redemption, request.user, notes=request.data.get("notes", ""))
        return Response(RewardRedemptionSerializer(redemption).data)

    @action(detail=True, methods=["post"])
    def deny(self, request, pk=None):
        if not _is_parent(request.user):
            return Response({"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN)
        redemption = self.get_object()
        RewardService.deny(redemption, request.user, notes=request.data.get("notes", ""))
        return Response(RewardRedemptionSerializer(redemption).data)


class CoinBalanceView(APIView):
    def get(self, request):
        user = request.user
        target_user = user
        if _is_parent(user):
            child_id = request.query_params.get("user_id")
            if child_id:
                from apps.projects.models import User
                try:
                    target_user = User.objects.get(id=child_id, role="child")
                except User.DoesNotExist:
                    return Response(
                        {"error": "Child not found"}, status=status.HTTP_404_NOT_FOUND
                    )

        balance = CoinService.get_balance(target_user)
        breakdown = CoinService.get_breakdown(target_user)
        recent = CoinLedger.objects.filter(user=target_user)[:10]
        return Response({
            "balance": balance,
            "breakdown": breakdown,
            "recent_transactions": CoinLedgerSerializer(recent, many=True).data,
        })
