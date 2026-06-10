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


# Reward fields a child proposing a ritual cannot set.
_CHILD_STRIPPED_FIELDS = ("xp_reward", "is_active")


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
        # Audit C1: family-scope every query against the Habit catalog.
        # Without this filter the parent branch returned every household's
        # habits to every parent in the deployment (see the matching fix
        # on ChoreViewSet for the pattern). Children are still narrowed
        # to ``user=user`` below; the family filter on the parent path
        # closes the cross-family read/write/delete surface.
        user = self.request.user
        family = getattr(user, "family", None)
        if family is None:
            return Habit.objects.none()
        qs = Habit.objects.prefetch_related("skill_tags__skill").filter(
            user__family=family,
        )
        pending_filter = self.request.query_params.get("pending") == "true"
        if user.role == "child":
            qs = qs.filter(user=user)
            if pending_filter:
                # Child's own pending proposals.
                return qs.filter(pending_parent_review=True, created_by=user)
            # Regular tap surface: hide pending proposals (rewards unset).
            return qs.filter(pending_parent_review=False)
        if pending_filter:
            return qs.filter(pending_parent_review=True)
        return qs

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy", "approve"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        """Per-habit daily net taps over the last N local days.

        One aggregated HabitLog query across the role-scoped habit set —
        feeds the mini-bars on the Rituals page so strength decay and
        regrowth are visible, not just the current medallion value.
        ``days`` defaults to 14, clamped 1..30. Series are zero-filled
        (every day present, oldest first, ending today) and keyed by
        habit id as strings, since JSON object keys always are.
        """
        from datetime import timedelta

        from django.db.models import Sum
        from django.db.models.functions import TruncDate
        from django.utils import timezone

        from config.viewsets import clamp_int_param

        from .models import HabitLog

        days = clamp_int_param(
            request.query_params.get("days"), default=14, lo=1, hi=30,
        )
        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        habit_ids = list(self.get_queryset().values_list("id", flat=True))

        rows = (
            HabitLog.objects.filter(
                habit_id__in=habit_ids,
                created_at__date__gte=start,
            )
            .annotate(day=TruncDate("created_at"))
            .values("habit_id", "day")
            .annotate(net=Sum("direction"))
        )
        nets = {(r["habit_id"], r["day"]): r["net"] for r in rows}

        date_range = [start + timedelta(days=i) for i in range(days)]
        histories = {
            str(habit_id): [
                {"date": d.isoformat(), "net": nets.get((habit_id, d), 0)}
                for d in date_range
            ]
            for habit_id in habit_ids
        }
        return Response({
            "days": days,
            "start": start.isoformat(),
            "histories": histories,
        })

    @transaction.atomic
    def perform_create(self, serializer):
        # @transaction.atomic so a ValidationError from _apply_skill_tags
        # rolls back the Habit row — otherwise a 400 would leave a
        # tag-less habit persisted.
        user = self.request.user
        tags = serializer.validated_data.pop("skill_tags", None)
        if user.role == "child":
            # Child proposals: strip xp_reward + skill_tags, gate on parent.
            # Parent finalizes rewards via /approve/.
            for field in _CHILD_STRIPPED_FIELDS:
                serializer.validated_data.pop(field, None)
            # user + created_by both go to the child; skill tags dropped.
            habit = serializer.save(
                user=user,
                created_by=user,
                pending_parent_review=True,
            )
            from apps.notifications.models import NotificationType
            from apps.notifications.services import get_display_name, notify_parents
            display = get_display_name(user)
            notify_parents(
                title=f"New ritual proposed: {habit.name}",
                message=f'{display} proposed a new ritual "{habit.name}". Set XP and approve to publish.',
                notification_type=NotificationType.HABIT_PROPOSED,
                link="/manage",
                about_user=user,
            )
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

    def perform_destroy(self, instance):
        was_pending = instance.pending_parent_review
        proposer = instance.created_by
        name = instance.name
        super().perform_destroy(instance)
        if was_pending and proposer and proposer.role == "child":
            from apps.notifications.models import NotificationType
            from apps.notifications.services import notify
            notify(
                proposer,
                title=f"Ritual proposal declined: {name}",
                message=f'Your proposed ritual "{name}" was declined.',
                notification_type=NotificationType.HABIT_PROPOSAL_REJECTED,
                link="/habits",
            )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Parent approves a child-proposed ritual and sets XP + tags."""
        habit = self.get_object()
        if not habit.pending_parent_review:
            return Response(
                {"error": "This ritual is already published."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = HabitWriteSerializer(habit, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tags = serializer.validated_data.pop("skill_tags", None)
        habit = serializer.save()
        habit.pending_parent_review = False
        habit.save(update_fields=["pending_parent_review"])
        if tags is not None:
            _apply_skill_tags(habit, tags)

        proposer = habit.created_by
        if proposer and proposer.role == "child":
            from apps.notifications.models import NotificationType
            from apps.notifications.services import notify
            notify(
                proposer,
                title=f"Ritual published: {habit.name}",
                message=(
                    f'Your proposed ritual "{habit.name}" was approved '
                    f'and is now in your ritual list.'
                ),
                notification_type=NotificationType.HABIT_PROPOSAL_APPROVED,
                link="/habits",
            )

        return Response(HabitSerializer(habit).data)

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
