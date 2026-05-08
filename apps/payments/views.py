import csv

from datetime import date

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import (
    RoleFilteredQuerySetMixin, resolve_target_user,
)

from .models import PaymentLedger
from .serializers import PaymentLedgerSerializer
from .services import PaymentService


class PaymentLedgerViewSet(RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """List + retrieve PaymentLedger rows.

    Supports filter query params on list/export:
    - ``entry_type`` — one or more (comma-separated) values from
      ``PaymentLedger.EntryType``. Unknown types are silently dropped.
    - ``start_date`` / ``end_date`` — inclusive YYYY-MM-DD bounds on
      ``created_at::date``. Either / both / neither.
    - ``user_id`` — parent-only; defaults to all of the parent's
      family's children combined when omitted.
    """

    serializer_class = PaymentLedgerSerializer
    queryset = PaymentLedger.objects.all()

    def get_queryset(self):
        qs = self.get_role_filtered_queryset(super().get_queryset())
        return self._apply_filters(qs)

    def _apply_filters(self, qs):
        params = self.request.query_params

        entry_types = params.get("entry_type")
        if entry_types:
            valid = {choice for choice, _ in PaymentLedger.EntryType.choices}
            requested = {t.strip() for t in entry_types.split(",") if t.strip()}
            picked = requested & valid
            if picked:
                qs = qs.filter(entry_type__in=picked)

        start_date = _parse_iso_date(params.get("start_date"))
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        end_date = _parse_iso_date(params.get("end_date"))
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        # Parent-only narrowing to a specific child. Children already see
        # only their own rows via RoleFilteredQuerySetMixin, so the param
        # is meaningful only when the caller is a parent.
        if self.request.user.role == "parent":
            user_id = params.get("user_id")
            if user_id:
                qs = qs.filter(user_id=user_id)

        return qs

    @action(detail=False, methods=["get"], permission_classes=[IsParent])
    def export(self, request):
        """Stream the filtered ledger as a CSV.

        Mirrors the `Timecards` CSV export — parent-only, RFC 4180-ish
        encoding, columns chosen for direct paste into a spreadsheet so
        the parent doesn't have to reformat for taxes / allowance
        reconciliation.
        """
        qs = self.get_queryset().select_related("user")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="payment-ledger.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([
            "created_at", "user", "entry_type", "amount",
            "description", "id",
        ])
        for entry in qs.order_by("created_at"):
            writer.writerow([
                entry.created_at.isoformat(),
                getattr(entry.user, "username", entry.user_id),
                entry.entry_type,
                f"{entry.amount}",
                entry.description or "",
                entry.id,
            ])
        return response


def _parse_iso_date(raw):
    """Permissive YYYY-MM-DD → date; None on missing or malformed input.

    Silent drop is deliberate: a bad date filter shouldn't 500 a list view
    that's trying to render the parent dashboard. The user just sees the
    unfiltered ledger and notices their filter was ignored.
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


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
