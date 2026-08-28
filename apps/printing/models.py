"""Models for the 3D print request subsystem.

Shape of the feature, in one paragraph: a child submits a **PrintRequest**
(a MakerWorld/Printables link or an uploaded model, plus colour, reason and
a needed-by date). A parent approves it, which mints a deterministic
``slug`` + ``plate_filename`` and tells the parent exactly what to name the
sliced plate. The parent slices and prints from Bambu Studio or Handy —
nothing about their workflow changes. Our single MQTT listener sees
``gcode_state`` flip to ``RUNNING`` on a **PrinterProfile**, reads
``subtask_name``, and opens a **PrintJob** linked to the matching request by
exact slug. Progress, layers and remaining time stream into
**PrintJobEvent** rows until FINISH or FAILED, at which point the request
closes out and a **PrintBudgetLedger** row debits the child's monthly
**PrintBudget**.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from config.base_models import (
    ApprovalWorkflowModel,
    CreatedAtModel,
    TimestampedModel,
)

from .constants import ACCESS_CODE_LOCATION


class PrinterProfile(TimestampedModel):
    """One physical printer, owned by a family.

    Per-family content (same shape as ``Reward`` / ``Chore`` /
    ``ProjectTemplate``): a deployment hosts many unrelated households and a
    printer belongs to exactly one of them. Unlike those three this model is
    new, so ``family`` is non-null from ``0001_initial`` — there are no
    legacy rows to backfill and the 3-step migration dance doesn't apply.
    The ``save()`` auto-attach below is still here as defense in depth for
    fixtures and tests that construct rows without a family.

    Credentials (LAN access code, or the cloud user id + token) live in
    ``encrypted_secret`` as a Fernet-encrypted JSON blob — never in
    cleartext columns, and never rendered by a serializer. See
    ``apps/printing/crypto.py``.
    """

    class Transport(models.TextChoices):
        LOCAL = "local", "Local MQTT (LAN)"
        CLOUD = "cloud", "Bambu Cloud MQTT"

    family = models.ForeignKey(
        "families.Family",
        on_delete=models.CASCADE,
        related_name="printers",
    )
    name = models.CharField(max_length=80, help_text="Display name, e.g. 'X1C in the garage'.")
    serial = models.CharField(
        max_length=32,
        help_text="Printer serial number. Forms the MQTT topic: device/<serial>/report.",
    )
    model_name = models.CharField(
        max_length=40,
        default="X1C",
        help_text="Informational only — X1C / X1E / P1S / A1. Does not change protocol handling.",
    )
    transport = models.CharField(
        max_length=8,
        choices=Transport.choices,
        default=Transport.LOCAL,
        help_text=(
            "Which MQTT transport the listener opens. Swapping local↔cloud is a "
            "config change; both speak the same report schema."
        ),
    )
    host = models.CharField(
        max_length=255,
        blank=True,
        help_text="LAN IP or hostname. Local transport only — cloud derives its host from settings.",
    )
    port = models.PositiveIntegerField(
        default=8883,
        help_text="MQTT TLS port. 8883 for both local and Bambu Cloud.",
    )
    encrypted_secret = models.BinaryField(
        blank=True,
        default=b"",
        help_text=(
            "Fernet-encrypted JSON: {access_code, cloud_user_id, cloud_token}. "
            "Written via PrinterProfile.set_secrets(); never serialized out."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive printers are skipped by the listener supervisor.",
    )

    # --- Observed state, written by the listener ---------------------------
    last_report_at = models.DateTimeField(null=True, blank=True)
    last_gcode_state = models.CharField(max_length=24, blank=True)
    last_error = models.CharField(
        max_length=300,
        blank=True,
        help_text="Last connection/transport error, surfaced in the parent UI.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "serial"],
                name="uniq_printer_serial_per_family",
            ),
        ]
        indexes = [models.Index(fields=["serial"])]

    def __str__(self):
        return f"{self.name} ({self.serial})"

    def save(self, *args, **kwargs):
        # Defense in depth, mirroring Reward.save() / ProjectTemplate.save():
        # production paths (PrinterProfileViewSet.perform_create) always stamp
        # an explicit family. Fixtures and tests that don't get routed to the
        # default family rather than raising IntegrityError.
        if self.family_id is None:
            from apps.families.models import Family

            family, _ = Family.objects.get_or_create(
                slug="default-family",
                defaults={"name": "Default Family"},
            )
            self.family = family
        super().save(*args, **kwargs)

    # --- Secrets ----------------------------------------------------------
    def get_secrets(self) -> dict:
        """Decrypt and return the credential blob (``{}`` when unset/undecryptable)."""
        from .crypto import decrypt_secrets

        return decrypt_secrets(self.encrypted_secret)

    def set_secrets(self, **values) -> None:
        """Merge ``values`` into the encrypted credential blob.

        Does NOT save — the caller owns the transaction. Passing a key with
        value ``None`` leaves the existing value alone (so a PATCH that omits
        the access code doesn't wipe it); pass ``""`` to clear one.
        """
        from .crypto import encrypt_secrets

        current = self.get_secrets()
        for key, value in values.items():
            if value is None:
                continue
            current[key] = value
        self.encrypted_secret = encrypt_secrets(current)

    #: What the parent has to supply, per transport, before the listener can
    #: open a connection. Keys are the *write-serializer field names* so the
    #: API can hang a validation error on the exact input that is blank.
    #: ``host`` lives on the model; the rest live in ``encrypted_secret``.
    REQUIRED_BY_TRANSPORT = {
        Transport.LOCAL: ("host", "access_code"),
        Transport.CLOUD: ("cloud_user_id", "cloud_token"),
    }

    @property
    def missing_credentials(self) -> list[str]:
        """Field names still blank for this printer's transport.

        Empty means the listener has everything it needs to dial. This is the
        primitive; ``has_credentials`` and ``credential_hint`` are both
        derived from it, so the API, the parent UI and the listener's
        skip-reason can never disagree about what is wrong.
        """
        present = {**self.get_secrets(), "host": self.host}
        # ``.get`` rather than ``[]``: this property runs inside the listener
        # supervisor's loop, and one row with an out-of-choices transport must
        # not take down every other printer with a KeyError.
        required = self.REQUIRED_BY_TRANSPORT.get(
            self.transport, self.REQUIRED_BY_TRANSPORT[self.Transport.LOCAL],
        )
        return [field for field in required if not present.get(field)]

    @property
    def has_credentials(self) -> bool:
        return not self.missing_credentials

    @property
    def credential_hint(self) -> str:
        """One sentence naming what is missing, or ``""`` when nothing is.

        Rendered on the printer card and stamped into ``last_error`` by the
        listener supervisor, because "it doesn't work" without saying which
        field is blank is the single most common way this feature strands a
        parent.
        """
        missing = self.missing_credentials
        if not missing:
            return ""
        if self.transport == self.Transport.CLOUD:
            wanted = " and ".join(
                {"cloud_user_id": "user id", "cloud_token": "access token"}[field]
                for field in missing
            )
            return f"No Bambu Cloud {wanted} saved."
        if missing == ["host"]:
            return "No LAN address saved — the printer's IP is on its network screen."
        prefix = (
            "No LAN address or access code saved"
            if len(missing) > 1
            else "No LAN access code saved"
        )
        return f"{prefix} — {ACCESS_CODE_LOCATION}"


class PrintRequest(ApprovalWorkflowModel, TimestampedModel):
    """A child's "please print this for me".

    Inherits ``decided_at`` / ``decided_by`` from ``ApprovalWorkflowModel``
    like every other submit-then-approve model in the codebase
    (ChoreCompletion, HomeworkSubmission, RewardRedemption, ExchangeRequest).

    ``slug`` is the load-bearing field: it is minted exactly once, at
    approval, and is what makes job matching deterministic. Nothing else in
    the system is allowed to write it.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PRINTING = "printing", "Printing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    #: Statuses from which a print can start (i.e. a job may bind to them).
    #: ``FAILED`` is included so a re-print of a failed plate re-binds
    #: without the parent having to re-approve.
    BINDABLE_STATUSES = (Status.APPROVED, Status.PRINTING, Status.FAILED, Status.COMPLETED)

    class SourceKind(models.TextChoices):
        MAKERWORLD = "makerworld", "MakerWorld"
        PRINTABLES = "printables", "Printables"
        THINGIVERSE = "thingiverse", "Thingiverse"
        OTHER_URL = "other_url", "Other link"
        UPLOAD = "upload", "Uploaded model"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="print_requests",
    )

    # --- What she wants ---------------------------------------------------
    title = models.CharField(
        max_length=160,
        help_text="Scraped from the link's OpenGraph title, or typed for uploads.",
    )
    source_kind = models.CharField(
        max_length=16,
        choices=SourceKind.choices,
        default=SourceKind.OTHER_URL,
    )
    source_url = models.URLField(max_length=500, blank=True)
    source_author = models.CharField(max_length=120, blank=True)
    thumbnail_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Remote og:image URL. Kept even after we cache a local copy, as provenance.",
    )
    thumbnail = models.ImageField(
        upload_to="print-requests/thumbs/",
        blank=True,
        null=True,
        help_text=(
            "Locally cached copy of thumbnail_url, fetched by "
            "apps.printing.tasks.cache_request_thumbnail. Preferred by the "
            "serializer so cards keep working when the model host rotates URLs."
        ),
    )
    model_file = models.FileField(
        upload_to="print-requests/models/",
        blank=True,
        null=True,
        help_text="Uploaded STL/3MF/step. Only set for SourceKind.UPLOAD.",
    )
    color = models.CharField(max_length=40, help_text="Free text — 'glow in the dark green'.")
    reason = models.TextField(help_text="Why she wants it. Required — this is the point of the flow.")
    needed_by = models.DateField(null=True, blank=True)

    # --- Decision ---------------------------------------------------------
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    parent_notes = models.TextField(blank=True)

    # --- Deterministic matching ------------------------------------------
    slug = models.SlugField(
        max_length=80,
        blank=True,
        default="",
        help_text=(
            "Minted once at approval, e.g. 'req-0042-dragon'. Empty until then. "
            "Unique among non-empty values — see the partial constraint in Meta."
        ),
    )
    plate_filename = models.CharField(
        max_length=120,
        blank=True,
        help_text="What the parent must name the sliced plate, e.g. 'req-0042-dragon.3mf'.",
    )

    # --- Budget estimates, entered by the parent from the slicer ----------
    estimated_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Filament estimate from Bambu Studio, in grams. The MQTT report does "
            "NOT carry consumed filament, so this is what the budget debits."
        ),
    )
    estimated_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Print-time estimate from the slicer, in minutes. Informational at approval.",
    )

    # --- Lifecycle timestamps --------------------------------------------
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    print_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of jobs that have bound to this request (re-prints included).",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Partial unique: many requests sit at slug="" before approval, so a
            # plain unique=True would collide on the second pending row.
            models.UniqueConstraint(
                fields=["slug"],
                condition=~models.Q(slug=""),
                name="uniq_print_request_slug_when_set",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "needed_by"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    @property
    def is_open(self) -> bool:
        """True while the request is still expected to produce a print."""
        return self.status in (
            self.Status.APPROVED,
            self.Status.PRINTING,
            self.Status.FAILED,
        )


class PrintBudget(TimestampedModel):
    """A child's monthly filament + print-time allowance.

    ``None`` on either cap means "no cap on that dimension" — a family that
    only cares about grams leaves ``minutes_per_month`` null. Zero is a real
    value meaning "nothing this month", which is why these are nullable
    rather than defaulting to 0.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="print_budget",
    )
    grams_per_month = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Filament allowance per calendar month, in grams. Null = unlimited.",
    )
    minutes_per_month = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Print-time allowance per calendar month, in minutes. Null = unlimited.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="When false the caps are ignored entirely (still ledgered, never enforced).",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Print budget for {self.user}"


class PrintBudgetLedger(CreatedAtModel):
    """Append-only record of budget consumption.

    Deliberately NOT a ``config.services.BaseLedgerService`` subclass. That
    base assumes a single ``amount`` column (it is shared by ``PaymentLedger``
    and ``CoinLedger``, both single-currency); a print consumes two
    independent resources — grams of filament and minutes of machine time —
    and a family may cap either, both, or neither. Splitting into two
    single-amount ledgers would double every write and make a single print's
    two debits reconcilable only by timestamp. ``PrintBudgetService``
    therefore implements ``get_usage`` / ``get_remaining`` directly over this
    two-column shape.

    Positive values consume budget; negative values return it (a refund after
    a parent voids a bad debit).
    """

    class Reason(models.TextChoices):
        PRINT_COMPLETED = "print_completed", "Print completed"
        PRINT_FAILED = "print_failed", "Print failed (partial)"
        ADJUSTMENT = "adjustment", "Manual adjustment"
        REFUND = "refund", "Refund"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="print_budget_entries",
    )
    request = models.ForeignKey(
        "printing.PrintRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_entries",
    )
    job = models.ForeignKey(
        "printing.PrintJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_entries",
    )
    period_month = models.DateField(
        db_index=True,
        help_text=(
            "First day of the local (America/Phoenix) month this entry counts "
            "against. Denormalised so the monthly rollup is an indexed equality "
            "filter rather than a timezone-sensitive range scan over created_at."
        ),
    )
    grams = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    minutes = models.IntegerField(default=0)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Parent who made a manual adjustment; null for automatic debits.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "period_month"])]

    def __str__(self):
        return f"{self.user} {self.reason}: {self.grams}g / {self.minutes}min"


class PrintJob(TimestampedModel):
    """One observed print on a printer.

    Created by the MQTT listener the first time it sees a printer in a
    running state with a ``subtask_name``. ``request`` is filled in
    automatically when the normalised subtask name matches a request slug,
    and can be set later through the manual link endpoint for prints started
    from Handy without the minted filename.

    ``user`` is denormalised from ``request.user`` so
    ``RoleFilteredQuerySetMixin`` can scope the queryset with a single join.
    An unmatched job has ``user=None`` and is visible to parents only.
    """

    class State(models.TextChoices):
        RUNNING = "running", "Running"
        PAUSED = "paused", "Paused"
        FINISHED = "finished", "Finished"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        UNKNOWN = "unknown", "Unknown"

    #: States after which no further report updates the job.
    TERMINAL_STATES = (
        State.FINISHED, State.FAILED, State.CANCELLED, State.UNKNOWN,
    )

    class LinkSource(models.TextChoices):
        AUTO = "auto", "Matched automatically"
        MANUAL = "manual", "Linked by a parent"
        UNLINKED = "unlinked", "Not linked"

    printer = models.ForeignKey(
        PrinterProfile,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    request = models.ForeignKey(
        PrintRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="print_jobs",
        help_text="Denormalised from request.user at link time; null while unmatched.",
    )

    # --- Identity from the report ----------------------------------------
    subtask_name = models.CharField(
        max_length=200,
        help_text="Raw print.subtask_name as reported. Never normalised in place.",
    )
    normalized_name = models.CharField(
        max_length=200,
        db_index=True,
        help_text="subtask_name run through matching.normalize_subtask_name(). What we match on.",
    )
    gcode_file = models.CharField(max_length=255, blank=True)
    task_id = models.CharField(max_length=40, blank=True, db_index=True)
    subtask_id = models.CharField(max_length=40, blank=True)

    # --- Progress ---------------------------------------------------------
    state = models.CharField(
        max_length=12,
        choices=State.choices,
        default=State.RUNNING,
        db_index=True,
    )
    gcode_state_raw = models.CharField(
        max_length=24,
        blank=True,
        help_text="The literal print.gcode_state string, kept for diagnosis when firmware adds values.",
    )
    layer_num = models.PositiveIntegerField(default=0)
    total_layer_num = models.PositiveIntegerField(default=0)
    percent_complete = models.PositiveSmallIntegerField(default=0)
    remaining_minutes = models.IntegerField(null=True, blank=True)

    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    last_report_at = models.DateTimeField(null=True, blank=True)

    link_source = models.CharField(
        max_length=10,
        choices=LinkSource.choices,
        default=LinkSource.UNLINKED,
    )

    # --- Failure ----------------------------------------------------------
    failure_code = models.CharField(
        max_length=40,
        blank=True,
        help_text="Canonical HMS code, e.g. '0300_0100_0002_0001', or 'print_error:<n>'.",
    )
    failure_reason = models.CharField(
        max_length=300,
        blank=True,
        help_text="Human-readable decode. This is what the timeline shows instead of a number.",
    )
    failure_severity = models.CharField(max_length=16, blank=True)

    # --- Budget close-out -------------------------------------------------
    grams_debited = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )
    minutes_debited = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            # One open (unfinished) job per printer. The X1 prints one plate at
            # a time, so a second open row means we failed to close the first —
            # better to reject the write than to silently double-track.
            models.UniqueConstraint(
                fields=["printer"],
                condition=models.Q(finished_at__isnull=True),
                name="uniq_open_job_per_printer",
            ),
        ]
        indexes = [
            models.Index(fields=["request", "-started_at"]),
            models.Index(fields=["user", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.subtask_name} on {self.printer.name} ({self.state})"

    @property
    def is_open(self) -> bool:
        return self.finished_at is None


class PrintJobEvent(CreatedAtModel):
    """One row on a job's timeline.

    Deliberately narrow and append-only: this is what the UI renders as "what
    happened, in order", and it is the surface where a decoded HMS message
    replaces a raw code.
    """

    class Kind(models.TextChoices):
        STARTED = "started", "Started"
        PROGRESS = "progress", "Progress"
        PAUSED = "paused", "Paused"
        RESUMED = "resumed", "Resumed"
        HMS = "hms", "Printer alert"
        FINISHED = "finished", "Finished"
        FAILED = "failed", "Failed"
        LINKED = "linked", "Linked to request"
        UNLINKED = "unlinked", "Unlinked from request"
        BUDGET = "budget", "Budget debited"
        NOTE = "note", "Note"

    job = models.ForeignKey(
        PrintJob,
        on_delete=models.CASCADE,
        related_name="events",
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    message = models.CharField(max_length=300)
    code = models.CharField(
        max_length=40,
        blank=True,
        help_text="Canonical HMS code when kind=hms/failed; empty otherwise.",
    )
    severity = models.CharField(max_length=16, blank=True)
    layer_num = models.PositiveIntegerField(null=True, blank=True)
    percent_complete = models.PositiveSmallIntegerField(null=True, blank=True)
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Free-form extras (raw hms attr/code pair, remaining minutes, debit math).",
    )

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["job", "created_at"])]

    def __str__(self):
        return f"[{self.kind}] {self.message}"
