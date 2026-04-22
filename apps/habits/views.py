from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from config.permissions import IsParent
from config.viewsets import WriteReadSerializerMixin

from .models import Habit, HabitSkillTag
from .serializers import HabitSerializer, HabitWriteSerializer
from .services import HabitService


def _apply_skill_tags(habit, tag_dicts):
    """Replace the habit's skill_tags with the given list of {skill_id, xp_weight}.

    Pre-validates every ``skill_id`` — see the same helper in
    ``apps/chores/views.py`` for why this can't rely on FK-constraint errors
    alone (SQLite defers those, so bad input would 201-then-rollback).
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

    HabitSkillTag.objects.filter(habit=habit).delete()
    HabitSkillTag.objects.bulk_create([
        HabitSkillTag(
            habit=habit,
            skill_id=int(t["skill_id"]),
            xp_weight=int(t.get("xp_weight", 1)),
        )
        for t in tag_dicts
    ])


class HabitViewSet(WriteReadSerializerMixin, viewsets.ModelViewSet):
    serializer_class = HabitSerializer
    write_serializer_class = HabitWriteSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Habit.objects.prefetch_related("skill_tags__skill")
        if user.role == "child":
            qs = qs.filter(user=user)
        return qs

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    @transaction.atomic
    def perform_create(self, serializer):
        # @transaction.atomic so a ValidationError from _apply_skill_tags
        # rolls back the Habit row — otherwise a 400 would leave a
        # tag-less habit persisted.
        user = self.request.user
        tags = serializer.validated_data.pop("skill_tags", None)
        if user.role == "child":
            habit = serializer.save(user=user, created_by=user)
        else:
            habit = serializer.save(created_by=user)
        if tags is not None:
            _apply_skill_tags(habit, tags)

    @transaction.atomic
    def perform_update(self, serializer):
        tags = serializer.validated_data.pop("skill_tags", None)
        habit = serializer.save()
        if tags is not None:
            _apply_skill_tags(habit, tags)

    @action(detail=True, methods=["post"])
    def log(self, request, pk=None):
        habit = self.get_object()
        direction = request.data.get("direction")
        try:
            direction = int(direction)
        except (TypeError, ValueError):
            return Response(
                {"error": "direction must be an integer (+1 or -1)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = HabitService.log_tap(request.user, habit, direction)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        game_event = None
        if direction == 1:
            # Imported lazily to avoid a static dep from habits → rpg at
            # module load; the game loop is only triggered for positive taps.
            from apps.rpg.constants import TriggerType
            from apps.rpg.services import GameLoopService

            game_event = GameLoopService.on_task_completed(
                request.user, TriggerType.HABIT_LOG, {"habit_id": habit.pk},
            )

        return Response({**result, "game_event": game_event})
