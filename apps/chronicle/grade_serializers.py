"""Validate and normalize school results independently of reward eligibility."""
from collections.abc import Mapping
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers


GRADE_LETTERS = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "P", "NP", "I")
GRADE_VALUE_FIELDS = {"score", "possible", "letter"}
INDIVIDUAL_GRADE_FIELDS = {"subject", "assessment", "grade_format", *GRADE_VALUE_FIELDS}


def _local_today():
    return timezone.localdate()


def canonical_decimal(value):
    """Use JSON-safe decimal strings without rounding or redundant zeros."""
    value = Decimal(value)
    if not value:
        return "0"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _normalized_mark(merged, supplied, *, descriptive_fields):
    grade_format = merged.get("grade_format")
    active = {
        "percentage": {"score"}, "points": {"score", "possible"}, "letter": {"letter"},
    }.get(grade_format, set())
    errors = {}
    for key in GRADE_VALUE_FIELDS - active:
        if supplied.get(key) not in (None, ""):
            errors[key] = f"This field is not used for {grade_format} grades."
    for key in (*descriptive_fields, "grade_format", *active):
        if merged.get(key) in (None, ""):
            errors[key] = "This field is required."
    if errors:
        raise serializers.ValidationError(errors)
    if grade_format == "percentage" and Decimal(merged["score"]) > 100:
        raise serializers.ValidationError({"score": "A percentage must be between 0 and 100."})
    if grade_format == "points" and Decimal(merged["possible"]) <= 0:
        raise serializers.ValidationError({"possible": "Possible points must be greater than zero."})
    normalized = {key: merged[key] for key in (*descriptive_fields, "grade_format", *active)}
    for key in active & {"score", "possible"}:
        normalized[key] = canonical_decimal(normalized[key])
    return normalized


class GradeValueSerializer(serializers.Serializer):
    grade_format = serializers.ChoiceField(choices=("percentage", "points", "letter"), required=False)
    score = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0"), required=False, allow_null=True,
    )
    possible = serializers.DecimalField(max_digits=18, decimal_places=6, required=False, allow_null=True)
    letter = serializers.ChoiceField(choices=GRADE_LETTERS, required=False, allow_blank=True, allow_null=True)


class StrictFieldsSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: "Unknown field." for key in sorted(unknown)})
        return super().to_internal_value(data)


class ReportCardSubjectSerializer(StrictFieldsSerializer, GradeValueSerializer):
    subject = serializers.CharField(max_length=80)

    def validate(self, data):
        # Even a partial report-card PATCH replaces every supplied subject row.
        return _normalized_mark(data, data, descriptive_fields=("subject",))


class ReportCardWriteSerializer(StrictFieldsSerializer):
    period_type = serializers.ChoiceField(choices=("quarter", "semester"))
    period_number = serializers.IntegerField(min_value=1, max_value=4)
    school_year = serializers.IntegerField(min_value=1, max_value=9998)
    subjects = ReportCardSubjectSerializer(many=True, min_length=1, max_length=30)

    def validate(self, data):
        entry = self.context.get("entry")
        previous = entry.metadata.get("report_card", {}) if entry is not None else {}
        merged = {**previous, **data}
        missing = {key: "This field is required." for key in self.fields if key not in merged}
        if missing:
            raise serializers.ValidationError(missing)
        if merged["period_type"] == "semester" and merged["period_number"] > 2:
            raise serializers.ValidationError({"period_number": "A semester must be 1 or 2."})
        subjects = [row["subject"].casefold() for row in merged["subjects"]]
        if len(set(subjects)) != len(subjects):
            raise serializers.ValidationError({"subjects": "Each subject can appear only once on a report card."})
        return merged


class GradeEntryWriteSerializer(GradeValueSerializer):
    subject = serializers.CharField(max_length=80, required=False)
    assessment = serializers.CharField(max_length=80, required=False)
    report_card = ReportCardWriteSerializer(required=False)
    reflection = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    occurred_on = serializers.DateField(required=False, default=_local_today)
    is_private = serializers.BooleanField(required=False, default=True)
    client_entry_id = serializers.UUIDField()

    def validate_occurred_on(self, day):
        if day > timezone.localdate():
            raise serializers.ValidationError("A grade's date cannot be in the future.")
        return day

    def validate(self, data):
        entry = self.context.get("entry")
        if entry is not None and "client_entry_id" in data:
            raise serializers.ValidationError({"client_entry_id": "The original save ID cannot be changed."})
        previous_is_report = entry is not None and "report_card" in entry.metadata
        if "report_card" in data or previous_is_report:
            if entry is not None and not previous_is_report:
                raise serializers.ValidationError({"report_card": "An individual grade cannot become a report card."})
            mixed = INDIVIDUAL_GRADE_FIELDS & set(self.initial_data)
            if mixed:
                raise serializers.ValidationError({key: "Individual grade fields cannot be used on a report card." for key in sorted(mixed)})
            unknown = set(self.initial_data) - {
                "report_card", "reflection", "occurred_on", "is_private", "client_entry_id", "user_id",
            }
            if unknown:
                raise serializers.ValidationError({key: "Unknown field." for key in sorted(unknown)})
            if "report_card" not in data:
                data["report_card"] = entry.metadata["report_card"]
            return data
        previous = entry.metadata.get("grade", {}) if entry is not None else {}
        # A format switch begins with only the subject/assessment; old points
        # or letters must not accidentally become a new format's result.
        switched = "grade_format" in data and data["grade_format"] != previous.get("grade_format")
        merged = {
            key: value for key, value in previous.items()
            if not switched or key not in GRADE_VALUE_FIELDS
        }
        merged.update({key: value for key, value in data.items() if key in INDIVIDUAL_GRADE_FIELDS})
        data["grade"] = _normalized_mark(merged, data, descriptive_fields=("subject", "assessment"))
        return data


class GradeListQuerySerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False, min_value=1, max_value=2**63 - 1)
    chapter_year = serializers.IntegerField(required=False, min_value=1, max_value=9999)
