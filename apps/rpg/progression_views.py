"""Staff-only, anonymous design calculations over the global game catalog."""
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from config.permissions import IsStaffParent

from .progression import describe_progression, normalize_config, simulate_progression
from .progression.challenge_gates import GateReferenceError


class ProgressionSimulationThrottle(UserRateThrottle):
    scope = "progression_lab"
    rate = "10/min"


class ProgressionCatalogUnavailable(APIException):
    status_code = 503
    default_code = "progression_catalog_unavailable"


class ProgressionScenarioSerializer(serializers.Serializer):
    """Share the engine's strict, bounded validation across all callers."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise ValidationError({"detail": "Supply an anonymous scenario object."})
        try:
            return normalize_config(data)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


class _ProgressionLabView(APIView):
    permission_classes = [IsAuthenticated, IsStaffParent]

    @staticmethod
    def reject_query_targeting(request):
        # The shared browser client partitions private GET caches and retries
        # upstream HTML responses with these transport-only markers. Neither
        # selects a household or changes the anonymous scenario.
        transport_keys = {"_abby_session", "_abby_retry"}
        if set(request.query_params) - transport_keys:
            raise ValidationError({"detail": "Progression Lab accepts no account or query selectors."})


class ProgressionLabView(_ProgressionLabView):
    def get(self, request):
        self.reject_query_targeting(request)
        try:
            return Response(describe_progression())
        except ValueError as exc:
            raise ProgressionCatalogUnavailable(str(exc)) from exc


class ProgressionSimulationView(_ProgressionLabView):
    throttle_classes = [ProgressionSimulationThrottle]

    def post(self, request):
        self.reject_query_targeting(request)
        scenario = ProgressionScenarioSerializer(data=request.data)
        scenario.is_valid(raise_exception=True)
        try:
            return Response(simulate_progression(scenario.validated_data))
        except GateReferenceError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except ValueError as exc:
            raise ProgressionCatalogUnavailable(str(exc)) from exc
