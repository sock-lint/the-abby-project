"""Serializers for the Forge.

Read serializers are ``ModelSerializer`` with ``read_only_fields = fields``
plus denormalised display extras; writes that route through a service use a
plain ``serializers.Serializer`` whose ``validated_data`` is unpacked into the
service call. Same split the rest of the codebase uses.

One rule with teeth: ``PrinterProfile.encrypted_secret`` is never rendered.
The write serializer accepts credentials as ``write_only`` fields and the
read serializer exposes only ``has_credentials`` — a boolean — so a child (or
a leaked response body) can never learn the printer's LAN access code or a
Bambu cloud token.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import (
    PrintBudget,
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintJobEvent,
    PrintRequest,
)


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class PrintRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_name", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    decided_by_name = serializers.CharField(
        source="decided_by.display_name", read_only=True, default=None,
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_kind_display = serializers.CharField(
        source="get_source_kind_display", read_only=True,
    )
    thumbnail = serializers.SerializerMethodField()
    model_file_url = serializers.SerializerMethodField()
    latest_job = serializers.SerializerMethodField()

    class Meta:
        model = PrintRequest
        fields = [
            "id", "user", "user_name", "username", "title", "source_kind",
            "source_kind_display", "source_url", "source_author", "thumbnail",
            "model_file_url", "color", "reason", "needed_by", "status",
            "status_display", "parent_notes", "slug", "plate_filename",
            "estimated_grams", "estimated_minutes", "decided_at",
            "decided_by", "decided_by_name", "started_at", "completed_at",
            "print_count", "latest_job", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_thumbnail(self, obj):
        """Prefer our cached copy; fall back to the model host's URL.

        Model hosts rotate CDN URLs, so a card that only ever pointed at the
        remote og:image goes blank weeks later. The cached copy is authoritative
        once ``cache_request_thumbnail`` has run.
        """
        if obj.thumbnail:
            try:
                return obj.thumbnail.url
            except ValueError:  # pragma: no cover - storage misconfiguration
                pass
        return obj.thumbnail_url or None

    def get_model_file_url(self, obj):
        if not obj.model_file:
            return None
        try:
            return obj.model_file.url
        except ValueError:  # pragma: no cover
            return None

    def get_latest_job(self, obj):
        """Compact progress summary for the card, newest job first."""
        job = next(iter(obj.jobs.all()[:1]), None)
        if job is None:
            return None
        return {
            "id": job.id,
            "state": job.state,
            "percent_complete": job.percent_complete,
            "layer_num": job.layer_num,
            "total_layer_num": job.total_layer_num,
            "remaining_minutes": job.remaining_minutes,
            "failure_reason": job.failure_reason or None,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }


class PrintRequestWriteSerializer(serializers.Serializer):
    """Child (or parent-on-behalf) submitting a new request."""

    title = serializers.CharField(max_length=160, required=False, allow_blank=True)
    source_url = serializers.URLField(max_length=500, required=False, allow_blank=True)
    model_file = serializers.FileField(required=False, allow_null=True)
    color = serializers.CharField(max_length=40)
    reason = serializers.CharField(max_length=2000)
    needed_by = serializers.DateField(required=False, allow_null=True)
    user_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get("source_url") and not attrs.get("model_file"):
            raise serializers.ValidationError(
                "Give a link to the model, or upload the file itself.",
            )
        return attrs


class PrintRequestEditSerializer(serializers.ModelSerializer):
    """The narrow set a request's owner may still change before it prints."""

    class Meta:
        model = PrintRequest
        fields = ["title", "color", "reason", "needed_by"]


class PrintRequestApproveSerializer(serializers.Serializer):
    estimated_grams = serializers.DecimalField(
        max_digits=7, decimal_places=2, required=False, allow_null=True, min_value=0,
    )
    estimated_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=0,
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    force = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Approve even though it exceeds the monthly budget.",
    )


class PrintRequestRejectSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class LinkPreviewSerializer(serializers.Serializer):
    """Scrape a model link before submitting, so the card previews properly."""

    url = serializers.URLField(max_length=500)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
class PrintJobEventSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = PrintJobEvent
        fields = [
            "id", "kind", "kind_display", "message", "code", "severity",
            "layer_num", "percent_complete", "context", "created_at",
        ]
        read_only_fields = fields


class PrintJobSerializer(serializers.ModelSerializer):
    printer_name = serializers.CharField(source="printer.name", read_only=True)
    request_title = serializers.CharField(
        source="request.title", read_only=True, default=None,
    )
    user_name = serializers.CharField(
        source="user.display_name", read_only=True, default=None,
    )
    state_display = serializers.CharField(source="get_state_display", read_only=True)
    events = PrintJobEventSerializer(many=True, read_only=True)

    class Meta:
        model = PrintJob
        fields = [
            "id", "printer", "printer_name", "request", "request_title",
            "user", "user_name", "subtask_name", "normalized_name",
            "gcode_file", "task_id", "state", "state_display",
            "gcode_state_raw", "layer_num", "total_layer_num",
            "percent_complete", "remaining_minutes", "started_at",
            "finished_at", "duration_minutes", "last_report_at",
            "link_source", "failure_code", "failure_reason",
            "failure_severity", "grams_debited", "minutes_debited",
            "events", "created_at",
        ]
        read_only_fields = fields


class PrintJobLinkSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #
class PrintBudgetSerializer(serializers.ModelSerializer):
    """The budget row plus this month's rolled-up usage.

    ``*_remaining`` is ``null`` when that dimension is uncapped, and may be
    negative when a parent approved past the cap with ``force`` or a print
    overshot its estimate — we surface the overage rather than clamping it.
    """

    user_name = serializers.CharField(source="user.display_name", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    period_month = serializers.SerializerMethodField()
    grams_used = serializers.SerializerMethodField()
    minutes_used = serializers.SerializerMethodField()
    grams_remaining = serializers.SerializerMethodField()
    minutes_remaining = serializers.SerializerMethodField()

    class Meta:
        model = PrintBudget
        fields = [
            "id", "user", "user_name", "username", "grams_per_month",
            "minutes_per_month", "is_active", "notes", "period_month",
            "grams_used", "minutes_used", "grams_remaining",
            "minutes_remaining", "updated_at",
        ]
        read_only_fields = [
            "id", "user", "user_name", "username", "period_month",
            "grams_used", "minutes_used", "grams_remaining",
            "minutes_remaining", "updated_at",
        ]

    def _summary(self, obj):
        from .budget import PrintBudgetService

        cached = getattr(obj, "_summary_cache", None)
        if cached is None:
            cached = PrintBudgetService.summary(obj.user)
            obj._summary_cache = cached
        return cached

    def get_period_month(self, obj):
        return self._summary(obj)["period_month"]

    def get_grams_used(self, obj):
        return self._summary(obj)["grams_used"]

    def get_minutes_used(self, obj):
        return self._summary(obj)["minutes_used"]

    def get_grams_remaining(self, obj):
        return self._summary(obj)["grams_remaining"]

    def get_minutes_remaining(self, obj):
        return self._summary(obj)["minutes_remaining"]


class PrintBudgetAdjustSerializer(serializers.Serializer):
    grams = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, default=0,
    )
    minutes = serializers.IntegerField(required=False, default=0)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)


class PrintBudgetLedgerSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    request_title = serializers.CharField(
        source="request.title", read_only=True, default=None,
    )

    class Meta:
        model = PrintBudgetLedger
        fields = [
            "id", "user", "request", "request_title", "job", "period_month",
            "grams", "minutes", "reason", "reason_display", "note", "created_at",
        ]
        read_only_fields = fields


# --------------------------------------------------------------------------- #
# Printers
# --------------------------------------------------------------------------- #
class PrinterProfileSerializer(serializers.ModelSerializer):
    """Read shape. Note the absence of ``encrypted_secret`` — deliberate."""

    transport_display = serializers.CharField(
        source="get_transport_display", read_only=True,
    )
    has_credentials = serializers.BooleanField(read_only=True)
    live = serializers.SerializerMethodField()

    class Meta:
        model = PrinterProfile
        fields = [
            "id", "name", "serial", "model_name", "transport",
            "transport_display", "host", "port", "is_active",
            "has_credentials", "last_report_at", "last_gcode_state",
            "last_error", "live", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "has_credentials", "last_report_at", "last_gcode_state",
            "last_error", "live", "created_at", "updated_at",
        ]

    def get_live(self, obj):
        """Latest snapshot from the listener's fan-out cache, if it's warm.

        ``None`` means the listener isn't currently connected to this printer
        — the UI renders that as "offline" rather than as stale numbers.
        """
        from .fanout import read_state

        return read_state(obj.serial)


class PrinterProfileWriteSerializer(serializers.Serializer):
    """Create/update. Credentials in, never out."""

    name = serializers.CharField(max_length=80)
    serial = serializers.CharField(max_length=32)
    model_name = serializers.CharField(max_length=40, required=False, allow_blank=True)
    transport = serializers.ChoiceField(
        choices=PrinterProfile.Transport.choices,
        required=False,
        default=PrinterProfile.Transport.LOCAL,
    )
    host = serializers.CharField(max_length=255, required=False, allow_blank=True)
    port = serializers.IntegerField(required=False, min_value=1, max_value=65535)
    is_active = serializers.BooleanField(required=False, default=True)

    # Write-only credentials. Omitting one leaves the stored value alone so a
    # PATCH that only renames the printer doesn't wipe its access code.
    access_code = serializers.CharField(
        max_length=64, required=False, allow_blank=True, write_only=True,
    )
    cloud_user_id = serializers.CharField(
        max_length=64, required=False, allow_blank=True, write_only=True,
    )
    cloud_token = serializers.CharField(
        max_length=4096, required=False, allow_blank=True, write_only=True,
    )
