from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ["This field is not accepted."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class RequestSerializer(StrictSerializer):
    client_request_id = serializers.UUIDField()


class SelectSerializer(RequestSerializer):
    offer_key = serializers.CharField(max_length=180)


class PracticeSerializer(RequestSerializer):
    name = serializers.CharField(max_length=100)
    minutes = serializers.IntegerField(min_value=1, max_value=240)
