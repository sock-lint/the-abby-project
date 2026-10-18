"""Staff-parent notebook; its decisions cannot publish or change rewards."""
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .progression.experiments import (
    ExperimentConflict, ExperimentNotFound, ExperimentUnavailable, capture_observation, compare_experiment, create_experiment,
    get_comparison, get_experiment, list_experiments, record_decision, save_experiment,
)
from .progression_views import ProgressionCatalogUnavailable, _ProgressionLabView


class _Conflict(APIException):
    status_code = 409
    default_code = "progression_experiment_conflict"


class ComparisonThrottle(UserRateThrottle):
    scope = "progression_comparison"
    rate = "5/min"


def _body(request, keys, *, optional=()):
    if (not isinstance(request.data, dict) or set(keys) - set(request.data)
            or set(request.data) - set(keys) - set(optional)):
        optional_text = f" Optional: {', '.join(optional)}." if optional else ""
        raise ValidationError({"detail": f"Supply exactly {', '.join(keys)}.{optional_text}"})
    return request.data


EXPERIMENT_FIELDS = ("name", "hypothesis", "config", "candidate_daily_coins", "targets")
OPTIONAL_EXPERIMENT_FIELDS = ("candidate_policy", "candidate_expedition_budget")


class _ExperimentView(_ProgressionLabView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.reject_query_targeting(request)

    def handle_exception(self, exc):
        if isinstance(exc, ExperimentConflict):
            exc = _Conflict({"detail": str(exc)})
        elif isinstance(exc, ExperimentNotFound):
            exc = NotFound({"detail": str(exc)})
        elif isinstance(exc, ExperimentUnavailable):
            exc = ProgressionCatalogUnavailable({"detail": str(exc)})
        elif isinstance(exc, ValueError):
            exc = ValidationError({"detail": str(exc)})
        return super().handle_exception(exc)


class ExperimentListView(_ExperimentView):
    def get(self, request):
        return Response(list_experiments(request.user))

    def post(self, request):
        return Response(create_experiment(request.user, _body(request, EXPERIMENT_FIELDS, optional=OPTIONAL_EXPERIMENT_FIELDS)), status=201)


class ExperimentDetailView(_ExperimentView):
    def get(self, request, experiment_id):
        return Response(get_experiment(request.user, experiment_id))

    def patch(self, request, experiment_id):
        data = _body(request, ("revision", *EXPERIMENT_FIELDS), optional=OPTIONAL_EXPERIMENT_FIELDS)
        return Response(save_experiment(request.user, experiment_id, data["revision"], data))


class ExperimentCompareView(_ExperimentView):
    throttle_classes = [ComparisonThrottle]

    def post(self, request, experiment_id):
        data = _body(request, ("revision",))
        return Response(compare_experiment(request.user, experiment_id, data["revision"]), status=201)


class ExperimentComparisonView(_ExperimentView):
    def get(self, request, experiment_id, comparison_id):
        return Response(get_comparison(request.user, experiment_id, comparison_id))


class ExperimentDecisionView(_ExperimentView):
    def post(self, request, experiment_id):
        data = _body(request, ("revision", "comparison_id", "outcome", "rationale", "next_action", "review_on"))
        return Response(record_decision(request.user, experiment_id, data), status=201)


class ProgressionObservationsView(_ExperimentView):
    def get(self, request):
        from .progression.observations import economy_observations
        return Response(economy_observations(request.user))


class ExperimentObservationView(_ExperimentView):
    def post(self, request, experiment_id):
        data = _body(request, ("revision",))
        return Response(capture_observation(request.user, experiment_id, data["revision"]), status=201)
