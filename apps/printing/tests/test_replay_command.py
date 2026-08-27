"""Pins ``manage.py run_printer_listener --replay``.

The replay path exists so you can debug "why didn't this print link" from a
captured log instead of standing next to a printer. It runs the *real* ingest
pipeline — gating, delta merge, job bracketing, HMS decode, budget close-out —
with no network at all, so this test is also the highest-level proof that the
whole chain fits together:

1. Approval mints a slug and a plate filename.
2. A print whose ``subtask_name`` is that filename links automatically.
3. Deltas merge; progress rows are written.
4. An HMS alert lands on the timeline as a readable sentence.
5. ``print_error`` decides the failure reason and closes the request.
6. The budget is debited proportionally.
"""
from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from config.tests.factories import make_family

from apps.printing.budget import PrintBudgetService
from apps.printing.models import (
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintJobEvent,
    PrintRequest,
)
from apps.printing.services import PrintRequestService

SERIAL = "00M09A342000000"

#: A captured X1 session: idle snapshot → running → progress deltas → an AMS
#: runout alert → a nozzle-clog print_error → FAILED. The integers are the real
#: wire values: 0x07002000 / 0x00020001 for the HMS pair and 0x03004006 for the
#: print error.
SESSION = [
    {"print": {"command": "push_status", "msg": 0, "gcode_state": "IDLE",
               "subtask_name": "", "gcode_file": "", "print_type": "idle",
               "layer_num": 0, "total_layer_num": 0, "mc_percent": 0,
               "mc_remaining_time": 0, "print_error": 0, "hms": []}},
    {"print": {"command": "push_status", "msg": 1, "gcode_state": "RUNNING",
               "subtask_name": "PLATE_NAME",
               "gcode_file": "/data/Metadata/plate_1.gcode",
               "print_type": "local", "layer_num": 1, "total_layer_num": 200,
               "mc_percent": 0, "mc_remaining_time": 95}},
    {"print": {"command": "push_status", "msg": 1, "layer_num": 50,
               "mc_percent": 25, "mc_remaining_time": 70}},
    {"print": {"command": "push_status", "msg": 1,
               "hms": [{"attr": 0x07002000, "code": 0x00020001}]}},
    {"print": {"command": "push_status", "msg": 1, "layer_num": 120,
               "mc_percent": 60}},
    {"print": {"command": "push_status", "msg": 1, "print_error": 0x03004006}},
    {"print": {"command": "push_status", "msg": 1, "gcode_state": "FAILED"}},
]


class ReplayCommandTests(TestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        PrinterProfile.objects.create(
            family=self.household.family,
            name="Garage X1C",
            serial=SERIAL,
            host="192.168.1.50",
        )
        budget = PrintBudgetService.get_budget(self.child)
        budget.grams_per_month = Decimal("500.00")
        budget.minutes_per_month = 3000
        budget.save()

    def _session_file(self, plate_name: str) -> str:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8",
        )
        for payload in SESSION:
            raw = json.dumps(payload).replace("PLATE_NAME", plate_name)
            handle.write(raw + "\n")
        # A blank line and a malformed line: a real capture has both, and one
        # bad line must not abort the replay.
        handle.write("\n")
        handle.write("not json at all\n")
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def _approved_request(self):
        request = PrintRequestService.create_request(
            self.child,
            title="Dragon",
            reason="I want to paint it",
            color="red",
            source_kind=PrintRequest.SourceKind.MAKERWORLD,
            source_url="https://makerworld.com/en/models/1",
        )
        return PrintRequestService.approve(
            request, self.parent,
            estimated_grams=Decimal("150.00"), estimated_minutes=95,
        )

    # ------------------------------------------------------------------ #
    def test_replay_drives_the_whole_pipeline(self):
        request = self._approved_request()
        # The plate is saved under exactly the name the app minted.
        self.assertEqual(request.plate_filename, f"{request.slug}.3mf")

        call_command(
            "run_printer_listener",
            replay=self._session_file(request.plate_filename),
            serial=SERIAL,
        )

        job = PrintJob.objects.get()
        self.assertEqual(job.request_id, request.pk)
        self.assertEqual(job.link_source, PrintJob.LinkSource.AUTO)
        self.assertEqual(job.state, PrintJob.State.FAILED)
        # Deltas merged: total_layer_num arrived once and was never re-sent.
        self.assertEqual(job.total_layer_num, 200)
        self.assertEqual(job.layer_num, 120)
        self.assertEqual(job.percent_complete, 60)

        # print_error wins over the HMS alert as the failure reason, and it
        # reads as a sentence.
        self.assertEqual(job.failure_code, "0300_4006")
        self.assertIn("nozzle is clogged", job.failure_reason)

        request.refresh_from_db()
        self.assertEqual(request.status, PrintRequest.Status.FAILED)

        # The AMS alert is on the timeline, decoded, with its unit and slot.
        hms_row = PrintJobEvent.objects.get(kind=PrintJobEvent.Kind.HMS)
        self.assertIn("ran out of filament", hms_row.message)
        self.assertIn("unit A, slot 1", hms_row.message)
        self.assertEqual(hms_row.code, "0700_2000_0002_0001")

        # 120 of 200 layers → 60% of the 150g estimate.
        entry = PrintBudgetLedger.objects.get()
        self.assertEqual(entry.reason, PrintBudgetLedger.Reason.PRINT_FAILED)
        self.assertEqual(entry.grams, Decimal("90.00"))
        self.assertEqual(
            PrintBudgetService.get_remaining(self.child)["grams"],
            Decimal("410.00"),
        )

    def test_replay_skips_blank_and_malformed_lines(self):
        request = self._approved_request()
        call_command(
            "run_printer_listener",
            replay=self._session_file(request.plate_filename),
            serial=SERIAL,
        )
        # The trailing blank + garbage lines did not abort the run: the job
        # still reached its terminal state.
        self.assertEqual(PrintJob.objects.get().state, PrintJob.State.FAILED)

    def test_replay_requires_a_serial(self):
        with self.assertRaises(CommandError):
            call_command("run_printer_listener", replay="/dev/null")

    def test_replay_rejects_an_unknown_serial(self):
        with self.assertRaises(CommandError):
            call_command(
                "run_printer_listener", replay="/dev/null", serial="NOPE",
            )
