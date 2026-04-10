from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin, get_child_or_404, child_not_found_response

from .models import CoinLedger, Reward, RewardRedemption
from .serializers import (
    CoinLedgerSerializer, RewardRedemptionSerializer, RewardSerializer,
    RewardWriteSerializer,
)
from .services import (
    CoinService, InsufficientCoinsError, RewardService, RewardUnavailableError,
)


class RewardViewSet(viewsets.ModelViewSet):
    serializer_class = RewardSerializer

    def get_queryset(self):
        if self.request.user.role == "parent":
            return Reward.objects.all()
        return Reward.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return RewardWriteSerializer
        return RewardSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

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


class RewardRedemptionViewSet(RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = RewardRedemptionSerializer
    queryset = RewardRedemption.objects.select_related("reward", "user")

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def approve(self, request, pk=None):
        redemption = self.get_object()
        RewardService.approve(redemption, request.user, notes=request.data.get("notes", ""))
        return Response(RewardRedemptionSerializer(redemption).data)

    @action(detail=True, methods=["post"], permission_classes=[IsParent])
    def deny(self, request, pk=None):
        redemption = self.get_object()
        RewardService.deny(redemption, request.user, notes=request.data.get("notes", ""))
        return Response(RewardRedemptionSerializer(redemption).data)


class CoinBalanceView(APIView):
    def get(self, request):
        user = request.user
        target_user = user
        if user.role == "parent":
            child_id = request.query_params.get("user_id")
            if child_id:
                target_user = get_child_or_404(child_id)
                if target_user is None:
                    return child_not_found_response()

        balance = CoinService.get_balance(target_user)
        breakdown = CoinService.get_breakdown(target_user)
        recent = CoinLedger.objects.filter(user=target_user)[:10]
        return Response({
            "balance": balance,
            "breakdown": breakdown,
            "recent_transactions": CoinLedgerSerializer(recent, many=True).data,
        })


class CoinAdjustmentView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        child_id = request.data.get("user_id")
        amount = request.data.get("amount")
        description = request.data.get("description", "")
        if not child_id or amount is None:
            return Response(
                {"error": "user_id and amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        child = get_child_or_404(child_id)
        if child is None:
            return child_not_found_response()
        amount = int(amount)
        if amount == 0:
            return Response(
                {"error": "Amount must not be zero"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount < 0:
            balance = CoinService.get_balance(child)
            if balance + amount < 0:
                return Response(
                    {"error": f"Insufficient coins ({balance} available)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        entry = CoinService.award_coins(
            child, amount, CoinLedger.Reason.ADJUSTMENT,
            description=description, created_by=request.user,
        )
        return Response(
            CoinLedgerSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )
