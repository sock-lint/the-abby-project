"""End-to-end MQTT ingest, with no broker anywhere.

``InMemoryTransport`` + ``PrinterListener.process`` run the *real* pipeline —
delta merge, job bracketing, HMS decode, budget close-out — against captured
payload shapes. If any of this drifts, these fail.

Invariants pinned here:

1. A ``msg: 1`` delta merges onto previous state; absent keys keep their old
   value rather than resetting to zero.
2. Nothing is written until ``pushall`` has answered (``msg: 0``), because
   before that we don't know ``subtask_name`` or ``total_layer_num``.
3. Command acknowledgements and cloud ``event`` envelopes never reach the
   state merge.
4. A print whose ``subtask_name`` is the minted plate name links to its
   request automatically, and the request moves to ``printing``.
5. FINISH closes the request and debits the full estimate.
6. FAILED closes it with a *decoded* reason, and debits proportionally.
7. A user cancel (``print_error`` 50348044) is not a failure — the request
   goes back to approved so it can be re-printed.
8. Progress rows are throttled; a 100-report print does not write 100 rows.
9. An unmatched print still produces a job a parent can link by hand.
10. A listener that restarts mid-print re-attaches to the job row that print
    already has, instead of opening a second one and debiting twice.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from config.tests.factories import make_family

from apps.printing.budget import PrintBudgetService
from apps.printing.constants import STALE_JOB_MINUTES
from apps.printing.listener import PrinterListener
from apps.printing.models import (
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintJobEvent,
    PrintRequest,
)
from apps.printing.services import PrintRequestService
from apps.printing.transports.memory import InMemoryTransport


def push(fields: dict, *, msg: int = 1) -> dict:
    """Build a ``push_status`` report with the given print-block fields."""
    return {"print": {"command": "push_status", "msg": msg, "sequence_id": "1", **fields}}


def snapshot(**fields) -> dict:
    """A full (``msg: 0``) snapshot — what ``pushall`` answers with."""
    base = {
        "gcode_state": "IDLE",
        "subtask_name": "",
        "gcode_file": "",
        "task_id": "0",
        "gcode_start_time": "0",
        "print_type": "idle",
        "layer_num": 0,
        "total_layer_num": 0,
        "mc_percent": 0,
        "mc_remaining_time": 0,
        "print_error": 0,
        "hms": [],
    }
    base.update(fields)
    return push(base, msg=0)


class IngestFixture(TestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.printer = PrinterProfile.objects.create(
            family=self.household.family,
            name="Garage X1C",
            serial="00M09A000000001",
            host="192.168.1.50",
        )
        self.listener = PrinterListener(
            self.printer,
            transport=InMemoryTransport(on_payload=lambda payload: None),
        )
        # Bypass start() so no threads are involved; process() is called
        # directly, which is both deterministic and exactly what the real
        # consumer thread does.
        self.state = self.listener.state

    def approved_request(self, *, grams="120.00", minutes=180, title="Dragon"):
        request = PrintRequestService.create_request(
            self.child,
            title=title,
            reason="I want to paint it",
            color="red",
            source_kind=PrintRequest.SourceKind.MAKERWORLD,
            source_url="https://makerworld.com/en/models/1",
        )
        return PrintRequestService.approve(
            request,
            self.parent,
            estimated_grams=Decimal(grams),
            estimated_minutes=minutes,
        )

    def start_print(self, plate_name: str, *, total_layers=100,
                    start_time="1756000000", listener=None):
        (listener or self.listener).process(snapshot(
            gcode_state="RUNNING",
            subtask_name=plate_name,
            gcode_file="/data/Metadata/plate_1.gcode",
            print_type="local",
            layer_num=1,
            total_layer_num=total_layers,
            mc_percent=0,
            mc_remaining_time=180,
            gcode_start_time=start_time,
        ))


class DeltaMergeTests(IngestFixture):
    def test_absent_keys_keep_their_previous_value(self):
        self.listener.process(snapshot(
            gcode_state="RUNNING", subtask_name="thing",
            total_layer_num=250, layer_num=3, mc_percent=1,
        ))
        # A real delta: only the two fields that changed.
        self.listener.process(push({"layer_num": 10, "mc_percent": 4}))
        self.assertEqual(self.state.total_layer_num, 250)
        self.assertEqual(self.state.subtask_name, "thing")
        self.assertEqual(self.state.layer_num, 10)

    def test_string_typed_numbers_are_coerced(self):
        # Bambu mixes quoted strings and raw ints across firmware versions.
        self.listener.process(snapshot(
            gcode_state="RUNNING", subtask_name="thing",
            layer_num="7", total_layer_num="99", mc_remaining_time="45",
        ))
        self.assertEqual(self.state.layer_num, 7)
        self.assertEqual(self.state.total_layer_num, 99)
        self.assertEqual(self.state.remaining_minutes, 45)

    def test_remaining_time_is_minutes_not_seconds(self):
        self.listener.process(snapshot(
            gcode_state="RUNNING", subtask_name="t", mc_remaining_time=90,
        ))
        self.assertEqual(self.state.remaining_minutes, 90)

    def test_nothing_is_written_before_the_first_full_snapshot(self):
        # Deltas arriving before pushall answers must not open a job: we don't
        # know subtask_name or total_layer_num yet.
        self.listener.process(push({"gcode_state": "RUNNING", "layer_num": 5}))
        self.assertFalse(self.state.seeded)
        self.assertEqual(PrintJob.objects.count(), 0)

    def test_command_acknowledgements_do_not_merge(self):
        self.listener.process(snapshot(gcode_state="IDLE"))
        self.listener.process({
            "print": {"command": "project_file", "gcode_state": "RUNNING",
                      "subtask_name": "not-a-status-report"},
        })
        self.assertEqual(self.state.gcode_state, "IDLE")
        self.assertEqual(self.state.subtask_name, "")

    def test_cloud_connection_events_do_not_crash_and_flip_online(self):
        self.listener.process({"event": {"event": "client.disconnected"}})
        self.assertFalse(self.state.online)
        self.listener.process({"event": {"event": "client.connected"}})
        self.assertTrue(self.state.online)

    def test_hms_cleared_to_empty_is_honoured(self):
        # hms IS reliably re-sent in deltas, including as [] — unlike most
        # absent-key cases, an empty list genuinely means "all clear".
        self.listener.process(snapshot(
            gcode_state="RUNNING", subtask_name="t",
            hms=[{"attr": 0x07002000, "code": 0x00030001}],
        ))
        self.assertEqual(len(self.state.hms), 1)
        self.listener.process(push({"hms": []}))
        self.assertEqual(self.state.hms, [])


class AutoLinkTests(IngestFixture):
    def test_minted_plate_name_links_the_job_to_the_request(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)

        job = PrintJob.objects.get()
        self.assertEqual(job.request, request)
        self.assertEqual(job.user, self.child)
        self.assertEqual(job.link_source, PrintJob.LinkSource.AUTO)

        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.PRINTING)
        self.assertEqual(request.print_count, 1)
        self.assertIsNotNone(request.started_at)

    def test_subtask_name_without_an_extension_still_links(self):
        # Firmware normally reports the display name with NO extension.
        request = self.approved_request()
        self.start_print(request.slug)
        self.assertEqual(PrintJob.objects.get().request, request)

    def test_a_started_print_notifies_the_child(self):
        from apps.notifications.models import Notification, NotificationType

        request = self.approved_request()
        self.start_print(request.plate_filename)
        self.assertTrue(
            Notification.objects.filter(
                user=self.child, notification_type=NotificationType.PRINT_STARTED,
            ).exists(),
        )

    def test_an_unmatched_print_still_opens_a_linkable_job(self):
        self.start_print("Clamshell Parts Box")
        job = PrintJob.objects.get()
        self.assertIsNone(job.request)
        self.assertIsNone(job.user)
        self.assertEqual(job.link_source, PrintJob.LinkSource.UNLINKED)
        self.assertEqual(job.normalized_name, "clamshell-parts-box")

    def test_calibration_runs_do_not_open_a_job(self):
        self.listener.process(snapshot(
            gcode_state="RUNNING",
            subtask_name="auto_cali_for_extrusion",
            print_type="system",
            total_layer_num=0,
        ))
        self.assertEqual(PrintJob.objects.count(), 0)

    def test_a_print_with_no_name_waits_out_the_grace_window(self):
        # subtask_name routinely arrives a beat after gcode_state flips, so an
        # immediate open would produce a phantom job on every single print.
        self.listener.process(snapshot(
            gcode_state="PREPARE", subtask_name="", print_type="cloud",
        ))
        self.assertEqual(PrintJob.objects.count(), 0)

    def test_a_name_arriving_late_still_links_normally(self):
        request = self.approved_request()
        self.listener.process(snapshot(
            gcode_state="PREPARE", subtask_name="", print_type="cloud",
        ))
        self.listener.process(push({
            "gcode_state": "RUNNING", "subtask_name": request.plate_filename,
        }))
        job = PrintJob.objects.get()
        self.assertEqual(job.request, request)
        self.assertIsNone(self.listener.tracker.unnamed_since)

    def test_a_permanently_unnamed_print_opens_a_linkable_job_after_the_grace(self):
        # A job started from the printer's own screen may never set a name.
        # A print nobody can see is worse than one with a blank name — a
        # parent can still link it by hand.
        clock = iter([0.0, 1000.0])
        self.listener.tracker._clock = lambda: next(clock)
        self.listener.process(snapshot(
            gcode_state="RUNNING", subtask_name="", print_type="local",
            total_layer_num=50,
        ))
        self.assertEqual(PrintJob.objects.count(), 0)
        self.listener.process(push({"layer_num": 2}))

        job = PrintJob.objects.get()
        self.assertEqual(job.subtask_name, "")
        self.assertEqual(job.normalized_name, "")
        self.assertIsNone(job.request)
        self.assertEqual(job.link_source, PrintJob.LinkSource.UNLINKED)
        self.assertIn(
            "unnamed print",
            PrintJobEvent.objects.filter(
                kind=PrintJobEvent.Kind.STARTED,
            ).get().message,
        )


class CloseOutTests(IngestFixture):
    def test_finish_completes_the_request_and_debits_the_full_estimate(self):
        request = self.approved_request(grams="120.00")
        self.start_print(request.plate_filename)
        self.listener.process(push({
            "gcode_state": "FINISH", "mc_percent": 100, "layer_num": 100,
        }))

        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.COMPLETED)
        job = PrintJob.objects.get()
        self.assertEqual(job.state, PrintJob.State.FINISHED)
        self.assertEqual(job.grams_debited, Decimal("120.00"))

        entry = PrintBudgetLedger.objects.get()
        self.assertEqual(entry.reason, PrintBudgetLedger.Reason.PRINT_COMPLETED)
        self.assertEqual(entry.grams, Decimal("120.00"))
        self.assertEqual(PrintBudgetService.get_usage(self.child)["grams"],
                         Decimal("120.00"))

    def test_failed_prints_record_a_decoded_reason_not_a_code(self):
        request = self.approved_request(grams="100.00")
        self.start_print(request.plate_filename, total_layers=100)
        # Nozzle clogged, then the print dies.
        self.listener.process(push({
            "layer_num": 40, "mc_percent": 40,
            "hms": [{"attr": 0x03001A00, "code": 0x00020002}],
        }))
        self.listener.process(push({"gcode_state": "FAILED"}))

        job = PrintJob.objects.get()
        self.assertEqual(job.state, PrintJob.State.FAILED)
        self.assertEqual(job.failure_code, "0300_1A00_0002_0002")
        self.assertIn("nozzle is clogged", job.failure_reason.lower())
        self.assertEqual(job.failure_severity, "serious")

        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.FAILED)

    def test_a_failed_print_is_debited_proportionally(self):
        request = self.approved_request(grams="100.00")
        self.start_print(request.plate_filename, total_layers=100)
        self.listener.process(push({"layer_num": 40, "mc_percent": 40}))
        self.listener.process(push({"gcode_state": "FAILED"}))

        entry = PrintBudgetLedger.objects.get()
        self.assertEqual(entry.reason, PrintBudgetLedger.Reason.PRINT_FAILED)
        self.assertEqual(entry.grams, Decimal("40.00"))

    def test_an_early_failure_still_costs_the_floor(self):
        # A print that dies on layer 1 burned a purge line and a skirt.
        request = self.approved_request(grams="100.00")
        self.start_print(request.plate_filename, total_layers=100)
        self.listener.process(push({"gcode_state": "FAILED"}))
        self.assertEqual(PrintBudgetLedger.objects.get().grams, Decimal("10.00"))

    def test_a_user_cancel_is_not_a_failure(self):
        request = self.approved_request(grams="100.00")
        self.start_print(request.plate_filename, total_layers=100)
        self.listener.process(push({"layer_num": 20, "print_error": 50348044}))
        # print_error resets to 0 within seconds — the latch must survive it.
        self.listener.process(push({"print_error": 0}))
        self.listener.process(push({"gcode_state": "FAILED"}))

        job = PrintJob.objects.get()
        self.assertEqual(job.state, PrintJob.State.CANCELLED)
        request.refresh_from_db()
        # Still approved, still named — a re-slice re-binds to the same slug.
        self.assertEqual(request.status, PrintRequest.Status.APPROVED)

    def test_print_error_wins_over_hms_as_the_failure_reason(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        self.listener.process(push({
            "hms": [{"attr": 0x0C000300, "code": 0x00030008}],
            "print_error": 0x03004006,
        }))
        self.listener.process(push({"gcode_state": "FAILED"}))
        job = PrintJob.objects.get()
        self.assertEqual(job.failure_code, "0300_4006")

    def test_going_straight_to_idle_closes_as_unknown_not_success(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        self.listener.process(push({"gcode_state": "IDLE"}))
        job = PrintJob.objects.get()
        self.assertEqual(job.state, PrintJob.State.UNKNOWN)
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.FAILED)

    def test_close_out_is_idempotent(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        self.listener.process(push({"gcode_state": "FINISH", "mc_percent": 100}))
        job = PrintJob.objects.get()
        # A duplicate FINISH (the printer re-sends state on reconnect) must
        # not double-debit.
        PrintRequestService.close_out(job)
        self.assertEqual(PrintBudgetLedger.objects.count(), 1)

    def test_an_unlinked_job_closing_writes_no_ledger_row(self):
        self.start_print("Some Random Plate")
        self.listener.process(push({"gcode_state": "FINISH", "mc_percent": 100}))
        self.assertEqual(PrintBudgetLedger.objects.count(), 0)
        self.assertEqual(PrintJob.objects.get().state, PrintJob.State.FINISHED)

    def test_a_reprint_of_a_failed_request_binds_again(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        self.listener.process(push({"gcode_state": "FAILED"}))
        self.listener.process(push({"gcode_state": "IDLE"}))

        self.start_print(request.plate_filename)
        self.assertEqual(PrintJob.objects.count(), 2)
        request.refresh_from_db()
        self.assertEqual(request.print_count, 2)
        self.assertEqual(request.status, PrintRequest.Status.PRINTING)


class TimelineTests(IngestFixture):
    def test_progress_rows_are_throttled(self):
        request = self.approved_request()
        self.start_print(request.plate_filename, total_layers=100)
        for percent in range(1, 101):
            self.listener.process(push({"mc_percent": percent, "layer_num": percent}))
        rows = PrintJobEvent.objects.filter(kind=PrintJobEvent.Kind.PROGRESS).count()
        # 5% steps → ~20 rows, not 100.
        self.assertLessEqual(rows, 21)
        self.assertGreaterEqual(rows, 19)

    def test_an_hms_alert_writes_one_row_not_one_per_report(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        alert = [{"attr": 0x07002000, "code": 0x00020001}]
        for _ in range(5):
            self.listener.process(push({"hms": alert}))
        rows = PrintJobEvent.objects.filter(kind=PrintJobEvent.Kind.HMS)
        self.assertEqual(rows.count(), 1)
        self.assertIn("ran out of filament", rows.get().message)

    def test_a_new_alert_after_a_clear_writes_another_row(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        alert = [{"attr": 0x07002000, "code": 0x00020001}]
        self.listener.process(push({"hms": alert}))
        self.listener.process(push({"hms": []}))
        self.listener.process(push({"hms": alert}))
        self.assertEqual(
            PrintJobEvent.objects.filter(kind=PrintJobEvent.Kind.HMS).count(), 2,
        )

    def test_pause_and_resume_are_recorded_once_each(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        self.listener.process(push({"gcode_state": "PAUSE"}))
        self.listener.process(push({"gcode_state": "PAUSE"}))
        self.listener.process(push({"gcode_state": "RUNNING"}))
        self.assertEqual(
            PrintJobEvent.objects.filter(kind=PrintJobEvent.Kind.PAUSED).count(), 1,
        )
        self.assertEqual(
            PrintJobEvent.objects.filter(kind=PrintJobEvent.Kind.RESUMED).count(), 1,
        )

    def test_the_timeline_opens_with_a_started_row_and_a_link_row(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        kinds = list(
            PrintJobEvent.objects.order_by("id").values_list("kind", flat=True),
        )
        self.assertEqual(
            kinds[:2], [PrintJobEvent.Kind.STARTED, PrintJobEvent.Kind.LINKED],
        )


class ListenerRestartTests(IngestFixture):
    """A restarted listener must re-attach to a print, not re-open it.

    ``PrinterJobTracker.open_job_id`` is in-memory state, the process holding
    it restarts on every deploy, and a print runs for hours — so a restart
    lands mid-print routinely. Without the resume step the new tracker sees
    "printing, named, and no open job", writes a second row for one plate,
    force-closes the first as ``unknown``, and debits the budget twice.

    Every test here builds a *second* ``PrinterListener`` over the same
    printer, which is exactly what the new process does.
    """

    def restarted(self):
        return PrinterListener(
            self.printer,
            transport=InMemoryTransport(on_payload=lambda payload: None),
        )

    def resume_snapshot(self, plate_name, **fields):
        """What pushall answers with when we reconnect to a print in progress."""
        base = {
            "gcode_state": "RUNNING",
            "subtask_name": plate_name,
            "gcode_file": "/data/Metadata/plate_1.gcode",
            "print_type": "local",
            "layer_num": 40,
            "total_layer_num": 100,
            "mc_percent": 40,
            "mc_remaining_time": 90,
            "gcode_start_time": "1756000000",
        }
        base.update(fields)
        return snapshot(**base)

    def test_a_restart_mid_print_reattaches_to_the_open_job(self):
        request = self.approved_request()
        self.start_print(request.plate_filename)
        original = PrintJob.objects.get()

        listener = self.restarted()
        listener.process(self.resume_snapshot(request.plate_filename))

        self.assertEqual(PrintJob.objects.count(), 1)
        self.assertEqual(listener.tracker.open_job_id, original.pk)
        original.refresh_from_db()
        self.assertEqual(original.state, PrintJob.State.RUNNING)
        self.assertIsNone(original.finished_at)
        self.assertEqual(original.percent_complete, 40)

    def test_a_restart_mid_print_does_not_debit_the_budget_twice(self):
        # The expensive half of the duplicate: the abandoned row closes as
        # unknown and is debited as a partial failure, then the second row
        # finishes and is debited the full estimate on top.
        request = self.approved_request(grams="120.00")
        self.start_print(request.plate_filename)

        listener = self.restarted()
        listener.process(self.resume_snapshot(request.plate_filename))
        listener.process(push({
            "gcode_state": "FINISH", "mc_percent": 100, "layer_num": 100,
        }))

        self.assertEqual(PrintJob.objects.count(), 1)
        self.assertEqual(PrintBudgetLedger.objects.count(), 1)
        self.assertEqual(PrintBudgetService.get_usage(self.child)["grams"],
                         Decimal("120.00"))
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.COMPLETED)
        self.assertEqual(request.print_count, 1)

    def test_coming_back_to_a_finished_printer_closes_the_row_as_finished(self):
        # The printer holds the finished print's name and start time until the
        # next one begins, so a listener that missed the FINISH transition can
        # still close the row correctly instead of leaving it for the stale
        # sweep to write off as unknown.
        request = self.approved_request(grams="120.00")
        self.start_print(request.plate_filename)

        listener = self.restarted()
        listener.process(self.resume_snapshot(
            request.plate_filename, gcode_state="FINISH",
            layer_num=100, mc_percent=100, mc_remaining_time=0,
        ))

        job = PrintJob.objects.get()
        self.assertEqual(job.state, PrintJob.State.FINISHED)
        self.assertIsNotNone(job.finished_at)
        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.COMPLETED)

    def test_a_restart_between_two_prints_still_opens_the_second_job(self):
        self.start_print("Card Holder", start_time="1756000000")

        listener = self.restarted()
        listener.process(self.resume_snapshot(
            "Battery Tray", gcode_start_time="1756009999",
        ))

        self.assertEqual(PrintJob.objects.count(), 2)
        first, second = PrintJob.objects.order_by("started_at")
        self.assertEqual(first.state, PrintJob.State.UNKNOWN)
        self.assertEqual(second.subtask_name, "Battery Tray")
        self.assertEqual(second.state, PrintJob.State.RUNNING)

    def test_a_reprint_of_the_same_plate_is_not_absorbed(self):
        # Same name, different run: the start time is what tells them apart,
        # and adopting here would lose a whole print.
        self.start_print("Card Holder", start_time="1756000000")

        listener = self.restarted()
        listener.process(self.resume_snapshot(
            "Card Holder", gcode_start_time="1756009999",
        ))

        self.assertEqual(PrintJob.objects.count(), 2)

    def test_a_row_predating_the_start_time_is_matched_by_name(self):
        # The upgrade path: a job already open when this shipped has no
        # gcode_start_time, so the name is all there is to go on. Adopting it
        # also backfills the id, so the next restart gets the strong check.
        self.start_print("Card Holder")
        PrintJob.objects.update(gcode_start_time="")

        listener = self.restarted()
        listener.process(self.resume_snapshot("Card Holder"))

        job = PrintJob.objects.get()
        self.assertEqual(listener.tracker.open_job_id, job.pk)
        self.assertEqual(job.gcode_start_time, "1756000000")

    def test_a_row_left_open_by_an_old_print_is_not_adopted(self):
        # No ids on either side and the same plate name, but the printer went
        # quiet on that row hours ago — it is a power-cut leftover, not this
        # print. Adopting it would merge two prints into one row.
        self.start_print("Card Holder")
        PrintJob.objects.update(
            gcode_start_time="",
            started_at=timezone.now() - timedelta(minutes=STALE_JOB_MINUTES + 30),
            last_report_at=timezone.now() - timedelta(minutes=STALE_JOB_MINUTES + 30),
        )

        listener = self.restarted()
        listener.process(self.resume_snapshot("Card Holder", gcode_start_time="0"))

        self.assertEqual(PrintJob.objects.count(), 2)
        self.assertEqual(
            PrintJob.objects.filter(state=PrintJob.State.UNKNOWN).count(), 1,
        )

    def test_alerts_already_on_the_timeline_are_not_logged_again(self):
        # The hms array is re-sent every second while an alert is active, so a
        # tracker that came back with an empty memory of it would write the
        # same row a second time.
        alert = [{"attr": 0x07002000, "code": 0x00020001}]
        self.start_print("Card Holder")
        self.listener.process(push({"hms": alert}))

        listener = self.restarted()
        listener.process(self.resume_snapshot("Card Holder", hms=alert))

        self.assertEqual(
            PrintJobEvent.objects.filter(kind=PrintJobEvent.Kind.HMS).count(), 1,
        )

    def test_reattaching_leaves_a_note_on_the_timeline(self):
        self.start_print("Card Holder")
        listener = self.restarted()
        listener.process(self.resume_snapshot("Card Holder"))

        note = PrintJobEvent.objects.filter(kind=PrintJobEvent.Kind.NOTE).get()
        self.assertIn("listener restarted", note.message)

    def test_an_idle_printer_with_no_open_job_resumes_nothing(self):
        listener = self.restarted()
        listener.process(snapshot(gcode_state="IDLE"))
        self.assertEqual(PrintJob.objects.count(), 0)
