from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PaymentLedger
from .serializers import PaymentLedgerSerializer
from .services import PaymentService


class PaymentLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentLedgerSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return PaymentLedger.objects.all()
        return PaymentLedger.objects.filter(user=user)


class BalanceView(APIView):
    def get(self, request):
        user = request.user
        target_user = user
        if user.role == "parent":
            child_id = request.query_params.get("user_id")
            if child_id:
                from apps.projects.models import User
                try:
                    target_user = User.objects.get(id=child_id, role="child")
                except User.DoesNotExist:
                    return Response(
                        {"error": "Child not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

        balance = PaymentService.get_balance(target_user)
        breakdown = PaymentService.get_breakdown(target_user)
        recent = PaymentLedger.objects.filter(user=target_user)[:10]

        return Response({
            "balance": float(balance),
            "breakdown": {k: float(v) for k, v in breakdown.items()},
            "recent_transactions": PaymentLedgerSerializer(recent, many=True).data,
        })


class PayoutView(APIView):
    def post(self, request):
        if request.user.role != "parent":
            return Response(
                {"error": "Parents only"}, status=status.HTTP_403_FORBIDDEN
            )
        child_id = request.data.get("user_id")
        amount = request.data.get("amount")
        if not child_id or not amount:
            return Response(
                {"error": "user_id and amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from apps.projects.models import User
        try:
            child = User.objects.get(id=child_id, role="child")
        except User.DoesNotExist:
            return Response(
                {"error": "Child not found"}, status=status.HTTP_404_NOT_FOUND
            )
        entry = PaymentService.record_payout(child, amount, request.user)
        return Response(PaymentLedgerSerializer(entry).data, status=status.HTTP_201_CREATED)
