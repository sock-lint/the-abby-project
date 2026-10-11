"""Family-scoped reads and parent-only local Greenlight bookkeeping writes."""
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import child_not_found_response, get_child_or_404
from .greenlight import confirm_transfer, overview, payout_data, preview_statement, reconcile_statement
from .models import GreenlightBalanceSnapshot
from .serializers import (
    GreenlightBalanceSnapshotSerializer, GreenlightPayoutSerializer,
    GreenlightPreviewSerializer, GreenlightReconcileSerializer,
    GreenlightSnapshotInputSerializer, GreenlightTargetSerializer,
)


def target(request, data):
    child = get_child_or_404(data["user_id"], requesting_user=request.user)
    return child


class GreenlightOverviewView(APIView):
    def get(self, request):
        if request.user.role == "child":
            if request.query_params.get("user_id") and request.query_params["user_id"] != str(request.user.pk):
                return child_not_found_response()
            child = request.user
        else:
            serializer = GreenlightTargetSerializer(data=request.query_params)
            serializer.is_valid(raise_exception=True)
            child = target(request, serializer.validated_data)
            if child is None:
                return child_not_found_response()
        return Response(overview(child))


class GreenlightPayoutView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        serializer = GreenlightPayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        child = target(request, data)
        if child is None:
            return child_not_found_response()
        data.pop("user_id")
        transfer, created = confirm_transfer(child, request.user, **data)
        return Response({"created": created, "payout": payout_data(transfer.payment_entry)}, status=201 if created else 200)


class GreenlightSnapshotView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        serializer = GreenlightSnapshotInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        child = target(request, data)
        if child is None:
            return child_not_found_response()
        data.pop("user_id")
        snapshot = GreenlightBalanceSnapshot.objects.create(user=child, created_by=request.user, **data)
        return Response(GreenlightBalanceSnapshotSerializer(snapshot).data, status=201)


class GreenlightPreviewView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        serializer = GreenlightPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        child = target(request, serializer.validated_data)
        if child is None:
            return child_not_found_response()
        return Response(preview_statement(child, serializer.validated_data["csv_data"]))


class GreenlightReconcileView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        serializer = GreenlightReconcileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        child = target(request, data)
        if child is None:
            return child_not_found_response()
        return Response(reconcile_statement(child, request.user, data["csv_data"], data["selections"]))
