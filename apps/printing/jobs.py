"""The MQTT-facing state machine: reports in, jobs and timeline rows out.

One :class:`PrinterJobTracker` per printer, owned by the listener. It holds
the small amount of "what have I already persisted" state that lets us take a
~1 message/second firehose and write only meaningful rows — roughly a hundred
per print rather than tens of thousands per day.

Job bracketing is driven by ``gcode_state`` transitions and nothing else.
``mc_percent`` is not trustworthy at a job boundary (it can still read 100
from the previous print at the instant a new one starts) and layer numbers
briefly read 0 during PREPARE.

The tracker is in-memory state in front of a database, and the process
holding it restarts — on every deploy, and whenever the container is
recycled. A print takes hours, so a restart lands *mid-print* routinely.
``_resume`` is what makes that survivable: on the first seeded report the
tracker asks the database whether this printer already has an open job for
the print it is currently watching, and re-attaches to it. Without that step
the restarted tracker sees "printing, named, and no open job", opens a
*second* row for one plate, force-closes the first as ``unknown``, and — if
the print is linked to a request — debits the budget twice for it. That
double row is what a parent sees in "Prints without a request".
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import NotificationType
from apps.notifications.services import notify

from . import hms as hms_decoder
from .constants import (
    PROGRESS_EVENT_STEP_PERCENT,
    STALE_JOB_MINUTES,
    UNNAMED_PRINT_GRACE_SECONDS,
)
from .matching import find_request, normalize_subtask_name
from .models import PrintJob, PrintJobEvent, PrintRequest
from .report import NOT_PRINTING_STATES, PrinterState
from .services import FORGE_LINK, PrintRequestService

logger = logging.getLogger(__name__)


class PrinterJobTracker:
    """Per-printer edge detector + persister.

    ``handle(state)`` is called once per merged report. Everything it does is
    conditional on something having actually changed.
    """

    def __init__(self, printer, *, clock=time.monotonic):
        self.printer = printer
        #: Injectable so tests can drive the unnamed-print grace window without
        #: sleeping.
        self._clock = clock
        #: When we first saw a print running with no ``subtask_name``.
        self.unnamed_since: float | None = None
        self.last_gcode_state = ""
        self.last_persisted_percent = -1
        self.last_hms_codes: set[str] = set()
        #: ``print_error`` latches for only a couple of seconds before the
        #: printer resets it to 0, so we capture it on the rising edge and
        #: hold it until the job closes. Polling for it loses the value.
        self.latched_print_error = 0
        self.open_job_id: int | None = None
        #: ``_resume`` runs exactly once, on the first seeded report. After
        #: that ``open_job_id`` is authoritative and re-querying would only
        #: cost a round trip per message.
        self._resumed = False

    # ------------------------------------------------------------------ #
    def handle(self, state: PrinterState) -> None:
        """Process one merged report. Safe to call on every message."""
        if not state.seeded:
            # Until pushall has answered we don't know subtask_name or
            # total_layer_num, so anything we wrote would be wrong.
            return

        self._latch_error(state)
        # Before reading our own in-memory edges: a restarted process has
        # none, and the printer is mid-print regardless.
        self._resume(state)

        was_printing = self.last_gcode_state not in NOT_PRINTING_STATES
        is_printing = state.is_printing

        if is_printing:
            self._ensure_job(state)
            self._record_hms(state)
            self._record_progress(state)
            self._record_pause_edge(state, was_printing)
        elif was_printing or self.open_job_id:
            self._close_job(state)

        self.last_gcode_state = state.gcode_state

    # ------------------------------------------------------------------ #
    def _latch_error(self, state: PrinterState) -> None:
        if state.print_error and state.print_error != self.latched_print_error:
            self.latched_print_error = state.print_error

    # ------------------------------------------------------------------ #
    def _resume(self, state: PrinterState) -> None:
        """Re-attach to the job row this print already has, once, on startup.

        ``open_job_id`` is in-memory state and this process restarts on every
        deploy, so "no open job in memory" does not mean "no open job". The
        printer, meanwhile, keeps reporting the same ``gcode_start_time`` and
        ``subtask_name`` right across our restart, so the row is recoverable —
        and recovering it is the difference between one print with one row and
        one print with two rows, two timeline halves, and two budget debits.

        Adopting also restores the edge state ``handle`` reads a line later,
        so both outcomes fall out of the ordinary bracket logic: still
        printing it and we carry on writing to the row; done with it (we came
        back to a printer already sitting in FINISH) and it closes on this
        very report with the terminal state the printer is actually
        reporting, rather than waiting hours for ``reconcile_stale_jobs`` to
        write it off as ``unknown``.
        """
        if self._resumed:
            return
        self._resumed = True

        job = PrintJob.objects.filter(
            printer=self.printer, finished_at__isnull=True,
        ).first()
        if job is None or not self._is_same_print(job, state):
            # Nothing of ours here. A row that belongs to some *other* print
            # is left alone deliberately — ``_force_close_stale`` closes it
            # when the next print opens, which is where that decision lives.
            return

        self._adopt(job, state)

    def _adopt(self, job: PrintJob, state: PrinterState) -> None:
        """Make ``job`` this tracker's open job again."""
        self.open_job_id = job.pk
        self.last_persisted_percent = job.percent_complete
        # Re-seed the edge detectors from the row so the first report after a
        # restart doesn't re-announce a pause, or re-log alerts that are still
        # active and were already written to this timeline.
        self.last_gcode_state = job.gcode_state_raw or state.gcode_state
        self.last_hms_codes = {
            code
            for code in job.events.filter(
                kind=PrintJobEvent.Kind.HMS,
            ).values_list("code", flat=True)
            if code
        }

        if not job.gcode_start_time and _print_identity(state.gcode_start_time):
            # Backfill rows written before we stored it, so the *next* restart
            # gets the strong identity check rather than the name fallback.
            job.gcode_start_time = state.gcode_start_time[:32]
            job.save(update_fields=["gcode_start_time", "updated_at"])

        PrintJobEvent.objects.create(
            job=job,
            kind=PrintJobEvent.Kind.NOTE,
            message="Picked this print back up after the listener restarted.",
            layer_num=state.layer_num,
            percent_complete=state.mc_percent,
            context={"gcode_state": state.gcode_state},
        )
        logger.info(
            "printing[%s]: resumed tracking job %s (%r) after a restart",
            self.printer.serial, job.pk, job.subtask_name,
        )

    def _is_same_print(self, job: PrintJob, state: PrinterState) -> bool:
        """Is ``job`` the row this exact print run already opened?

        Three rungs, strongest first, and the first rung that both sides can
        answer settles it — in *both* directions, so a mismatch is a real "no"
        rather than a fall-through to something weaker.

        ``gcode_start_time`` is the printer's own id for the run and is in the
        pushall snapshot, so it survives our restart; it is the rung that
        normally decides. ``task_id`` is only meaningful for cloud-started
        prints — a LAN start reports ``"0"``. With neither (a row written
        before we stored the start time, or firmware that reports neither) we
        fall back to the name, and then only for a row the printer was still
        reporting on recently: a re-print of the same plate must not absorb
        the row a power cut left open.
        """
        for reported, recorded in (
            (state.gcode_start_time, job.gcode_start_time),
            (state.task_id, job.task_id),
        ):
            reported, recorded = _print_identity(reported), _print_identity(recorded)
            if reported and recorded:
                return reported == recorded

        if normalize_subtask_name(state.subtask_name) != job.normalized_name:
            return False
        last_seen = job.last_report_at or job.started_at
        if last_seen is None:  # pragma: no cover - started_at is never null
            return False
        return timezone.now() - last_seen < timedelta(minutes=STALE_JOB_MINUTES)

    # ------------------------------------------------------------------ #
    def _ensure_job(self, state: PrinterState) -> PrintJob | None:
        """Open a job the first time we see a named, user-initiated print.

        Deliberately not a strict ``IDLE → RUNNING`` edge: when the listener
        starts up mid-print we still want a job row, and ``subtask_name`` can
        arrive a beat after the state flips. "Printing, named, and no open
        job" covers both cases with one condition — but only because
        ``_resume`` has already run, so "no open job" means the database
        agrees, not merely that this process was born a moment ago.
        """
        if self.open_job_id is not None:
            return None
        if not state.is_user_job:
            # Calibration / maintenance gcode. Real, but not a user's print.
            return None

        if not state.subtask_name:
            # A print can legitimately have no name: ``print.project_file``
            # defaults ``subtask_name`` to "", and a job started from the
            # printer's own screen may never set it. But the field also
            # routinely arrives a beat after ``gcode_state`` flips, so we wait
            # out a grace window before concluding there will never be one.
            # Opening a nameless job beats never showing the print at all —
            # a parent can link it by hand from the Forge.
            now = self._clock()
            if self.unnamed_since is None:
                self.unnamed_since = now
                return None
            if now - self.unnamed_since < UNNAMED_PRINT_GRACE_SECONDS:
                return None
        self.unnamed_since = None

        normalized = normalize_subtask_name(state.subtask_name)
        # find_request("") returns None, so a nameless job can never bind.
        request = find_request(normalized, family=self.printer.family)

        with transaction.atomic():
            # Defensive: close anything stale so the one-open-job-per-printer
            # constraint can't reject this insert (power cut mid-print leaves
            # a row open until the reconcile task or the next print).
            self._force_close_stale()

            job = PrintJob.objects.create(
                printer=self.printer,
                request=request,
                user=request.user if request else None,
                subtask_name=state.subtask_name[:200],
                normalized_name=normalized[:200],
                gcode_file=state.gcode_file[:255],
                task_id=state.task_id[:40],
                subtask_id=state.subtask_id[:40],
                gcode_start_time=state.gcode_start_time[:32],
                state=PrintJob.State.RUNNING,
                gcode_state_raw=state.gcode_state[:24],
                layer_num=state.layer_num,
                total_layer_num=state.total_layer_num,
                percent_complete=state.mc_percent,
                remaining_minutes=state.remaining_minutes or None,
                started_at=timezone.now(),
                last_report_at=timezone.now(),
                link_source=(
                    PrintJob.LinkSource.AUTO if request
                    else PrintJob.LinkSource.UNLINKED
                ),
            )
            PrintJobEvent.objects.create(
                job=job,
                kind=PrintJobEvent.Kind.STARTED,
                message=(
                    f"Started printing “{state.subtask_name}”"
                    if state.subtask_name
                    else f"Started an unnamed print on {self.printer.name}"
                ),
                layer_num=state.layer_num,
                percent_complete=state.mc_percent,
                context={
                    "normalized_name": normalized,
                    "plate_index": state.plate_index,
                    "print_type": state.print_type,
                    "total_layers": state.total_layer_num,
                },
            )
            if request is not None:
                PrintJobEvent.objects.create(
                    job=job,
                    kind=PrintJobEvent.Kind.LINKED,
                    message=f"Matched to “{request.title}” automatically",
                    context={"request_id": request.pk, "slug": request.slug},
                )
                request.status = PrintRequest.Status.PRINTING
                request.started_at = request.started_at or job.started_at
                request.print_count = (request.print_count or 0) + 1
                request.save(update_fields=[
                    "status", "started_at", "print_count", "updated_at",
                ])

        self.open_job_id = job.pk
        self.last_persisted_percent = state.mc_percent
        self.last_hms_codes = set()
        self.latched_print_error = 0

        if request is not None:
            notify(
                request.user,
                "Your print started",
                f"{request.title} is on the printer now"
                + (f" — about {state.remaining_minutes} min to go."
                   if state.remaining_minutes else "."),
                NotificationType.PRINT_STARTED,
                link=FORGE_LINK,
            )
        else:
            logger.info(
                "printing[%s]: started unmatched print %r (normalised %r) — "
                "a parent can link it from the Forge",
                self.printer.serial, state.subtask_name, normalized,
            )
        return job

    def _force_close_stale(self) -> None:
        stale = PrintJob.objects.filter(
            printer=self.printer, finished_at__isnull=True,
        ).exclude(pk=self.open_job_id or 0)
        for job in stale:
            job.state = PrintJob.State.UNKNOWN
            job.finished_at = timezone.now()
            job.duration_minutes = _elapsed_minutes(job.started_at, job.finished_at)
            job.save(update_fields=[
                "state", "finished_at", "duration_minutes", "updated_at",
            ])
            PrintJobEvent.objects.create(
                job=job,
                kind=PrintJobEvent.Kind.NOTE,
                message=(
                    "Closed automatically — the printer started a new print "
                    "while this one was still open."
                ),
            )
            PrintRequestService.close_out(job)

    # ------------------------------------------------------------------ #
    def _record_progress(self, state: PrinterState) -> None:
        """Persist progress, but only when the integer percentage moves.

        That caps writes at ~100 per print instead of one per second. Live
        layer counts and ETA still stream to the UI through the Redis
        snapshot, which is updated on every report.
        """
        if self.open_job_id is None:
            return
        if state.mc_percent == self.last_persisted_percent:
            return

        previous = self.last_persisted_percent
        self.last_persisted_percent = state.mc_percent
        PrintJob.objects.filter(pk=self.open_job_id).update(
            layer_num=state.layer_num,
            total_layer_num=state.total_layer_num,
            percent_complete=state.mc_percent,
            remaining_minutes=state.remaining_minutes or None,
            gcode_state_raw=state.gcode_state[:24],
            last_report_at=timezone.now(),
            updated_at=timezone.now(),
        )

        if previous < 0:
            return
        step = PROGRESS_EVENT_STEP_PERCENT
        if state.mc_percent // step > previous // step:
            PrintJobEvent.objects.create(
                job_id=self.open_job_id,
                kind=PrintJobEvent.Kind.PROGRESS,
                message=(
                    f"{state.mc_percent}% — layer {state.layer_num}"
                    f" of {state.total_layer_num}" if state.total_layer_num
                    else f"{state.mc_percent}%"
                ),
                layer_num=state.layer_num,
                percent_complete=state.mc_percent,
                context={"remaining_minutes": state.remaining_minutes},
            )

    # ------------------------------------------------------------------ #
    def _record_pause_edge(self, state: PrinterState, was_printing: bool) -> None:
        if self.open_job_id is None:
            return
        was_paused = self.last_gcode_state in ("PAUSE",)
        if state.is_paused and not was_paused:
            PrintJob.objects.filter(pk=self.open_job_id).update(
                state=PrintJob.State.PAUSED, updated_at=timezone.now(),
            )
            PrintJobEvent.objects.create(
                job_id=self.open_job_id,
                kind=PrintJobEvent.Kind.PAUSED,
                message="Print paused",
                layer_num=state.layer_num,
                percent_complete=state.mc_percent,
            )
        elif was_paused and not state.is_paused and was_printing:
            PrintJob.objects.filter(pk=self.open_job_id).update(
                state=PrintJob.State.RUNNING, updated_at=timezone.now(),
            )
            PrintJobEvent.objects.create(
                job_id=self.open_job_id,
                kind=PrintJobEvent.Kind.RESUMED,
                message="Print resumed",
                layer_num=state.layer_num,
                percent_complete=state.mc_percent,
            )

    # ------------------------------------------------------------------ #
    def _record_hms(self, state: PrinterState) -> None:
        """Write a timeline row for each newly-raised alert, decoded.

        This is what makes the timeline read "The AMS slot ran out of
        filament (unit A, slot 3)" instead of "0700_2000_0002_0001". Only
        *new* codes produce a row — the array is re-sent every second while
        an alert is active.
        """
        if self.open_job_id is None:
            return
        alerts = hms_decoder.describe_all(
            state.hms, model_name=self.printer.model_name,
        )
        current = {alert.code for alert in alerts}
        for alert in alerts:
            if alert.code in self.last_hms_codes:
                continue
            PrintJobEvent.objects.create(
                job_id=self.open_job_id,
                kind=PrintJobEvent.Kind.HMS,
                message=alert.message[:300],
                code=alert.code,
                severity=alert.severity,
                layer_num=state.layer_num,
                percent_complete=state.mc_percent,
                context=alert.as_context(),
            )
        self.last_hms_codes = current

    # ------------------------------------------------------------------ #
    def _close_job(self, state: PrinterState) -> None:
        """Bracket the job on the transition back into a not-printing state."""
        job_id, self.open_job_id = self.open_job_id, None
        self.last_persisted_percent = -1
        self.unnamed_since = None
        if job_id is None:
            self.latched_print_error = 0
            return

        try:
            job = PrintJob.objects.get(pk=job_id)
        except PrintJob.DoesNotExist:  # pragma: no cover - defensive
            self.latched_print_error = 0
            return
        if not job.is_open:
            self.latched_print_error = 0
            return

        error_alert = hms_decoder.describe_print_error(
            self.latched_print_error, model_name=self.printer.model_name,
        )
        cancelled = bool(error_alert and error_alert.cancelled)

        if state.gcode_state == "FINISH":
            job.state = PrintJob.State.FINISHED
        elif cancelled:
            job.state = PrintJob.State.CANCELLED
        elif state.gcode_state == "FAILED":
            job.state = PrintJob.State.FAILED
        else:
            # Straight to IDLE/OFFLINE without a FINISH or FAILED — a power
            # blip, or we missed the transition. Don't claim it succeeded.
            job.state = PrintJob.State.UNKNOWN

        hms_alerts = hms_decoder.describe_all(
            state.hms, model_name=self.printer.model_name,
        )
        summary = hms_decoder.summarize_failure(hms_alerts, error_alert)
        if job.state in (PrintJob.State.FAILED, PrintJob.State.UNKNOWN,
                         PrintJob.State.CANCELLED) and summary is not None:
            job.failure_code = summary.code[:40]
            job.failure_reason = summary.message[:300]
            job.failure_severity = summary.severity[:16]

        job.finished_at = timezone.now()
        job.duration_minutes = _elapsed_minutes(job.started_at, job.finished_at)
        job.gcode_state_raw = state.gcode_state[:24]
        job.percent_complete = state.mc_percent
        job.layer_num = state.layer_num or job.layer_num
        job.save(update_fields=[
            "state", "finished_at", "duration_minutes", "gcode_state_raw",
            "percent_complete", "layer_num", "failure_code", "failure_reason",
            "failure_severity", "updated_at",
        ])

        succeeded = job.state == PrintJob.State.FINISHED
        PrintJobEvent.objects.create(
            job=job,
            kind=(
                PrintJobEvent.Kind.FINISHED if succeeded
                else PrintJobEvent.Kind.FAILED
            ),
            message=_close_message(job, cancelled),
            code=job.failure_code,
            severity=job.failure_severity,
            layer_num=job.layer_num,
            percent_complete=job.percent_complete,
            context={
                "gcode_state": state.gcode_state,
                "print_error": self.latched_print_error or None,
                "cancelled": cancelled,
            },
        )
        self.latched_print_error = 0
        self.last_hms_codes = set()

        PrintRequestService.close_out(job)


def _print_identity(value: str) -> str:
    """Return a usable print-run id, or ``""`` for the firmware placeholders.

    ``task_id`` is ``"0"`` for a LAN-started print and ``gcode_start_time``
    reads ``"0"`` on an idle printer. Both mean "no id", not "id zero", and
    comparing two of them for equality would match every print to every other.
    """
    text = (value or "").strip()
    return "" if text in ("", "0", "-1") else text


def _elapsed_minutes(started_at, finished_at) -> int:
    if not started_at or not finished_at:
        return 0
    return max(0, int((finished_at - started_at).total_seconds() // 60))


def _close_message(job: PrintJob, cancelled: bool) -> str:
    if job.state == PrintJob.State.FINISHED:
        return f"Finished after {job.duration_minutes} min"
    if cancelled:
        return "Print cancelled on the printer"
    if job.failure_reason:
        return job.failure_reason
    if job.state == PrintJob.State.UNKNOWN:
        return "The printer stopped reporting before the print finished"
    return "Print failed"
