from rest_framework import serializers

from apps.rpg.models import ItemDefinition
from apps.rpg.serializers import ItemDefinitionSerializer

from .models import CoinLedger, ExchangeRequest, Reward, RewardRedemption


class RewardSerializer(serializers.ModelSerializer):
    item_definition_detail = ItemDefinitionSerializer(
        source="item_definition", read_only=True,
    )

    class Meta:
        model = Reward
        fields = [
            "id", "name", "description", "icon", "image", "cost_coins",
            "rarity", "stock", "requires_parent_approval", "is_active", "order",
            "fulfillment_kind", "item_definition", "item_definition_detail",
        ]


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
        return attrs


class RewardRedemptionSerializer(serializers.ModelSerializer):
    reward = RewardSerializer(read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)
    # Alias: column was renamed to ``created_at`` (PR: adopt CreatedAtModel)
    # but the frontend still reads ``requested_at`` — keep exposing the old
    # key to avoid a coordinated release.
    requested_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = RewardRedemption
        fields = [
            "id", "user", "user_name", "reward", "status",
            "coin_cost_snapshot", "requested_at", "decided_at",
            "decided_by", "parent_notes",
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
