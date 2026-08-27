"""Pins the single-connection guarantee and the listener's ingest gate.

No broker, no sockets, and no threads: every test drives
``PrinterListener.process`` directly, which is exactly what the real consumer
thread calls.

Invariants this file exists to protect:

1. ``PrinterLock`` is the runtime half of "exactly one MQTT connection per
   printer". The first holder wins, a second holder is refused, ``refresh``
   keeps a live lock alive, and ``release`` frees it for the next process.
   The X1's broker tolerates ~4 clients; two of our own listeners fighting
   over one printer is the failure this prevents.
2. A printer whose lock is already held is skipped by the supervisor rather
   than connected to anyway.
3. A printer that can't be dialled is skipped and the reason is recorded on
   ``PrinterProfile.last_error``, where the parent's printer card shows it.
4. Only unsolicited ``push_status`` reports reach the state merge. Command
   acknowledgements carry a ``print`` key too, and merging one corrupts state.
5. Fan-out writes a snapshot the status endpoint can serve, so the SPA reads
   Redis instead of opening its own connection to the printer.
"""
from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.printing import fanout
from apps.printing.listener import ListenerSupervisor, PrinterListener, PrinterLock
from apps.printing.models import PrinterProfile, PrintJob
from apps.printing.transports.memory import InMemoryTransport
from config.tests.factories import make_family

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "printing-listener-tests",
    },
}


@override_settings(CACHES=LOCMEM)
class _Fixture(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.printer = PrinterProfile.objects.create(
            family=self.household.family,
            name="Garage X1C",
            serial="00M09A000000001",
            host="192.168.1.50",
        )
        self.printer.set_secrets(access_code="12345678")
        self.printer.save(update_fields=["encrypted_secret"])

    def make_listener(self):
        """A listener wired to an in-memory transport, never started."""
        return PrinterListener(
            self.printer, transport=InMemoryTransport(on_payload=lambda p: None),
        )


class PrinterLockTests(_Fixture):
    def test_the_first_acquire_wins(self):
        lock = PrinterLock(self.printer.serial, "listener-a")
        self.assertTrue(lock.acquire())
        self.assertTrue(lock.held)

    def test_a_second_holder_is_refused(self):
        first = PrinterLock(self.printer.serial, "listener-a")
        second = PrinterLock(self.printer.serial, "listener-b")
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        self.assertFalse(second.held)

    def test_locks_on_different_printers_do_not_collide(self):
        self.assertTrue(PrinterLock("SERIAL-A", "listener-a").acquire())
        self.assertTrue(PrinterLock("SERIAL-B", "listener-a").acquire())

    def test_refresh_keeps_a_lock_we_still_hold(self):
        lock = PrinterLock(self.printer.serial, "listener-a")
        lock.acquire()
        self.assertTrue(lock.refresh())
        self.assertTrue(lock.held)

    def test_refresh_fails_and_drops_the_lock_when_somebody_else_took_it(self):
        lock = PrinterLock(self.printer.serial, "listener-a")
        lock.acquire()
        cache.set(f"printing:listener-lock:{self.printer.serial}", "listener-b", 90)
        self.assertFalse(lock.refresh())
        self.assertFalse(lock.held)

    def test_refresh_on_a_lock_we_never_held_is_false(self):
        self.assertFalse(PrinterLock(self.printer.serial, "listener-a").refresh())

    def test_release_frees_the_lock_for_the_next_process(self):
        first = PrinterLock(self.printer.serial, "listener-a")
        first.acquire()
        first.release()
        self.assertFalse(first.held)
        self.assertTrue(PrinterLock(self.printer.serial, "listener-b").acquire())

    def test_release_never_steals_a_lock_somebody_else_now_owns(self):
        first = PrinterLock(self.printer.serial, "listener-a")
        first.acquire()
        cache.set(f"printing:listener-lock:{self.printer.serial}", "listener-b", 90)
        first.release()
        self.assertEqual(
            cache.get(f"printing:listener-lock:{self.printer.serial}"), "listener-b",
        )


@override_settings(CACHES=LOCMEM)
class ListenerSupervisorTests(_Fixture):
    def test_sync_skips_a_printer_whose_lock_is_already_held(self):
        held = PrinterLock(self.printer.serial, "some-other-process")
        self.assertTrue(held.acquire())

        supervisor = ListenerSupervisor(owner="this-process")
        supervisor.sync()

        self.assertEqual(supervisor.listeners, {})
        self.assertEqual(
            cache.get(f"printing:listener-lock:{self.printer.serial}"),
            "some-other-process",
        )

    def test_sync_skips_a_printer_with_no_credentials(self):
        bare = PrinterProfile.objects.create(
            family=self.household.family,
            name="Unconfigured P1S",
            serial="00M09A000000002",
        )
        # Take the configured printer out of the picture so this test is only
        # about the credential-less one.
        self.printer.is_active = False
        self.printer.save(update_fields=["is_active"])

        supervisor = ListenerSupervisor(owner="this-process")
        supervisor.sync()

        self.assertNotIn(bare.pk, supervisor.listeners)
        # And it never even reached for the lock, so another process could.
        self.assertTrue(PrinterLock(bare.serial, "someone-else").acquire())

    def test_sync_records_why_a_printer_could_not_be_dialled(self):
        self.printer.transport = "carrier-pigeon"
        self.printer.save(update_fields=["transport"])

        supervisor = ListenerSupervisor(owner="this-process")
        supervisor.sync()

        self.assertEqual(supervisor.listeners, {})
        self.printer.refresh_from_db()
        self.assertIn("carrier-pigeon", self.printer.last_error)
        # The lock is handed back so a healthier process can try.
        self.assertTrue(PrinterLock(self.printer.serial, "someone-else").acquire())

    def test_sync_drops_a_printer_that_was_deactivated(self):
        supervisor = ListenerSupervisor(owner="this-process")
        lock = PrinterLock(self.printer.serial, "this-process")
        lock.acquire()
        supervisor.listeners[self.printer.pk] = self.make_listener()
        supervisor.locks[self.printer.pk] = lock

        self.printer.is_active = False
        self.printer.save(update_fields=["is_active"])
        supervisor.sync()

        self.assertEqual(supervisor.listeners, {})
        self.assertTrue(PrinterLock(self.printer.serial, "someone-else").acquire())


@override_settings(CACHES=LOCMEM)
class ProcessGateTests(_Fixture):
    def test_a_command_acknowledgement_never_reaches_the_state_merge(self):
        listener = self.make_listener()
        listener.process({"print": {
            "command": "project_file",
            "msg": 0,
            "gcode_state": "RUNNING",
            "subtask_name": "req-0001-dragon",
        }})
        self.assertEqual(listener.state.gcode_state, "")
        self.assertEqual(listener.state.subtask_name, "")
        self.assertFalse(listener.state.seeded)
        self.assertFalse(PrintJob.objects.exists())

    def test_a_payload_with_no_print_block_is_ignored(self):
        listener = self.make_listener()
        listener.process({"info": {"command": "get_version", "sequence_id": "1"}})
        self.assertEqual(listener.state.gcode_state, "")

    def test_a_push_status_report_does_reach_the_merge(self):
        listener = self.make_listener()
        listener.process({"print": {
            "command": "push_status",
            "msg": 0,
            "gcode_state": "IDLE",
            "layer_num": 0,
            "total_layer_num": 0,
        }})
        self.assertEqual(listener.state.gcode_state, "IDLE")
        self.assertTrue(listener.state.seeded)

    def test_a_cloud_lifecycle_envelope_flips_online_without_merging(self):
        listener = self.make_listener()
        listener.process({"event": {"event": "client.disconnected"}})
        self.assertFalse(listener.state.online)
        self.assertEqual(listener.state.gcode_state, "")

        listener.process({"event": {"event": "client.connected"}})
        self.assertTrue(listener.state.online)


@override_settings(CACHES=LOCMEM)
class FanoutTests(_Fixture):
    def test_read_state_is_cold_until_the_listener_publishes(self):
        self.assertIsNone(fanout.read_state(self.printer.serial))

    def test_publish_state_writes_a_snapshot_read_state_can_serve(self):
        listener = self.make_listener()
        listener.process({"print": {
            "command": "push_status",
            "msg": 0,
            "gcode_state": "RUNNING",
            "subtask_name": "req-0042-dragon",
            "gcode_file": "/data/Metadata/plate_1.gcode",
            "layer_num": 12,
            "total_layer_num": 340,
            "mc_percent": 4,
            "mc_remaining_time": 176,
            "print_error": 0,
            "hms": [],
        }})

        snapshot = fanout.read_state(self.printer.serial)
        self.assertIsNotNone(snapshot)
        # Exactly the fields GET /api/printers/<id>/status/ promises under "live".
        for key in (
            "serial", "online", "gcode_state", "subtask_name", "gcode_file",
            "plate_index", "layer_num", "total_layer_num", "percent",
            "remaining_minutes", "print_error", "hms", "seeded",
        ):
            self.assertIn(key, snapshot)
        self.assertEqual(snapshot["gcode_state"], "RUNNING")
        self.assertEqual(snapshot["subtask_name"], "req-0042-dragon")
        self.assertEqual(snapshot["percent"], 4)
        self.assertEqual(snapshot["remaining_minutes"], 176)
        self.assertEqual(snapshot["plate_index"], 1)

    def test_snapshots_are_scoped_per_serial(self):
        fanout.publish_state("SERIAL-A", {"serial": "SERIAL-A"})
        self.assertEqual(fanout.read_state("SERIAL-A"), {"serial": "SERIAL-A"})
        self.assertIsNone(fanout.read_state("SERIAL-B"))

    def test_publishing_never_raises_even_with_no_redis(self):
        # Fan-out is best effort: a cache/Redis outage must not break ingest.
        fanout.publish_state(self.printer.serial, {"serial": self.printer.serial})
