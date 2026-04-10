from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin, get_child_or_404, child_not_found_response

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
        user = request.user
        target_user = user
        if user.role == "parent":
            child_id = request.query_params.get("user_id")
            if child_id:
                target_user = get_child_or_404(child_id)
                if target_user is None:
                    return child_not_found_response()

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
        child_id = request.data.get("user_id")
        amount = request.data.get("amount")
        if not child_id or not amount:
            return Response(
                {"error": "user_id and amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        child = get_child_or_404(child_id)
        if child is None:
            return child_not_found_response()
        entry = PaymentService.record_payout(child, amount, request.user)
        return Response(PaymentLedgerSerializer(entry).data, status=status.HTTP_201_CREATED)
