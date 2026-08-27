"""The one process that talks to the printers.

Two guarantees this module exists to provide:

**Exactly one MQTT connection per printer.** Enforced twice, on purpose:

1. *Structurally* — the listener only ever runs inside its own
   ``manage.py run_printer_listener`` process (the ``printer_listener``
   compose service). Gunicorn workers and Celery workers never import a
   transport, so they cannot open a socket even by accident. This is the
   guarantee that actually holds.
2. *At runtime* — a Redis advisory lock per serial, so if someone scales the
   listener service to two replicas, or starts a second one by hand during a
   deploy, the loser skips that printer instead of joining the fight. The
   lock has a TTL and is refreshed by the supervisor, so a killed process
   releases it within one TTL rather than wedging the printer forever.

**Nothing blocking on the network thread.** paho runs its callbacks on a
single network thread, and the broker drops a client that misses a PINGREQ
for 1.5× keepalive. Database writes happen on a dedicated consumer thread fed
by a bounded queue; the paho thread only parses JSON and enqueues.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from django.core.cache import cache
from django.db import OperationalError, ProgrammingError
from django.utils import timezone

from . import fanout, report
from .constants import LISTENER_HEARTBEAT_PATH
from .jobs import PrinterJobTracker
from .models import PrinterProfile
from .transports import TransportError, build_transport

logger = logging.getLogger(__name__)

#: Advisory-lock TTL. Must exceed the supervisor's refresh interval by enough
#: that a slow tick doesn't drop the lock mid-print.
LOCK_TTL_SECONDS = 90
LOCK_REFRESH_SECONDS = 30

#: No message for this long means the stream is dead even though TCP looks
#: fine — ask for a fresh snapshot.
STALE_NUDGE_SECONDS = 60
#: Still nothing after this long — tear the connection down and rebuild it.
STALE_RECONNECT_SECONDS = 180

#: Bounded so a database stall can't grow memory without limit. On overflow we
#: drop the oldest report and re-seed with pushall, because a dropped delta
#: leaves our merged state subtly wrong and only a full snapshot fixes that.
INGEST_QUEUE_MAX = 500


def lock_key(serial: str) -> str:
    return f"printing:listener-lock:{serial}"


class PrinterLock:
    """Redis advisory lock naming the one listener allowed on a printer."""

    def __init__(self, serial: str, owner: str):
        self.serial = serial
        self.owner = owner
        self.held = False

    def acquire(self) -> bool:
        # cache.add is SETNX with a TTL on the Redis backend — atomic, and a
        # no-op if somebody already holds it.
        self.held = bool(cache.add(lock_key(self.serial), self.owner, LOCK_TTL_SECONDS))
        return self.held

    def refresh(self) -> bool:
        """Re-stamp our TTL. Returns False if somebody else took the lock."""
        if not self.held:
            return False
        current = cache.get(lock_key(self.serial))
        if current not in (None, self.owner):
            self.held = False
            return False
        cache.set(lock_key(self.serial), self.owner, LOCK_TTL_SECONDS)
        return True

    def release(self) -> None:
        if not self.held:
            return
        if cache.get(lock_key(self.serial)) == self.owner:
            cache.delete(lock_key(self.serial))
        self.held = False


class PrinterListener:
    """One printer: one transport, one merged state, one job tracker."""

    def __init__(self, printer: PrinterProfile, *, transport=None):
        self.printer = printer
        self.state = report.PrinterState(serial=printer.serial)
        self.tracker = PrinterJobTracker(printer)
        self._queue: queue.Queue = queue.Queue(maxsize=INGEST_QUEUE_MAX)
        self._stop = threading.Event()
        self._consumer: threading.Thread | None = None
        self._needs_reseed = False
        #: (state, detail) set by the network thread, persisted by the
        #: supervisor tick so no DB call runs on paho's network thread.
        self._pending_status: tuple[str, str] | None = None
        self.last_message_at = 0.0
        self.last_nudge_at = 0.0
        # Injected in tests (InMemoryTransport); built from the profile in prod.
        self._transport = transport

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._transport is None:
            self._transport = build_transport(
                self.printer,
                on_payload=self._enqueue,
                on_status=self._on_status,
            )
        else:
            self._transport.on_payload = self._enqueue
            self._transport.on_status = self._on_status

        self._stop.clear()
        self._consumer = threading.Thread(
            target=self._consume_forever,
            name=f"printing-ingest-{self.printer.serial}",
            daemon=True,
        )
        self._consumer.start()
        self._transport.start()
        self.last_message_at = time.monotonic()

    def stop(self) -> None:
        self._stop.set()
        if self._transport is not None:
            try:
                self._transport.stop()
            except Exception:  # noqa: BLE001
                logger.debug("printing[%s]: transport stop raised", self.printer.serial)
        # Wake the consumer so it can notice the stop flag.
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._consumer is not None:
            self._consumer.join(timeout=5)

    @property
    def transport(self):
        return self._transport

    # -- paho thread: parse + enqueue only ---------------------------------
    def _enqueue(self, payload: dict) -> None:
        self.last_message_at = time.monotonic()
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            # Drop the oldest and re-seed. A dropped delta silently corrupts
            # merged state, and only a full snapshot can repair it.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(payload)
            except (queue.Empty, queue.Full):  # pragma: no cover - racy edge
                pass
            self._needs_reseed = True
            logger.warning(
                "printing[%s]: ingest queue full — dropped a report and will re-seed",
                self.printer.serial,
            )

    def _on_status(self, state: str, detail: str) -> None:
        """Connection lifecycle callback — runs on paho's network thread.

        Deliberately does NO database I/O. paho runs its callbacks on a single
        network thread and the broker drops a client that misses a PINGREQ for
        1.5x keepalive, so a slow database here would cost us the connection.
        The pending status is stashed and the supervisor's tick persists it.
        """
        logger.info("printing[%s]: %s %s", self.printer.serial, state, detail)
        if state == "connected":
            # A fresh connection means our merged state is stale; pushall on
            # connect re-seeds it, but until that lands we must not trust it.
            self.state.seeded = False
        self._pending_status = (state, detail[:300])

    def flush_status(self) -> None:
        """Persist the last connection status. Called off the network thread."""
        pending, self._pending_status = self._pending_status, None
        if pending is None:
            return
        state, detail = pending
        PrinterProfile.objects.filter(pk=self.printer.pk).update(
            last_error=detail if state == "error" else "",
        )

    # -- consumer thread: merge + persist ----------------------------------
    def _consume_forever(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            if payload is None:
                continue
            try:
                self.process(payload)
            except Exception:  # noqa: BLE001 - one bad report must not end ingest
                logger.exception(
                    "printing[%s]: failed to process a report", self.printer.serial,
                )

    def process(self, payload: dict) -> None:
        """Merge one payload and persist anything meaningful.

        Public because the tests (and ``--replay``) drive it directly with
        captured payloads, exercising the real path without a broker.
        """
        event = report.connection_event(payload)
        if event is not None:
            # Cloud-only lifecycle envelope: no "print" key at all.
            self.state.online = event == "connected"
            fanout.publish_state(self.printer.serial, self.state.snapshot())
            return

        if not report.is_status_report(payload):
            # Command acknowledgements carry a "print" key too; merging one
            # would corrupt state.
            return

        report.merge(self.state, payload)
        fanout.publish_state(self.printer.serial, self.state.snapshot())
        self.tracker.handle(self.state)
        self._touch_printer_row()

    def _touch_printer_row(self) -> None:
        """Persist the coarse 'is it alive' fields, not the whole state.

        At roughly one report per second, writing the printer row on every
        message is ~86,000 writes a day per printer. We only write when the
        coarse state actually changes; liveness for the UI comes from the
        cached snapshot's TTL.
        """
        if self.printer.last_gcode_state == self.state.gcode_state:
            return
        self.printer.last_gcode_state = self.state.gcode_state
        self.printer.last_report_at = timezone.now()
        PrinterProfile.objects.filter(pk=self.printer.pk).update(
            last_gcode_state=self.state.gcode_state[:24],
            last_report_at=self.printer.last_report_at,
        )

    # -- watchdog ----------------------------------------------------------
    def tick(self) -> None:
        """Called by the supervisor once per loop. Handles stale streams."""
        self.flush_status()
        if self._transport is None:
            return
        if self._needs_reseed:
            self._needs_reseed = False
            self._safe_pushall()
            return

        idle = time.monotonic() - self.last_message_at
        if idle > STALE_RECONNECT_SECONDS:
            logger.warning(
                "printing[%s]: no reports for %ds — rebuilding the connection",
                self.printer.serial, int(idle),
            )
            self.stop()
            self._transport = None
            self.start()
            return
        if idle > STALE_NUDGE_SECONDS:
            # Nudge at most once per stale window, never on a short timer —
            # pushall is expensive on the printer side.
            if time.monotonic() - self.last_nudge_at > STALE_NUDGE_SECONDS:
                self.last_nudge_at = time.monotonic()
                self._safe_pushall()

    def _safe_pushall(self) -> None:
        try:
            self._transport.request_full_status()
        except Exception:  # noqa: BLE001
            logger.debug("printing[%s]: pushall failed", self.printer.serial)


class ListenerSupervisor:
    """Own one listener per active printer, and keep the locks fresh."""

    def __init__(self, *, owner: str, poll_interval: int = 5,
                 heartbeat_path: str = LISTENER_HEARTBEAT_PATH):
        self.owner = owner
        self.poll_interval = poll_interval
        self.heartbeat_path = heartbeat_path
        self.listeners: dict[int, PrinterListener] = {}
        self.locks: dict[int, PrinterLock] = {}
        self._stop = threading.Event()
        self._last_refresh = 0.0

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        """Supervise until stopped. Survives a database that isn't there yet.

        This process outlives deploys, so the loop body must not be fatal:

        * On a deploy that adds the printing tables, this container can start
          before the ``django`` service has finished migrating — the query in
          ``sync()`` then raises ``ProgrammingError`` for a table that is
          about to exist. That is a wait, not a crash.
        * Postgres restarting under a rolling deploy leaves this long-lived
          process holding a dead connection. ``close_old_connections()`` at
          the top of each pass discards it, the same way the Celery
          pre/post-run hooks do for workers.

        Letting either kill the process would be quietly expensive: the
        container would restart, drop its MQTT connection, and if that
        happened mid-print it would miss the FINISH transition entirely —
        the job would only close hours later via ``reconcile_stale_jobs``,
        as ``unknown``, with the budget debited as a partial failure.
        """
        from django.db import close_old_connections

        try:
            while not self._stop.is_set():
                try:
                    close_old_connections()
                    self.sync()
                    self.tick()
                except OperationalError as exc:
                    logger.warning(
                        "printing: database unavailable, retrying in %ss: %s",
                        self.poll_interval, exc,
                    )
                except ProgrammingError as exc:
                    logger.warning(
                        "printing: printing tables not migrated yet, waiting: %s",
                        exc,
                    )
                except Exception:  # noqa: BLE001 - a bad pass must not end the process
                    logger.exception("printing: supervisor pass failed, continuing")
                # Heartbeat AFTER the pass, including the failure branches: a
                # supervisor waiting out a migration is alive and healthy. What
                # this must not survive is the loop wedging or the process
                # dying, and neither of those reaches here.
                self.touch_heartbeat()
                self._stop.wait(self.poll_interval)
        finally:
            self.shutdown()

    def touch_heartbeat(self) -> None:
        """Stamp the liveness file the compose healthcheck reads.

        Never raises: a read-only or full /tmp is not a reason to take the
        listener down, it just means the healthcheck goes stale and the
        container gets restarted — which is the correct outcome anyway.
        """
        try:
            with open(self.heartbeat_path, "w", encoding="utf-8") as handle:
                handle.write(str(int(time.time())))
        except OSError as exc:  # pragma: no cover - filesystem dependent
            logger.warning("printing: could not write heartbeat: %s", exc)

    def sync(self) -> None:
        """Start listeners for printers we should own; drop the rest."""
        active = {
            printer.pk: printer
            for printer in PrinterProfile.objects.filter(is_active=True)
        }
        for pk in list(self.listeners):
            if pk not in active:
                self._drop(pk)

        for pk, printer in active.items():
            if pk in self.listeners:
                # Refresh our in-memory copy so an edited host/credential is
                # picked up on the next reconnect.
                self.listeners[pk].printer = printer
                continue
            if not printer.has_credentials:
                # Stamp the reason. Skipping silently is the same as the
                # printer simply not working, and "no access code saved" is
                # the single most common misconfiguration — the parent needs
                # to see it on the printer card, not guess.
                reason = (
                    "No Bambu user id / access token saved."
                    if printer.transport == PrinterProfile.Transport.CLOUD
                    else "No LAN access code saved (it's on the printer screen "
                         "under Settings → Network)."
                )
                if printer.last_error != reason:
                    PrinterProfile.objects.filter(pk=pk).update(last_error=reason)
                continue
            lock = PrinterLock(printer.serial, self.owner)
            if not lock.acquire():
                logger.info(
                    "printing[%s]: another listener holds the connection — skipping",
                    printer.serial,
                )
                continue
            listener = PrinterListener(printer)
            try:
                listener.start()
            except TransportError as exc:
                lock.release()
                logger.error("printing[%s]: %s", printer.serial, exc)
                PrinterProfile.objects.filter(pk=pk).update(last_error=str(exc)[:300])
                continue
            self.listeners[pk] = listener
            self.locks[pk] = lock

    def tick(self) -> None:
        now = time.monotonic()
        refresh = now - self._last_refresh > LOCK_REFRESH_SECONDS
        if refresh:
            self._last_refresh = now

        for pk, listener in list(self.listeners.items()):
            if refresh and not self.locks[pk].refresh():
                logger.warning(
                    "printing[%s]: lost the listener lock — disconnecting",
                    listener.printer.serial,
                )
                self._drop(pk)
                continue
            transport = listener.transport
            if transport is not None and getattr(transport, "has_fatal_auth_error", False):
                logger.error(
                    "printing[%s]: credentials rejected — not retrying",
                    listener.printer.serial,
                )
                self._drop(pk)
                continue
            listener.tick()

    def _drop(self, pk: int) -> None:
        listener = self.listeners.pop(pk, None)
        lock = self.locks.pop(pk, None)
        if listener is not None:
            listener.stop()
        if lock is not None:
            lock.release()

    def shutdown(self) -> None:
        for pk in list(self.listeners):
            self._drop(pk)
        fanout.reset_republisher()
