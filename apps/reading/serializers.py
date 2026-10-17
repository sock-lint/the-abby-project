from django.utils import timezone
from rest_framework import serializers

from apps.quests.activity import household_timezone

from .constants import (
    DISCOVERY_FEEDBACK_CHOICES, DISCOVERY_FORMATS, DISCOVERY_LENGTHS,
    DISCOVERY_MOODS, DISCOVERY_STYLES, DISCOVERY_THEMES, INTERESTS,
)
from .models import ReadingBook, ReadingFamilySuggestion, ReadingSession
from .recommendations import catalog_entry_for_book


class ReadingBookSerializer(serializers.ModelSerializer):
    catalog_entry = serializers.SerializerMethodField()

    def get_catalog_entry(self, book):
        return catalog_entry_for_book(book)

    class Meta:
        model = ReadingBook
        fields = ["id", "user", "title", "author", "status", "interests", "client_request_id", "created_at", "updated_at", "catalog_entry"]
        read_only_fields = fields


class ReadingSessionSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    book_author = serializers.CharField(source="book.author", read_only=True)
    reading_reward = serializers.SerializerMethodField()

    def get_reading_reward(self, session):
        reward = getattr(session, "reading_daily_reward", None)
        if reward is None or reward.awarded_at is None:
            return None
        return {
            "day": reward.day.isoformat(), "xp_awarded": reward.xp_awarded, "coins_awarded": reward.coins_awarded,
        }

    class Meta:
        model = ReadingSession
        fields = [
            "id", "user", "book", "book_title", "book_author", "occurred_on", "duration_minutes",
            "pages_read", "section", "reflection", "format", "reaction", "client_request_id", "created_at", "updated_at",
            "reading_reward",
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


def catalog_entry_by_id(catalog_id):
    from .catalog import BOOK_CATALOG

    entry = next((book for book in BOOK_CATALOG if book["id"] == catalog_id), None)
    return catalog_entry_for_book(entry) if entry else None


class CatalogIdField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(max_length=80, **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if catalog_entry_by_id(value) is None:
            raise serializers.ValidationError("Choose a book from the discovery catalog.")
        return value


class DiscoveryFilterSerializer(serializers.Serializer):
    interest = serializers.ChoiceField(choices=INTERESTS, required=False)
    mood = serializers.ChoiceField(choices=DISCOVERY_MOODS, required=False)
    style = serializers.ChoiceField(choices=DISCOVERY_STYLES, required=False)
    book_format = serializers.ChoiceField(choices=DISCOVERY_FORMATS, required=False)
    length = serializers.ChoiceField(choices=DISCOVERY_LENGTHS, required=False)
    theme = serializers.ChoiceField(choices=DISCOVERY_THEMES, required=False)
    q = serializers.CharField(max_length=160, allow_blank=True, default="")
    similar_to = CatalogIdField(required=False)
    rotation = serializers.IntegerField(min_value=0, max_value=1000, default=0)


class DiscoveryFeedbackWriteSerializer(StrictWriteSerializer):
    user_id = serializers.IntegerField(min_value=1, required=False)
    catalog_id = CatalogIdField()
    choice = serializers.ChoiceField(choices=["", *DISCOVERY_FEEDBACK_CHOICES])


class FamilySuggestionCreateSerializer(StrictWriteSerializer):
    user_id = serializers.IntegerField(min_value=1)
    catalog_id = CatalogIdField()
    message = serializers.CharField(max_length=500, allow_blank=True, default="")
    client_request_id = serializers.UUIDField()


class FamilySuggestionWriteSerializer(StrictWriteSerializer):
    status = serializers.ChoiceField(choices=[ReadingFamilySuggestion.Status.DISMISSED])


class ReadingFamilySuggestionSerializer(serializers.ModelSerializer):
    suggested_by = serializers.SerializerMethodField()
    catalog_entry = serializers.SerializerMethodField()
    on_shelf = serializers.SerializerMethodField()

    def get_suggested_by(self, suggestion):
        return {"id": suggestion.suggested_by_id, "display_name": suggestion.author_name or "A parent"}

    def get_catalog_entry(self, suggestion):
        return catalog_entry_by_id(suggestion.catalog_id)

    def get_on_shelf(self, suggestion):
        # A list is scoped to one reader; share one shelf query across its rows.
        owned = self.context.setdefault("_owned_catalog_ids", {})
        if suggestion.user_id not in owned:
            owned[suggestion.user_id] = {
                entry["id"] for book in ReadingBook.objects.filter(user_id=suggestion.user_id).values("title", "author")
                if (entry := catalog_entry_for_book(book)) is not None
            }
        return suggestion.catalog_id in owned[suggestion.user_id]

    class Meta:
        model = ReadingFamilySuggestion
        fields = [
            "id", "user", "suggested_by", "catalog_id", "catalog_entry", "message", "status",
            "client_request_id", "created_at", "updated_at", "on_shelf",
        ]
        read_only_fields = fields
