"""Staff-parent ``/api/dev/*`` REST surface.

Each POST endpoint wraps one function in ``apps.dev_tools.operations``;
the operation is the single source of truth shared with the management
commands. Children targeted by ``user_id`` are always resolved through
``get_child_or_404(child_id, requesting_user=request.user)`` so a staff
parent in family A can't fire a drop into family B's child.

The whole surface is gated by ``IsDevToolsEnabled`` (parent +
``is_staff=True`` + DEBUG / DEV_TOOLS_ENABLED). ``createsuperuser`` sets
``is_staff=True`` automatically; signup-created parents do NOT, so a
production deploy can flip ``DEV_TOOLS_ENABLED=true`` for the founding
superuser without unlocking the panel for every family that signed up.

The frontend ``/manage → Test`` tab probes ``GET /api/dev/ping/`` to
decide whether to render itself.
"""
from __future__ import annotations

from django.db import models
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
    """``GET /api/dev/children/`` — children in caller's family with nested pets + mounts."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        from apps.families.queries import children_in
        from apps.pets.models import MountExpedition, UserMount, UserPet

        children = list(
            children_in(request.user.family)
            .prefetch_related(
                # Both prefetches scoped to non-evolved pets and to mounts;
                # one extra query per side covers every kid in the family.
                models.Prefetch(
                    "pets",
                    queryset=UserPet.objects.select_related("species", "potion")
                    .filter(evolved_to_mount=False),
                    to_attr="_dev_pets",
                ),
                models.Prefetch(
                    "mounts",
                    queryset=UserMount.objects.select_related("species", "potion"),
                    to_attr="_dev_mounts",
                ),
            )
        )

        # Active expeditions, batched per mount so we don't N+1 across kids.
        mount_ids = [m.pk for c in children for m in getattr(c, "_dev_mounts", [])]
        active_mounts = set(
            MountExpedition.objects
            .filter(mount_id__in=mount_ids, status=MountExpedition.Status.ACTIVE)
            .values_list("mount_id", flat=True)
        )

        items = []
        for c in children:
            pets = [
                {
                    "id": p.pk,
                    "name": p.name or f"{p.species.name}",
                    "species_name": p.species.name,
                    "species_slug": p.species.slug,
                    "potion_name": p.potion.name,
                    "growth_points": p.growth_points,
                    "evolved": p.evolved_to_mount,
                }
                for p in getattr(c, "_dev_pets", [])
            ]
            mounts = [
                {
                    "id": m.pk,
                    "species_name": m.species.name,
                    "species_slug": m.species.slug,
                    "potion_name": m.potion.name,
                    "last_bred_at": (
                        m.last_bred_at.isoformat() if m.last_bred_at else None
                    ),
                    "has_active_expedition": m.pk in active_mounts,
                }
                for m in getattr(c, "_dev_mounts", [])
            ]
            items.append({
                "id": c.id,
                "username": c.username,
                "display_label": getattr(c, "display_label", c.username),
                "pets": pets,
                "mounts": mounts,
            })
        return Response(items)


class PetSpeciesSelectView(APIView):
    """``GET /api/dev/pet-species/`` — global PetSpecies catalog."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        from apps.pets.models import PetSpecies

        items = [
            {
                "slug": s.slug,
                "name": s.name,
                "icon": s.icon,
                "sprite_key": s.sprite_key,
            }
            for s in PetSpecies.objects.order_by("name") if s.slug
        ]
        return Response(items)


class PotionTypeSelectView(APIView):
    """``GET /api/dev/potion-types/`` — global PotionType catalog."""

    permission_classes = [permissions.IsAuthenticated, IsDevToolsEnabled]

    def get(self, request):
        from apps.pets.models import PotionType

        items = [
            {
                "slug": p.slug,
                "name": p.name,
                "rarity": p.rarity,
                "color_hex": p.color_hex,
            }
            for p in PotionType.objects.order_by("name") if p.slug
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
# E. Toast & ceremony coverage (added 2026-05-11)
# --------------------------------------------------------------------------

class _ForceApprovalNotificationSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    flow = serializers.ChoiceField(
        choices=[
            "chore", "homework", "creation", "exchange",
            "chore_proposal", "habit_proposal",
        ],
    )
    outcome = serializers.ChoiceField(choices=["approved", "rejected"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=400)


class ForceApprovalNotificationView(_Base):
    def post(self, request):
        s = _ForceApprovalNotificationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.force_approval_notification(
                target,
                flow=s.validated_data["flow"],
                outcome=s.validated_data["outcome"],
                note=s.validated_data.get("note", ""),
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _ForceQuestProgressSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    delta = serializers.IntegerField(default=10, min_value=1, max_value=1000)


class ForceQuestProgressView(_Base):
    def post(self, request):
        s = _ForceQuestProgressSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.force_quest_progress(
                target, delta=s.validated_data["delta"],
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _MarkDailyChallengeReadySerializer(serializers.Serializer):
    user_id = serializers.IntegerField()


class MarkDailyChallengeReadyView(_Base):
    def post(self, request):
        s = _MarkDailyChallengeReadySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.mark_daily_challenge_ready(target)
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _SetPetGrowthSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    pet_id = serializers.IntegerField()
    growth = serializers.IntegerField(default=99, min_value=0, max_value=99)


class SetPetGrowthView(_Base):
    def post(self, request):
        s = _SetPetGrowthSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.set_pet_growth(
                target,
                pet_id=s.validated_data["pet_id"],
                growth=s.validated_data["growth"],
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _GrantHatchIngredientsSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    species_slug = serializers.CharField(max_length=60)
    potion_slug = serializers.CharField(max_length=60)


class GrantHatchIngredientsView(_Base):
    def post(self, request):
        s = _GrantHatchIngredientsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.grant_hatch_ingredients(
                target,
                species_slug=s.validated_data["species_slug"],
                potion_slug=s.validated_data["potion_slug"],
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _ClearBreedCooldownsSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    mount_id = serializers.IntegerField(required=False, allow_null=True)


class ClearBreedCooldownsView(_Base):
    def post(self, request):
        s = _ClearBreedCooldownsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.clear_mount_breed_cooldowns(
                target, mount_id=s.validated_data.get("mount_id"),
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _SeedCompanionGrowthSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    ticks = serializers.IntegerField(default=3, min_value=1, max_value=10)
    force_evolve = serializers.BooleanField(default=False)


class SeedCompanionGrowthView(_Base):
    def post(self, request):
        s = _SeedCompanionGrowthSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.seed_companion_growth(
                target,
                ticks=s.validated_data["ticks"],
                force_evolve=s.validated_data["force_evolve"],
            )
        except ops.OperationError as e:
            return _operation_error(str(e))
        return Response(result)


class _MarkExpeditionReadySerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    mount_id = serializers.IntegerField(required=False, allow_null=True)
    tier = serializers.ChoiceField(
        choices=["short", "standard", "long"], default="standard",
    )


class MarkExpeditionReadyView(_Base):
    def post(self, request):
        s = _MarkExpeditionReadySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        target, err = _resolve_target(request, s.validated_data["user_id"])
        if err:
            return err
        try:
            result = ops.mark_expedition_ready(
                target,
                mount_id=s.validated_data.get("mount_id"),
                tier=s.validated_data["tier"],
            )
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
