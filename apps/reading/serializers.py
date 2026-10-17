from django.utils import timezone
from rest_framework import serializers

from apps.quests.activity import household_timezone

from .constants import INTERESTS
from .models import ReadingBook, ReadingSession


class ReadingBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingBook
        fields = ["id", "user", "title", "author", "status", "interests", "client_request_id", "created_at", "updated_at"]
        read_only_fields = fields


class ReadingSessionSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    book_author = serializers.CharField(source="book.author", read_only=True)

    class Meta:
        model = ReadingSession
        fields = [
            "id", "user", "book", "book_title", "book_author", "occurred_on", "duration_minutes",
            "pages_read", "section", "reflection", "format", "reaction", "client_request_id", "created_at", "updated_at",
        ]
        read_only_fields = fields


class StrictWriteSerializer(serializers.Serializer):
    """Reject accidental field names, especially attempts to reassign ownership."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: "This field cannot be changed." for key in sorted(unknown)})
        return super().to_internal_value(data)


class ReadingBookWriteSerializer(StrictWriteSerializer):
    title = serializers.CharField(max_length=200)
    author = serializers.CharField(max_length=160, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=ReadingBook.Status.choices, default=ReadingBook.Status.READING)
    interests = serializers.ListField(
        child=serializers.ChoiceField(choices=INTERESTS), max_length=6, default=list,
    )

    def validate_interests(self, value):
        # Order and duplicate taps do not change the meaning of the interests.
        return sorted(set(value))


class ReadingBookCreateSerializer(ReadingBookWriteSerializer):
    user_id = serializers.IntegerField(min_value=1, required=False)
    client_request_id = serializers.UUIDField()


class ReadingSessionWriteSerializer(StrictWriteSerializer):
    occurred_on = serializers.DateField(required=False)
    duration_minutes = serializers.IntegerField(min_value=0, max_value=600, default=0)
    pages_read = serializers.IntegerField(min_value=0, max_value=2000, default=0)
    section = serializers.CharField(max_length=120, allow_blank=True, default="")
    reflection = serializers.CharField(max_length=3000, allow_blank=True, default="")
    format = serializers.ChoiceField(choices=ReadingSession.Format.choices, default=ReadingSession.Format.PRINT)
    reaction = serializers.ChoiceField(choices=["", *ReadingSession.Reaction.values], default="")

    def validate_occurred_on(self, value):
        today = timezone.localdate(timezone=household_timezone(self.context["target_user"]))
        if value > today:
            raise serializers.ValidationError("Reading cannot be logged for a future date.")
        return value

    def validate(self, attrs):
        def current(field):
            return attrs.get(field, getattr(self.instance, field, None))

        if not any(current(field) for field in ("duration_minutes", "pages_read", "section", "reflection")):
            raise serializers.ValidationError("Add minutes, pages, a chapter or section, or a reflection about your reading.")
        return attrs


class ReadingSessionCreateSerializer(ReadingSessionWriteSerializer):
    book = serializers.IntegerField(min_value=1)
    user_id = serializers.IntegerField(min_value=1, required=False)
    client_request_id = serializers.UUIDField()
