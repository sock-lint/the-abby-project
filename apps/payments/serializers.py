from decimal import Decimal

from rest_framework import serializers
from django.utils import timezone

from .models import GreenlightBalanceSnapshot, PaymentLedger


class PaymentLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentLedger
        fields = [
            "id", "user", "amount", "entry_type", "description",
            "project", "timecard", "created_at", "created_by",
        ]
        read_only_fields = fields


class GreenlightBalanceSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = GreenlightBalanceSnapshot
        fields = ["id", "user", "amount", "as_of", "memo", "created_by", "created_at"]
        read_only_fields = fields


class GreenlightTargetSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)


class GreenlightPayoutSerializer(GreenlightTargetSerializer):
    amount = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))
    transferred_on = serializers.DateField()
    reference = serializers.CharField(max_length=200, allow_blank=True, default="")
    memo = serializers.CharField(max_length=1000, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=128)
    timecard_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)

    def validate_transferred_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Transfer date must not be in the future.")
        return value


class GreenlightSnapshotInputSerializer(GreenlightTargetSerializer):
    amount = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.00"))
    as_of = serializers.DateTimeField()
    memo = serializers.CharField(max_length=1000, allow_blank=True, default="")

    def validate_as_of(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("Balance observation must not be in the future.")
        return value


class GreenlightPreviewSerializer(GreenlightTargetSerializer):
    csv_data = serializers.CharField(max_length=512 * 1024, trim_whitespace=False)


class GreenlightSelectionSerializer(serializers.Serializer):
    fingerprint = serializers.RegexField(r"^[0-9a-f]{64}$")
    match_payment_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    timecard_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)


class GreenlightReconcileSerializer(GreenlightPreviewSerializer):
    selections = GreenlightSelectionSerializer(many=True, allow_empty=False, max_length=500)
