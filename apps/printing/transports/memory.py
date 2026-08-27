"""A transport that never touches the network.

This is how the listener, the delta-merge and the whole job state machine get
tested without a broker: a test builds the real
:class:`~apps.printing.listener.PrinterListener` around an
:class:`InMemoryTransport` and calls :meth:`feed` with captured payloads. Every
line of production ingest code runs; only the socket is missing.

It is also what ``manage.py run_printer_listener --replay <file.jsonl>`` uses
to push a recorded session through the pipeline, which is the fastest way to
debug "why did this print not link" without standing next to a printer.
"""
from __future__ import annotations

from .base import PrinterTransport, TransportConfig


class InMemoryTransport(PrinterTransport):
    """Deliver payloads on demand; record anything published."""

    def __init__(self, config: TransportConfig | None = None, *, on_payload,
                 on_status=None):
        super().__init__(
            config or TransportConfig(serial="TEST0000000000"),
            on_payload=on_payload,
            on_status=on_status,
        )
        self.started = False
        #: Everything the listener sent to the printer, in order.
        self.published: list[dict] = []

    def start(self) -> None:
        self.started = True
        self.on_status("connected", "")

    def stop(self) -> None:
        if self.started:
            self.started = False
            self.on_status("disconnected", "stopped")

    def publish(self, payload: dict) -> None:
        self.published.append(payload)

    # -- test/replay driver -------------------------------------------------
    def feed(self, payload: dict) -> None:
        """Push one report through the handler, exactly as a broker would."""
        self.on_payload(payload)

    def feed_all(self, payloads) -> None:
        for payload in payloads:
            self.feed(payload)
