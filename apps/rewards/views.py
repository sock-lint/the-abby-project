from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import (
    ApprovalActionMixin, ParentWritePermissionMixin,
    RoleFilteredQuerySetMixin, WriteReadSerializerMixin, resolve_target_user,
)

from django.conf import settings as django_settings

from .models import CoinLedger, ExchangeRequest, Reward, RewardRedemption, RewardWishlist
from .serializers import (
    CoinLedgerSerializer, ExchangeRequestSerializer,
    RewardRedemptionSerializer, RewardSerializer, RewardWriteSerializer,
)
from .services import (
    CoinService, ExchangeService, InsufficientCoinsError,
    InsufficientFundsError, RewardService, RewardUnavailableError,
)


class RewardViewSet(WriteReadSerializerMixin, ParentWritePermissionMixin, viewsets.ModelViewSet):
    serializer_class = RewardSerializer
    write_serializer_class = RewardWriteSerializer

    def get_queryset(self):
        family = getattr(self.request.user, "family", None)
        if family is None:
            return Reward.objects.none()
        if self.request.user.role == "parent":
            return Reward.objects.filter(family=family)
        return Reward.objects.filter(family=family, is_active=True)

    def perform_create(self, serializer):
        serializer.save(family=self.request.user.family)

    def perform_update(self, serializer):
        # Stock-restock fanout: when a parent edits a reward and the stock
        # transitions from 0 → ≥1, notify every child who'd wishlisted it
        # AND clear their wishlist row so the next stock-out → restock
        # cycle isn't a re-spam. The notification fires once per edit
        # that actually crosses the boundary, never on PATCHes that
        # leave stock unchanged.
        previous_stock = (
            serializer.instance.stock if serializer.instance else None
        )
        reward = serializer.save()
        new_stock = reward.stock
        was_out = previous_stock == 0
        is_in = new_stock is not None and new_stock >= 1
        if was_out and is_in:
            self._notify_wishlist_on_restock(reward)

    @staticmethod
    def _notify_wishlist_on_restock(reward):
        from apps.notifications.models import NotificationType
        from apps.notifications.services import notify

        wishlist_users = list(
            User.objects.filter(reward_wishlist_entries__reward=reward).distinct()
        )
        for user in wishlist_users:
            notify(
                user,
                title=f"Back in stock: {reward.name}",
                message=(
                    f'"{reward.name}" is available again — head to the '
                    f'rewards shelf to redeem.'
                ),
                notification_type=NotificationType.REWARD_RESTOCKED,
                link="/rewards",
            )
        # Clear the wishlist rows so a future stock-out → restock cycle
        # doesn't re-fire the same notification on the same wishlist
        # entries — the kid had their chance to redeem; if they still
        # want it back on the wishlist after, they can re-add it.
        RewardWishlist.objects.filter(reward=reward).delete()

    @action(detail=True, methods=["post"])
    def redeem(self, request, pk=None):
        reward = self.get_object()
        try:
            redemption = RewardService.request_redemption(request.user, reward)
        except InsufficientCoinsError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RewardUnavailableError as exc:
            # Out-of-stock returns 409 with a small payload of cheaper /
            # similar-rarity rewards so the frontend can offer a graceful
            # "sold out — but you might like..." picker rather than a
            # dead-end toast.
            return Response(
                {
                    "error": str(exc),
                    "code": "out_of_stock",
                    "similar": _similar_rewards_payload(request, reward),
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            RewardRedemptionSerializer(redemption).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post", "delete"], url_path="wishlist")
    def wishlist(self, request, pk=None):
        """Toggle a reward on/off the requesting user's wishlist.

        POST is idempotent (re-adding a row already there is a no-op);
        DELETE silently succeeds when the row doesn't exist. Both keep
        the kid's interaction simple — tap once to bookmark, tap again
        to clear.
        """
        reward = self.get_object()
        if request.method == "POST":
            entry, created = RewardWishlist.objects.get_or_create(
                user=request.user, reward=reward,
            )
            return Response(
                {"wishlisted": True, "created": created},
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )
        # DELETE
        RewardWishlist.objects.filter(user=request.user, reward=reward).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="my-wishlist")
    def my_wishlist(self, request):
        family = getattr(request.user, "family", None)
        if family is None:
            return Response([])
        rewards = (
            Reward.objects.filter(
                family=family, is_active=True,
                wishlist_entries__user=request.user,
            )
            .distinct()
            .order_by("-wishlist_entries__created_at")
        )
        return Response(
            RewardSerializer(rewards, many=True, context={"request": request}).data,
        )


# Imported here rather than at module top to avoid circular reference with
# apps.projects.models (which re-exports User for back-compat).
from apps.projects.models import User  # noqa: E402


def _similar_rewards_payload(request, reward):
    """Return up to 3 in-stock rewards in the same family for the OOS fallback.

    Prefers same-rarity peers, falls back to anything the kid can afford-ish
    (same cost band ± 50%). Excludes the reward we're showing the error
    for and inactive rows.
    """
    base = (
        Reward.objects.filter(family=reward.family, is_active=True)
        .exclude(pk=reward.pk)
        .exclude(stock=0)
    )
    same_rarity = list(base.filter(rarity=reward.rarity).order_by("cost_coins")[:3])
    if len(same_rarity) >= 3:
        return RewardSerializer(
            same_rarity, many=True, context={"request": request},
        ).data
    cost_floor = max(0, int(reward.cost_coins * 0.5))
    cost_ceil = int(reward.cost_coins * 1.5)
    fallback = list(
        base.exclude(pk__in=[r.pk for r in same_rarity])
        .filter(cost_coins__gte=cost_floor, cost_coins__lte=cost_ceil)
        .order_by("cost_coins")[: 3 - len(same_rarity)]
    )
    return RewardSerializer(
        same_rarity + fallback, many=True, context={"request": request},
    ).data


class RewardRedemptionViewSet(
    ApprovalActionMixin, RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet,
):
    serializer_class = RewardRedemptionSerializer
    queryset = RewardRedemption.objects.select_related("reward", "user")
    approval_service = RewardService

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())


class CoinBalanceView(APIView):
    def get(self, request):
        target_user, err = resolve_target_user(request)
        if err:
            return err

        balance = CoinService.get_balance(target_user)
        breakdown = CoinService.get_breakdown(target_user)
        recent = CoinLedger.objects.filter(user=target_user)[:10]
        return Response({
            "balance": balance,
            "breakdown": breakdown,
            "recent_transactions": CoinLedgerSerializer(recent, many=True).data,
        })


class CoinAdjustmentView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        amount = request.data.get("amount")
        description = request.data.get("description", "")
        child, err = resolve_target_user(request, source="data")
        if err:
            return err
        if amount is None:
            return Response(
                {"error": "user_id and amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        amount = int(amount)
        if amount == 0:
            return Response(
                {"error": "Amount must not be zero"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount < 0:
            balance = CoinService.get_balance(child)
            if balance + amount < 0:
                return Response(
                    {"error": f"Insufficient coins ({balance} available)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        entry = CoinService.award_coins(
            child, amount, CoinLedger.Reason.ADJUSTMENT,
            description=description, created_by=request.user,
        )
        return Response(
            CoinLedgerSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


class ExchangeRateView(APIView):
    def get(self, request):
        return Response({"coins_per_dollar": django_settings.COINS_PER_DOLLAR})


class ExchangeRequestView(APIView):
    def post(self, request):
        dollar_amount = request.data.get("dollar_amount")
        if dollar_amount is None:
            return Response(
                {"error": "dollar_amount required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            exchange = ExchangeService.request_exchange(
                request.user, dollar_amount,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )
        except InsufficientFundsError as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            ExchangeRequestSerializer(exchange).data,
            status=status.HTTP_201_CREATED,
        )


class ExchangeRequestViewSet(
    ApprovalActionMixin, RoleFilteredQuerySetMixin, viewsets.ReadOnlyModelViewSet,
):
    """List exchange requests (role-filtered) plus parent approve/reject.

    Creation still happens through :class:`ExchangeRequestView` because the
    POST body and error translation (``InsufficientFundsError`` → 400) are
    distinctly child-facing and don't fit the generic viewset pattern.
    """

    serializer_class = ExchangeRequestSerializer
    queryset = ExchangeRequest.objects.select_related("user")
    approval_service = ExchangeService

    def get_queryset(self):
        return self.get_role_filtered_queryset(super().get_queryset())

    def handle_exception(self, exc):
        if isinstance(exc, InsufficientFundsError):
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
