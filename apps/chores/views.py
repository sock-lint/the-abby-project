from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from config.viewsets import (
    ApprovalActionMixin, ParentWritePermissionMixin,
    RoleFilteredQuerySetMixin, WriteReadSerializerMixin,
)

from .models import Chore, ChoreCompletion, ChoreSkillTag
from .serializers import (
    ChoreCompletionSerializer, ChoreSerializer, ChoreWriteSerializer,
)
from .services import ChoreNotAvailableError, ChoreService


def _apply_skill_tags(chore, tag_dicts):
    """Replace the chore's skill_tags with the given list of {skill_id, xp_weight}.

    Pre-validates every ``skill_id`` exists. SQLite defers FK checks to
    commit, so a bad ID in ``bulk_create`` wouldn't raise until the
    transaction closes — the API would already have responded 201 with a
    chore that then fails to persist. Failing early here surfaces bad
    input as a clean 400.
    """
    from apps.achievements.models import Skill

    skill_ids = {int(t["skill_id"]) for t in tag_dicts}
    if skill_ids:
        known = set(
            Skill.objects.filter(id__in=skill_ids).values_list("id", flat=True),
        )
        missing = sorted(skill_ids - known)
        if missing:
            raise ValidationError({
                "skill_tags": [f"Unknown skill IDs: {missing}"],
            })

    ChoreSkillTag.objects.filter(chore=chore).delete()
    ChoreSkillTag.objects.bulk_create([
        ChoreSkillTag(
            chore=chore,
            skill_id=int(t["skill_id"]),
            xp_weight=int(t.get("xp_weight", 1)),
        )
        for t in tag_dicts
    ])


class ChoreViewSet(WriteReadSerializerMixin, ParentWritePermissionMixin, viewsets.ModelViewSet):
    serializer_class = ChoreSerializer
    write_serializer_class = ChoreWriteSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == "parent":
            return Chore.objects.prefetch_related("skill_tags__skill")
        return Chore.objects.filter(is_active=True).prefetch_related(
            "skill_tags__skill",
        )

    @transaction.atomic
    def perform_create(self, serializer):
        # skill_tags is a write-only list field (see ChoreWriteSerializer);
        # pop before save so ModelSerializer doesn't try to assign to the
        # reverse FK manager, then apply after the Chore row exists.
        # @transaction.atomic is load-bearing: if _apply_skill_tags raises
        # ValidationError on a bad skill_id the Chore row rolls back, so
        # the 400 response matches reality — no half-built chore left over.
        tags = serializer.validated_data.pop("skill_tags", [])
        chore = serializer.save(created_by=self.request.user)
        _apply_skill_tags(chore, tags)

    @transaction.atomic
    def perform_update(self, serializer):
        # Only apply tags if the client explicitly sent the field —
        # omitting leaves the existing tag set alone (common for minor
        # edits that don't re-save the whole form).
        tags = serializer.validated_data.pop("skill_tags", None)
        chore = serializer.save()
        if tags is not None:
            _apply_skill_tags(chore, tags)

    def list(self, request, *args, **kwargs):
        user = request.user
        if user.role == "child":
            chores = ChoreService.get_available_chores(user)
            data = []
            for chore in chores:
                serialized = ChoreSerializer(chore).data
                serialized["is_available"] = not chore.is_done_today
                serialized["today_status"] = chore.today_completion_status
                serialized["today_completion_id"] = chore.today_completion_id
                data.append(serialized)
            return Response(data)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        chore = self.get_object()
        try:
            completion = ChoreService.submit_completion(
                request.user, chore, notes=request.data.get("notes", ""),
            )
        except ChoreNotAvailableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ChoreCompletionSerializer(completion).data,
            status=status.HTTP_201_CREATED,
        )


class ChoreCompletionViewSet(
    ApprovalActionMixin, RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet,
):
    serializer_class = ChoreCompletionSerializer
    queryset = ChoreCompletion.objects.select_related("chore", "user")
    approval_service = ChoreService
    approval_approve_method = "approve_completion"
    approval_reject_method = "reject_completion"

    def get_queryset(self):
        qs = self.get_role_filtered_queryset(super().get_queryset())
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs
