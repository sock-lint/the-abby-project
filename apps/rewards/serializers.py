from rest_framework import serializers

from apps.rpg.models import ItemDefinition
from apps.rpg.serializers import ItemDefinitionSerializer

from .models import CoinLedger, ExchangeRequest, Reward, RewardRedemption


class RewardSerializer(serializers.ModelSerializer):
    catalog_available = serializers.SerializerMethodField()
    item_definition_detail = ItemDefinitionSerializer(
        source="item_definition", read_only=True,
    )
    on_my_wishlist = serializers.SerializerMethodField()

    class Meta:
        model = Reward
        fields = [
            "id", "name", "description", "icon", "image", "cost_coins",
            "rarity", "stock", "requires_parent_approval", "is_active", "order",
            "fulfillment_kind", "item_definition", "item_definition_detail",
            "on_my_wishlist",
            "catalog_available",
        ]

    def get_catalog_available(self, obj):
        from .availability import reward_is_available
        return reward_is_available(obj)

    def get_on_my_wishlist(self, obj):
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return False
        # Use the prefetched manager when present (list view) so we don't
        # fire one query per row. Falls back to a direct query when the
        # serializer is invoked outside the viewset (e.g. from a
        # redemption response).
        cached = getattr(obj, "_my_wishlist_user_ids", None)
        if cached is not None:
            return request.user.id in cached
        from .models import RewardWishlist
        return RewardWishlist.objects.filter(
            user=request.user, reward=obj,
        ).exists()


class RewardWriteSerializer(serializers.ModelSerializer):
    item_definition = serializers.PrimaryKeyRelatedField(
        queryset=ItemDefinition.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Reward
        fields = [
            "name", "description", "icon", "image", "cost_coins",
            "rarity", "stock", "requires_parent_approval", "is_active", "order",
            "fulfillment_kind", "item_definition",
        ]

    def validate(self, attrs):
        fulfillment_kind = attrs.get(
            "fulfillment_kind",
            getattr(self.instance, "fulfillment_kind", Reward.FulfillmentKind.REAL_WORLD),
        )
        item_definition = attrs.get(
            "item_definition",
            getattr(self.instance, "item_definition", None),
        )
        if (
            fulfillment_kind
            in (Reward.FulfillmentKind.DIGITAL_ITEM, Reward.FulfillmentKind.BOTH)
            and item_definition is None
        ):
            raise serializers.ValidationError({
                "item_definition": "Digital rewards must choose an inventory item.",
            })
        if fulfillment_kind != Reward.FulfillmentKind.REAL_WORLD and item_definition and attrs.get("is_active", getattr(self.instance, "is_active", True)):
            from apps.rpg.catalog_support import item_is_available
            from apps.egg_discoveries.policy import legacy_egg_acquisition_allowed
            if not legacy_egg_acquisition_allowed(item_definition) or not item_is_available(item_definition):
                raise serializers.ValidationError({
                    "item_definition": "This item is not currently available for new rewards.",
                })
        return attrs


class RewardRedemptionSerializer(serializers.ModelSerializer):
    reward = serializers.SerializerMethodField()
    user_name = serializers.CharField(source="user.username", read_only=True)
    # Alias: column was renamed to ``created_at`` (PR: adopt CreatedAtModel)
    # but the frontend still reads ``requested_at`` — keep exposing the old
    # key to avoid a coordinated release.
    requested_at = serializers.DateTimeField(source="created_at", read_only=True)

    def get_reward(self, obj):
        # Keep the established response shape while showing the saved promise
        # in request history. The shop's RewardSerializer still shows today's
        # editable offer for new purchases.
        data = dict(RewardSerializer(obj.reward, context=self.context).data)
        data["cost_coins"] = obj.coin_cost_snapshot
        data["fulfillment_kind"] = obj.fulfillment_kind_snapshot
        data["item_definition"] = obj.item_definition_snapshot_id
        data["item_definition_detail"] = (
            ItemDefinitionSerializer(obj.item_definition_snapshot, context=self.context).data
            if obj.item_definition_snapshot_id is not None else None
        )
        return data

    class Meta:
        model = RewardRedemption
        fields = [
            "id", "user", "user_name", "reward", "status",
            "coin_cost_snapshot", "requested_at", "decided_at",
            "decided_by", "parent_notes", "delivered_at", "delivered_by",
        ]
        read_only_fields = fields


class CoinLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoinLedger
        fields = ["id", "user", "amount", "reason", "description", "created_at"]
        read_only_fields = fields


class ExchangeRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = ExchangeRequest
        fields = [
            "id", "user", "user_name", "dollar_amount", "coin_amount",
            "exchange_rate", "status", "created_at", "decided_at",
            "decided_by", "parent_notes",
        ]
        read_only_fields = fields
