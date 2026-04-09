from rest_framework import serializers

from .models import CoinLedger, Reward, RewardRedemption


class RewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reward
        fields = [
            "id", "name", "description", "icon", "image", "cost_coins",
            "rarity", "stock", "requires_parent_approval", "is_active", "order",
        ]


class RewardRedemptionSerializer(serializers.ModelSerializer):
    reward = RewardSerializer(read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

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
