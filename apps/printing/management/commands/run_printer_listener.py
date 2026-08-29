"""Run the single MQTT listener process.

This command is the **only** place in the codebase that opens a connection to
a printer. It is deployed as its own compose service (``printer_listener``)
rather than as a Celery task or a thread inside gunicorn, because the X1's
broker tolerates only about four clients and a per-worker connection would
blow through that instantly. See ``apps/printing/fanout.py`` for how everyone
else gets printer state without connecting.

    docker compose exec django python manage.py run_printer_listener

``--capture`` records what the printer actually says, and ``--replay`` pushes
it back through the real ingest path with no network at all. Together they
are how you debug "why didn't this print link" — or write a parser against a
firmware you don't have in front of you:

    python manage.py run_printer_listener --capture ./captures
    python manage.py run_printer_listener --replay ./captures/00M09A....jsonl \
        --serial 00M09A...

``--capture`` takes a *directory* and writes one ``<serial>.jsonl`` per
printer, so each file is a pure payload stream that ``--replay`` consumes
with no unwrapping. It records alongside normal operation — the listener goes
on tracking jobs exactly as it would otherwise.
"""
from __future__ import annotations

import json
import signal
import socket
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.printing.listener import ListenerSupervisor, PrinterListener
from apps.printing.models import PrinterProfile
from apps.printing.transports.memory import InMemoryTransport


class Command(BaseCommand):
    help = "Hold one MQTT connection per printer and ingest print jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replay",
            metavar="PATH",
            help=(
                "Replay a JSONL file of captured MQTT payloads through the "
                "real ingest path instead of connecting. One JSON object per line."
            ),
        )
        parser.add_argument(
            "--serial",
            help="Printer serial to replay against. Required with --replay.",
        )
        parser.add_argument(
            "--capture",
            metavar="DIR",
            help=(
                "Also append every ingested payload to DIR/<serial>.jsonl, "
                "one JSON object per line, for later --replay. The directory "
                "is created if missing. Diagnostic — leave it off normally."
            ),
        )
        parser.add_argument(
            "--poll-interval",
            type=int,
            default=5,
            help="Seconds between supervisor ticks (default: 5).",
        )

    def handle(self, *args, **options):
        if options.get("replay"):
            return self._replay(options["replay"], options.get("serial"))

        owner = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        capture_dir = options.get("capture")
        supervisor = ListenerSupervisor(
            owner=owner, poll_interval=options["poll_interval"],
            capture_dir=capture_dir,
        )

        def _shutdown(signum, frame):  # noqa: ARG001
            self.stdout.write(self.style.WARNING("\nShutting down listeners…"))
            supervisor.stop()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        self.stdout.write(self.style.SUCCESS(f"Printer listener started as {owner}"))
        if capture_dir:
            self.stdout.write(self.style.WARNING(
                f"Capturing payloads to {capture_dir}/<serial>.jsonl",
            ))
        supervisor.run_forever()
        self.stdout.write(self.style.SUCCESS("Printer listener stopped."))

    # ------------------------------------------------------------------ #
    def _replay(self, path: str, serial: str | None):
        if not serial:
            raise CommandError("--replay requires --serial.")
        try:
            printer = PrinterProfile.objects.get(serial=serial)
        except PrinterProfile.DoesNotExist:
            raise CommandError(f"No printer with serial {serial!r}.") from None

        listener = PrinterListener(printer, transport=InMemoryTransport(
            on_payload=lambda payload: None,
        ))
        listener.start()
        count = 0
        try:
            with open(path, encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        self.stderr.write(f"line {line_number}: not JSON, skipped")
                        continue
                    # Straight into process(): synchronous, ordered, and it
                    # exercises exactly the code a live broker would.
                    listener.process(payload)
                    count += 1
        finally:
            listener.stop()
        self.stdout.write(self.style.SUCCESS(f"Replayed {count} payloads."))
