from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from config.permissions import IsParent
from config.viewsets import (
    ApprovalActionMixin, RoleFilteredQuerySetMixin, WriteReadSerializerMixin,
)

from .models import Chore, ChoreCompletion, ChoreSkillTag
from .serializers import (
    ChoreCompletionSerializer, ChoreSerializer, ChoreWriteSerializer,
)
from .services import ChoreNotAvailableError, ChoreService


# Reward + gatekeeping fields children can never set on a proposal.
# Homework strips the same shape (``apps/homework/services.py:74``) — single
# source of truth for "child created this, parent must fill in later".
_CHILD_STRIPPED_FIELDS = (
    "reward_amount", "coin_reward", "xp_reward",
    "assigned_to", "is_active", "order",
)


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


class ChoreViewSet(WriteReadSerializerMixin, viewsets.ModelViewSet):
    serializer_class = ChoreSerializer
    write_serializer_class = ChoreWriteSerializer

    def get_permissions(self):
        # Children can CREATE (proposals). Everything else — updates,
        # destroy, approve — stays parent-only.
        if self.action in ("update", "partial_update", "destroy", "approve"):
            return [IsParent()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Chore.objects.prefetch_related("skill_tags__skill")
        if user.role == "parent":
            # Parents can filter to just pending proposals for the review queue.
            if self.request.query_params.get("pending") == "true":
                qs = qs.filter(pending_parent_review=True)
            return qs
        # Children see active, non-pending chores; their own pending
        # proposals are fetched via the explicit ``?mine=true&pending=true``
        # branch so they can track what they've asked for.
        if self.request.query_params.get("pending") == "true":
            return qs.filter(pending_parent_review=True, created_by=user)
        return qs.filter(is_active=True, pending_parent_review=False)

    @transaction.atomic
    def perform_create(self, serializer):
        # skill_tags is a write-only list field (see ChoreWriteSerializer);
        # pop before save so ModelSerializer doesn't try to assign to the
        # reverse FK manager, then apply after the Chore row exists.
        # @transaction.atomic is load-bearing: if _apply_skill_tags raises
        # ValidationError on a bad skill_id the Chore row rolls back, so
        # the 400 response matches reality — no half-built chore left over.
        user = self.request.user
        tags = serializer.validated_data.pop("skill_tags", [])
        if user.role == "child":
            # Child proposals: strip every reward + access field regardless
            # of what was posted. Parent finalizes later via /approve/.
            for field in _CHILD_STRIPPED_FIELDS:
                serializer.validated_data.pop(field, None)
            chore = serializer.save(
                created_by=user,
                assigned_to=user,
                pending_parent_review=True,
            )
            from apps.notifications.models import NotificationType
            from apps.notifications.services import get_display_name, notify_parents
            display = get_display_name(user)
            notify_parents(
                title=f"New duty proposed: {chore.title}",
                message=f'{display} proposed a new duty "{chore.title}". Set rewards and approve to publish.',
                notification_type=NotificationType.CHORE_PROPOSED,
                link="/manage",
            )
        else:
            chore = serializer.save(created_by=user)
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

    def perform_destroy(self, instance):
        # Rejecting a pending proposal: notify the proposer before the
        # row disappears so they know a human looked at it.
        was_pending = instance.pending_parent_review
        proposer = instance.created_by
        title = instance.title
        super().perform_destroy(instance)
        if was_pending and proposer and proposer.role == "child":
            from apps.notifications.models import NotificationType
            from apps.notifications.services import notify
            notify(
                proposer,
                title=f"Duty proposal declined: {title}",
                message=f'Your proposed duty "{title}" was declined.',
                notification_type=NotificationType.CHORE_PROPOSAL_REJECTED,
                link="/chores",
            )

    def list(self, request, *args, **kwargs):
        user = request.user
        # Parent review list bypasses the get_available_chores helper —
        # pending proposals haven't been priced yet and shouldn't be
        # annotated with tap availability.
        if request.query_params.get("pending") == "true":
            return super().list(request, *args, **kwargs)
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

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        """Parent approves a child-proposed duty and sets the rewards.

        Body accepts reward_amount, coin_reward, xp_reward, skill_tags,
        and optionally the gatekeeping fields parents routinely set
        (assigned_to, is_active). Anything not provided keeps its
        existing value. Clears ``pending_parent_review`` and notifies
        the proposer.
        """
        chore = self.get_object()
        if not chore.pending_parent_review:
            return Response(
                {"error": "This duty is already published."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ChoreWriteSerializer(chore, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tags = serializer.validated_data.pop("skill_tags", None)
        chore = serializer.save()
        chore.pending_parent_review = False
        chore.save(update_fields=["pending_parent_review"])
        if tags is not None:
            _apply_skill_tags(chore, tags)

        proposer = chore.created_by
        if proposer and proposer.role == "child":
            from apps.notifications.models import NotificationType
            from apps.notifications.services import notify
            notify(
                proposer,
                title=f"Duty published: {chore.title}",
                message=(
                    f'Your proposed duty "{chore.title}" was approved '
                    f'and is now in your duty list.'
                ),
                notification_type=NotificationType.CHORE_PROPOSAL_APPROVED,
                link="/chores",
            )

        return Response(ChoreSerializer(chore).data)


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
