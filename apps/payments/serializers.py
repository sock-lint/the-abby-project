from rest_framework import serializers

from .models import PaymentLedger


class PaymentLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentLedger
        fields = [
            "id", "user", "amount", "entry_type", "description",
            "project", "timecard", "created_at", "created_by",
        ]
        read_only_fields = fields
