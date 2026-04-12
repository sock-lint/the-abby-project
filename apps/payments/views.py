from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import (
    RoleFilteredQuerySetMixin, get_child_or_404, child_not_found_response,
    resolve_target_user,
)

from .models import PaymentLedger
from .serializers import PaymentLedgerSerializer
from .services import PaymentService


class PaymentLedgerViewSet(RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentLedgerSerializer
    queryset = PaymentLedger.objects.all()

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())


class BalanceView(APIView):
    def get(self, request):
        target_user, err = resolve_target_user(request)
        if err:
            return err

        balance = PaymentService.get_balance(target_user)
        breakdown = PaymentService.get_breakdown(target_user)
        recent = PaymentLedger.objects.filter(user=target_user)[:10]

        return Response({
            "balance": float(balance),
            "breakdown": {k: float(v) for k, v in breakdown.items()},
            "recent_transactions": PaymentLedgerSerializer(recent, many=True).data,
        })


class PayoutView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        amount = request.data.get("amount")
        child, err = resolve_target_user(request, source="data")
        if err:
            return err
        if not amount:
            return Response(
                {"error": "user_id and amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entry = PaymentService.record_payout(child, amount, request.user)
        return Response(PaymentLedgerSerializer(entry).data, status=status.HTTP_201_CREATED)


class PaymentAdjustmentView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        from decimal import Decimal, InvalidOperation
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
        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, TypeError):
            return Response(
                {"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST
            )
        if amount == 0:
            return Response(
                {"error": "Amount must not be zero"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entry = PaymentService.record_entry(
            child, amount, PaymentLedger.EntryType.ADJUSTMENT,
            description=description, created_by=request.user,
        )
        return Response(
            PaymentLedgerSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )
