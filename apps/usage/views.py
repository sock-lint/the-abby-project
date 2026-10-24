from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsStaffParent

from .models import UsageEvent
from .reporting import build_usage_report
from .services import record_visit


class UsageVisitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not isinstance(request.data, dict) or request.data:
            raise ValidationError({"error": "Send an empty object."})
        record_visit(request.user)
        return Response(status=204)


class UsageDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsStaffParent]

    def get(self, request):
        if set(request.query_params) - {"scope", "days", "role", "feature", "_abby_session", "_abby_retry"}:
            raise ValidationError({"error": "Unsupported usage filter."})
        scope = request.query_params.get("scope", "family")
        role = request.query_params.get("role", "all")
        feature = request.query_params.get("feature", "all")
        try:
            days = int(request.query_params.get("days", "28"))
        except (ValueError, TypeError):
            raise ValidationError({"days": "Choose 7, 28 or 90 days."}) from None
        if days not in {7, 28, 90}:
            raise ValidationError({"days": "Choose 7, 28 or 90 days."})
        if scope not in {"family", "deployment"}:
            raise ValidationError({"scope": "Choose family or deployment."})
        if role not in {"all", "parent", "child"}:
            raise ValidationError({"role": "Choose all, parent or child."})
        if feature not in {"all", *UsageEvent.Feature.values}:
            raise ValidationError({"feature": "Choose a supported feature."})
        if scope == "deployment" and not request.user.is_superuser:
            raise PermissionDenied("Deployment usage is restricted to superusers.")
        return Response(build_usage_report(request.user, scope=scope, days=days, role=role, feature=feature))
