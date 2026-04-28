from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import (
    ApprovalActionMixin, ParentWritePermissionMixin,
    RoleFilteredQuerySetMixin, WriteReadSerializerMixin, resolve_target_user,
)

from django.conf import settings as django_settings

from .models import CoinLedger, ExchangeRequest, Reward, RewardRedemption
from .serializers import (
    CoinLedgerSerializer, ExchangeRequestSerializer,
    RewardRedemptionSerializer, RewardSerializer, RewardWriteSerializer,
)
from .services import (
    CoinService, ExchangeService, InsufficientCoinsError,
    InsufficientFundsError, RewardService, RewardUnavailableError,
)


class RewardViewSet(WriteReadSerializerMixin, ParentWritePermissionMixin, viewsets.ModelViewSet):
    serializer_class = RewardSerializer
    write_serializer_class = RewardWriteSerializer

    def get_queryset(self):
        family = getattr(self.request.user, "family", None)
        if family is None:
            return Reward.objects.none()
        if self.request.user.role == "parent":
            return Reward.objects.filter(family=family)
        return Reward.objects.filter(family=family, is_active=True)

    def perform_create(self, serializer):
        serializer.save(family=self.request.user.family)

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


class RewardRedemptionViewSet(
    ApprovalActionMixin, RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet,
):
    serializer_class = RewardRedemptionSerializer
    queryset = RewardRedemption.objects.select_related("reward", "user")
    approval_service = RewardService

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())


class CoinBalanceView(APIView):
    def get(self, request):
        target_user, err = resolve_target_user(request)
        if err:
            return err

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
        amount = request.data.get("amount")
        description = request.data.get("description", "")
        child, err = resolve_target_user(request, source="data")
        if err:
            return err
        if amount is None:
            return Response(
                {"error": "user_id and amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
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


class ExchangeRateView(APIView):
    def get(self, request):
        return Response({"coins_per_dollar": django_settings.COINS_PER_DOLLAR})


class ExchangeRequestView(APIView):
    def post(self, request):
        dollar_amount = request.data.get("dollar_amount")
        if dollar_amount is None:
            return Response(
                {"error": "dollar_amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            exchange = ExchangeService.request_exchange(
                request.user, dollar_amount,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )
        except InsufficientFundsError as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            ExchangeRequestSerializer(exchange).data,
            status=status.HTTP_201_CREATED,
        )


class ExchangeRequestViewSet(
    ApprovalActionMixin, RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet,
):
    """List exchange requests (role-filtered) plus parent approve/reject.

    Creation still happens through :class:`ExchangeRequestView` because the
    POST body and error translation (``InsufficientFundsError`` → 400) are
    distinctly child-facing and don't fit the generic viewset pattern.
    """

    serializer_class = ExchangeRequestSerializer
    queryset = ExchangeRequest.objects.select_related("user")
    approval_service = ExchangeService

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    def handle_exception(self, exc):
        if isinstance(exc, InsufficientFundsError):
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
