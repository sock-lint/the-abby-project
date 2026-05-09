"""Parent-only ``/api/dev/*`` REST surface.

Each POST endpoint wraps one function in ``apps.dev_tools.operations``;
the operation is the single source of truth shared with the management
commands. Children targeted by ``user_id`` are always resolved through
``get_child_or_404(child_id, requesting_user=request.user)`` so a parent
in family A can't fire a drop into family B's child.

The whole surface is gated by ``IsDevToolsEnabled`` (parent + DEBUG /
DEV_TOOLS_ENABLED). The frontend ``/manage → Test`` tab probes
``GET /api/dev/ping/`` to decide whether to render itself.
"""
from __future__ import annotations

from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dev_tools import operations as ops
from apps.dev_tools.permissions import IsDevToolsEnabled
from config.viewsets import child_not_found_response, get_child_or_404


def _resolve_target(request, user_id):
    """Family-scoped child lookup. Returns ``(user, error_response)``."""
    user = get_child_or_404(user_id, requesting_user=request.user)
    if user is None:
        return None, child_not_found_response()
    return user, None


def _operation_error(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


# --------------------------------------------------------------------------
# Visibility + selectors
# --------------------------------------------------------------------------

class PingView(APIView):
    """``GET /api/dev/ping/`` — 200 when the panel may render."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        return Response({"enabled": True, "user": request.user.username})


class ChildSelectView(APIView):
    """``GET /api/dev/children/`` — children in caller's family (id + label)."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        from apps.families.queries import children_in

        items = [
            {
                "id": c.id,
                "username": c.username,
                "display_label": getattr(c, "display_label", c.username),
            }
            for c in children_in(request.user.family)
        ]
        return Response(items)


class RewardSelectView(APIView):
    """``GET /api/dev/rewards/`` — caller's family rewards (id, name, stock)."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        from apps.rewards.models import Reward

        items = [
            {"id": r.id, "name": r.name, "stock": r.stock}
            for r in Reward.objects.filter(family=request.user.family).order_by("name")
        ]
        return Response(items)


class ItemSelectView(APIView):
    """``GET /api/dev/items/`` — global ItemDefinitions (slug, name, rarity)."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        from apps.rpg.models import ItemDefinition

        rarity = request.query_params.get("rarity")
        qs = ItemDefinition.objects.all()
        if rarity:
            qs = qs.filter(rarity=rarity)
        items = [
            {"slug": i.slug, "name": i.name, "rarity": i.rarity, "icon": i.icon}
            for i in qs.order_by("rarity", "name")
            if i.slug  # skip slug-less legacy rows
        ]
        return Response(items)


# --------------------------------------------------------------------------
# Operation endpoints (POST)
# --------------------------------------------------------------------------

class _Base(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]


class _ForceDropSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    rarity = serializers.ChoiceField(
        choices=["common", "uncommon", "rare", "epic", "legendary"],
        required=False, allow_null=True,
    )
    slug = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    count = serializers.IntegerField(default=1, min_value=1, max_value=10)
    salvage = serializers.BooleanField(default=False)
    trigger = serializers.CharField(default="dev_tools", max_length=30)

    def validate(self, data):
        if not data.get("rarity") and not data.get("slug"):
            raise serializers.ValidationError("Pass rarity or slug.")
        return data


class ForceDropView(_Base):
    def post(self, request):
        s = _ForceDropSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.force_drop(
                target,
                rarity=s.validated_data.get("rarity") or None,
                slug=s.validated_data.get("slug") or None,
                count=s.validated_data["count"],
                salvage=s.validated_data["salvage"],
                trigger=s.validated_data["trigger"],
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _ForceCelebrationSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["streak_milestone", "perfect_day", "birthday"])
    days = serializers.IntegerField(default=30, min_value=1, max_value=10000)
    gift_coins = serializers.IntegerField(default=500, min_value=0, max_value=100000)


class ForceCelebrationView(_Base):
    def post(self, request):
        s = _ForceCelebrationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.force_celebration(
                target,
                kind=s.validated_data["kind"],
                days=s.validated_data["days"],
                gift_coins=s.validated_data["gift_coins"],
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _SetStreakSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    days = serializers.IntegerField(min_value=0, max_value=10000)
    perfect_days = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class SetStreakView(_Base):
    def post(self, request):
        s = _SetStreakSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        result = ops.set_streak(
            target,
            days=s.validated_data["days"],
            perfect_days=s.validated_data.get("perfect_days"),
        )
        return Response(result)


class _SetRewardStockSerializer(serializers.Serializer):
    reward_id = serializers.IntegerField()
    stock = serializers.IntegerField(min_value=0, max_value=10000)


class SetRewardStockView(_Base):
    def post(self, request):
        s = _SetRewardStockSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        # Re-scope by family — set_reward_stock takes a string ref but we
        # want the parent's family-bound view to do the lookup so they
        # can't poke another family's reward by id.
        from apps.rewards.models import Reward
        reward = Reward.objects.filter(
            pk=s.validated_data["reward_id"], family=request.user.family,
        ).first()
        if reward is None:
            return Response(
                {"detail": "Reward not found in your family."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            result = ops.set_reward_stock(
                reward_ref=str(reward.pk), stock=s.validated_data["stock"],
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _ExpireJournalSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    days_back = serializers.IntegerField(default=1, min_value=1, max_value=365)


class ExpireJournalView(_Base):
    def post(self, request):
        s = _ExpireJournalSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        result = ops.expire_journal(target, days_back=s.validated_data["days_back"])
        return Response(result)


class TickPerfectDayView(_Base):
    def post(self, request):
        return Response(ops.tick_perfect_day())


class _SetPetHappinessSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    level = serializers.ChoiceField(choices=list(ops.PET_HAPPINESS_DAYS_BACK))
    pet_id = serializers.IntegerField(required=False, allow_null=True)


class SetPetHappinessView(_Base):
    def post(self, request):
        s = _SetPetHappinessSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.set_pet_happiness(
                target,
                level=s.validated_data["level"],
                pet_id=s.validated_data.get("pet_id"),
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _ResetDayCountersSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    kind = serializers.ChoiceField(
        choices=list(ops.DAY_COUNTER_KINDS) + ["all"],
        default="all",
    )


class ResetDayCountersView(_Base):
    def post(self, request):
        s = _ResetDayCountersSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.reset_day_counters(target, kind=s.validated_data["kind"])
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


# --------------------------------------------------------------------------
# Checklist content (read docs/manual-testing.md so the panel can embed it)
# --------------------------------------------------------------------------

class ChecklistView(APIView):
    """``GET /api/dev/checklist/`` — raw markdown of docs/manual-testing.md."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "docs" / "manual-testing.md"
        if not path.exists():
            return Response({"detail": "Checklist file not found."}, status=404)
        return Response({"markdown": path.read_text(encoding="utf-8")})
