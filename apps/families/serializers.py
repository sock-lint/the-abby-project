from rest_framework import serializers

from .models import Family


class FamilySerializer(serializers.ModelSerializer):
    """Read-shape for the Family record. Writable fields not exposed in v1."""

    class Meta:
        model = Family
        fields = ["id", "name", "slug", "timezone", "default_theme", "primary_parent"]
        read_only_fields = fields
