from rest_framework import serializers

from .models import Timecard, TimeEntry


class TimeEntrySerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)

    class Meta:
        model = TimeEntry
        fields = [
            "id", "user", "project", "project_title", "clock_in", "clock_out",
            "duration_minutes", "notes", "auto_clocked_out", "status",
        ]
        read_only_fields = [
            "user", "clock_in", "clock_out", "duration_minutes",
            "auto_clocked_out", "status",
        ]


class TimecardSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = Timecard
        fields = [
            "id", "user", "username", "week_start", "week_end",
            "total_hours", "hourly_earnings", "bonus_earnings",
            "total_earnings", "status", "decided_by", "decided_at",
            "parent_notes", "created_at",
        ]
        read_only_fields = fields


class TimecardDetailSerializer(TimecardSerializer):
    entries = serializers.SerializerMethodField()

    class Meta(TimecardSerializer.Meta):
        fields = TimecardSerializer.Meta.fields + ["entries"]

    def get_entries(self, obj):
        entries = TimeEntry.objects.filter(
            user=obj.user, status="completed",
            clock_in__date__gte=obj.week_start,
            clock_in__date__lte=obj.week_end,
        )
        return TimeEntrySerializer(entries, many=True).data
