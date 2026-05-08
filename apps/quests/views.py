from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import get_child_or_404, child_not_found_response

from .models import DailyChallenge, QuestDefinition, Quest, QuestParticipant
from .serializers import (
    DailyChallengeSerializer,
    QuestSerializer,
    QuestDefinitionSerializer,
    QuestWriteSerializer,
)
from .services import DailyChallengeService, QuestService


class ActiveQuestView(APIView):
    """GET /api/quests/active/ — current active quest with progress."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        quest = QuestService.get_active_quest(request.user)
        if not quest:
            return Response(None)
        return Response(QuestSerializer(quest).data)


class AvailableQuestsView(APIView):
    """GET /api/quests/available/ — system quests + quest scrolls in inventory."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        system_quests = QuestDefinition.objects.filter(is_system=True)
        return Response(QuestDefinitionSerializer(system_quests, many=True).data)


class StartQuestView(APIView):
    """POST /api/quests/start/ — start a quest."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        definition_id = request.data.get("definition_id")
        scroll_item_id = request.data.get("scroll_item_id")
        if not definition_id:
            return Response({"error": "definition_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            quest = QuestService.start_quest(request.user, definition_id, scroll_item_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(QuestSerializer(quest).data, status=status.HTTP_201_CREATED)


class QuestHistoryView(APIView):
    """GET /api/quests/history/ — completed/failed/expired quests."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        quests = Quest.objects.filter(
            participants__user=request.user,
        ).exclude(status="active").select_related("definition")[:20]
        return Response(QuestSerializer(quests, many=True).data)


class CreateQuestView(APIView):
    """POST /api/quests/ — parent creates a custom quest.

    Accepts an optional ``coop_user_ids`` list (>= 2) to start the quest
    as a shared co-op campaign. ``assigned_to`` (single child) and
    ``coop_user_ids`` are mutually exclusive — co-op wins. Optional
    ``skill_tags`` (list of {skill_id, xp_weight}) sets up the XP fanout
    so custom quests don't silently award 0 XP at completion.
    """
    permission_classes = [IsParent]

    def post(self, request):
        from django.db import transaction
        from apps.achievements.models import Skill
        from apps.quests.models import QuestSkillTag

        serializer = QuestWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        coop_ids = data.get("coop_user_ids") or []
        skill_tag_rows = data.get("skill_tags") or []

        # Pre-validate skill ids before any write so a typo surfaces as
        # a friendly 400 with the offending id.
        if skill_tag_rows:
            requested = [row["skill_id"] for row in skill_tag_rows]
            existing = set(
                Skill.objects.filter(pk__in=requested).values_list("pk", flat=True)
            )
            missing = [pk for pk in requested if pk not in existing]
            if missing:
                return Response(
                    {"error": f"Unknown skill_id(s): {missing}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Resolve child(ren) before opening the txn so cross-family ids
        # surface as 404 without rolling back a partially-built quest.
        coop_children = []
        single_child = None
        if coop_ids:
            for uid in coop_ids:
                child = get_child_or_404(uid, requesting_user=request.user)
                if not child:
                    return child_not_found_response()
                coop_children.append(child)
        elif data.get("assigned_to"):
            single_child = get_child_or_404(
                data["assigned_to"], requesting_user=request.user,
            )
            if not single_child:
                return child_not_found_response()

        try:
            with transaction.atomic():
                definition = QuestDefinition.objects.create(
                    name=data["name"],
                    description=data["description"],
                    icon=data.get("icon", "⚔️"),
                    quest_type=data["quest_type"],
                    target_value=data["target_value"],
                    duration_days=data.get("duration_days", 7),
                    coin_reward=data.get("coin_reward", 0),
                    xp_reward=data.get("xp_reward", 0),
                    trigger_filter=data.get("trigger_filter", {}),
                    created_by=request.user,
                )

                # Skill tag fanout — dedup on skill_id; bulk_create.
                if skill_tag_rows:
                    seen = set()
                    tag_objects = []
                    for row in skill_tag_rows:
                        sid = row["skill_id"]
                        if sid in seen:
                            continue
                        seen.add(sid)
                        tag_objects.append(QuestSkillTag(
                            quest_definition=definition,
                            skill_id=sid,
                            xp_weight=row.get("xp_weight", 1),
                        ))
                    QuestSkillTag.objects.bulk_create(tag_objects)

                if coop_children:
                    QuestService.start_co_op_quest(definition.pk, coop_children)
                elif single_child is not None:
                    QuestService.start_quest(single_child, definition.pk)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(QuestDefinitionSerializer(definition).data, status=status.HTTP_201_CREATED)


class QuestCatalogView(ListAPIView):
    """GET /api/quests/catalog/ — parent-only browse of every authored QuestDefinition."""
    permission_classes = [permissions.IsAuthenticated, IsParent]
    serializer_class = QuestDefinitionSerializer
    pagination_class = None

    def get_queryset(self):
        return QuestDefinition.objects.prefetch_related(
            "reward_items", "reward_items__item",
        ).order_by("quest_type", "name")


class FamilyActiveQuestsView(APIView):
    """GET /api/quests/family/ — parent-only family roll-up of each child's active quest."""
    permission_classes = [IsParent]

    def get(self, request):
        from apps.projects.models import User

        children = (
            User.objects.filter(role="child", family=request.user.family)
            .order_by("display_name", "username")
        )
        rows = []
        for child in children:
            quest = QuestService.get_active_quest(child)
            rows.append({
                "child_id": child.pk,
                "child_name": child.display_label,
                "quest": QuestSerializer(quest).data if quest else None,
            })
        return Response({"results": rows})


class AssignQuestView(APIView):
    """POST /api/quests/{id}/assign/ — parent assigns quest to child."""
    permission_classes = [IsParent]

    def post(self, request, pk):
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        child = get_child_or_404(user_id, requesting_user=request.user)
        if not child:
            return child_not_found_response()
        try:
            quest = QuestService.start_quest(child, pk)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(QuestSerializer(quest).data, status=status.HTTP_201_CREATED)


class StartCoOpQuestView(APIView):
    """POST /api/quests/{id}/co-op/ — parent starts a shared quest for >1 child.

    Body: ``{"user_ids": [1, 2, ...]}``. Every user_id must be a child in
    the requesting parent's family — cross-family attempts surface as 404
    (the shape ``get_child_or_404`` already enforces).
    """
    permission_classes = [IsParent]

    def post(self, request, pk):
        user_ids = request.data.get("user_ids") or []
        if not isinstance(user_ids, list) or len(user_ids) < 2:
            return Response(
                {"error": "user_ids must be a list of at least 2 children"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        children = []
        for uid in user_ids:
            child = get_child_or_404(uid, requesting_user=request.user)
            if not child:
                return child_not_found_response()
            children.append(child)
        try:
            quest = QuestService.start_co_op_quest(pk, children)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(QuestSerializer(quest).data, status=status.HTTP_201_CREATED)


class DailyChallengeView(APIView):
    """GET /api/challenges/daily/ — today's daily challenge, auto-created on first access."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        challenge = DailyChallengeService.get_or_create_today(request.user)
        return Response(DailyChallengeSerializer(challenge).data)


class ClaimDailyChallengeView(APIView):
    """POST /api/challenges/daily/claim/ — award coin + XP for a completed daily."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            result = DailyChallengeService.claim_reward(request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
