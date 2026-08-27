"""Follow-up defects found while reviewing the Forge's own code.

1. ``GET /api/printers/<id>/status/`` handed any authenticated family member
   the full open job — including a sibling's request title and owner name.
   The UI hid it; the UI is not the access control. The ``live`` snapshot
   leaked the same identity by a second route: ``subtask_name`` IS the plate
   filename, which embeds the slug, which spells out the title.
2. ``ListenerSupervisor.sync`` skipped a printer with no saved credentials
   silently, so the most common misconfiguration ("access code never
   entered") showed the parent nothing at all on the printer card.
3. ``PahoTransportBase._build_ssl_context`` set ``verify_mode = CERT_NONE``
   before clearing ``check_hostname``, which Python rejects outright. The LAN
   transport takes that branch by default (``verify_tls`` is False until
   ``PRINT_BAMBU_CA_CERT`` is set), so every local connect raised ValueError.
"""
from __future__ import annotations

import pathlib
import tempfile
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from config.tests.factories import make_family

from apps.printing.fanout import publish_state
from apps.printing.listener import ListenerSupervisor
from apps.printing.models import PrinterProfile, PrintJob, PrintRequest

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "printing-followups",
    },
}


class _Fixture:
    def build_family(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}, {"username": "sibling"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        self.sibling = self.household.children[1]
        self.printer = PrinterProfile.objects.create(
            family=self.household.family,
            name="Garage X1C",
            serial="00M09A000000001",
            host="192.168.1.50",
        )


class LiveStatusPrivacyTests(_Fixture, APITestCase):
    def setUp(self):
        self.build_family()
        self.request = PrintRequest.objects.create(
            user=self.sibling,
            title="Secret birthday gift",
            reason="shh",
            color="gold",
            status=PrintRequest.Status.PRINTING,
            slug="req-0001-secret-birthday-gift",
        )
        self.job = PrintJob.objects.create(
            printer=self.printer,
            request=self.request,
            user=self.sibling,
            subtask_name="req-0001-secret-birthday-gift",
            normalized_name="req-0001-secret-birthday-gift",
            state=PrintJob.State.RUNNING,
        )
        self.url = f"/api/printers/{self.printer.id}/status/"

    def test_a_child_cannot_read_a_siblings_print_details(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)

        body = resp.content.decode()
        self.assertNotIn("Secret birthday gift", body)
        self.assertNotIn("req-0001-secret-birthday-gift", body)
        self.assertNotIn("sibling", body)

    def test_a_child_is_still_told_the_printer_is_busy(self):
        # "Can I print now?" is a fair question; the answer just isn't "with
        # your sibling's birthday present".
        self.client.force_authenticate(self.child)
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.json()["job"], {"busy_with_someone_elses_print": True},
        )

    def test_the_owner_sees_her_own_print_in_full(self):
        self.client.force_authenticate(self.sibling)
        resp = self.client.get(self.url)
        self.assertEqual(resp.json()["job"]["request_title"], "Secret birthday gift")

    def test_a_parent_sees_the_whole_job(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(self.url)
        self.assertEqual(resp.json()["job"]["request_title"], "Secret birthday gift")

    def test_an_idle_printer_reports_no_job_to_anyone(self):
        self.job.delete()
        for user in (self.child, self.sibling, self.parent):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertIsNone(self.client.get(self.url).json()["job"])

    @override_settings(CACHES=LOCMEM)
    def test_the_live_snapshot_itself_carries_no_request_identity(self):
        # The fan-out snapshot is printer telemetry, not request data — it is
        # served to every family member, so it must stay that way.
        cache.clear()
        publish_state(self.printer.serial, {
            "serial": self.printer.serial, "gcode_state": "RUNNING",
            "subtask_name": "req-0001-secret-birthday-gift",
        })
        self.client.force_authenticate(self.child)
        live = self.client.get(self.url).json()["live"]
        # subtask_name IS the plate name, which embeds the slug — so a child
        # must not get the snapshot verbatim either.
        self.assertNotIn("secret-birthday-gift", str(live or ""))
        self.assertNotIn("subtask_name", live)
        # The telemetry that is not identity survives.
        self.assertEqual(live["gcode_state"], "RUNNING")

    @override_settings(CACHES=LOCMEM)
    def test_the_owner_gets_the_snapshot_intact(self):
        cache.clear()
        publish_state(self.printer.serial, {
            "serial": self.printer.serial, "gcode_state": "RUNNING",
            "subtask_name": "req-0001-secret-birthday-gift",
        })
        self.client.force_authenticate(self.sibling)
        live = self.client.get(self.url).json()["live"]
        self.assertEqual(live["subtask_name"], "req-0001-secret-birthday-gift")


@override_settings(CACHES=LOCMEM)
class SupervisorSurvivesDatabaseTroubleTests(_Fixture, TestCase):
    """The listener outlives deploys, so a bad pass must not end the process.

    Two real cases: this container can start before the ``django`` service
    has migrated (the printing tables genuinely do not exist yet), and
    Postgres restarts under a rolling deploy. Either killing the process
    means dropping the MQTT connection — and if that lands mid-print the
    FINISH transition is missed entirely.
    """

    def setUp(self):
        self.build_family()
        cache.clear()

    def _run_one_pass(self, supervisor):
        """Drive exactly one loop iteration, then stop."""
        original = supervisor.sync

        def once(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            finally:
                supervisor.stop()

        supervisor.sync = once
        supervisor.poll_interval = 0
        supervisor.run_forever()

    def test_unmigrated_tables_are_waited_out_not_fatal(self):
        from django.db import ProgrammingError

        supervisor = ListenerSupervisor(owner="test", poll_interval=0)
        with patch.object(
            ListenerSupervisor, "sync",
            side_effect=ProgrammingError('relation "printing_printrequest" does not exist'),
        ):
            self._run_one_pass(supervisor)  # must return, not raise

    def test_a_dead_connection_is_waited_out_not_fatal(self):
        from django.db import OperationalError

        supervisor = ListenerSupervisor(owner="test", poll_interval=0)
        with patch.object(
            ListenerSupervisor, "sync",
            side_effect=OperationalError("server closed the connection unexpectedly"),
        ):
            self._run_one_pass(supervisor)

    def test_an_unexpected_error_is_logged_and_the_loop_continues(self):
        supervisor = ListenerSupervisor(owner="test", poll_interval=0)
        with patch.object(ListenerSupervisor, "sync", side_effect=RuntimeError("boom")):
            self._run_one_pass(supervisor)

    def test_a_healthy_pass_still_runs_normally(self):
        supervisor = ListenerSupervisor(owner="test", poll_interval=0)
        self._run_one_pass(supervisor)
        # No credentials on the fixture printer, so it is skipped with a reason
        # rather than dialled — the pass completed either way.
        self.printer.refresh_from_db()
        self.assertIn("access code", self.printer.last_error)


@override_settings(CACHES=LOCMEM)
class HeartbeatTests(_Fixture, TestCase):
    """The compose healthcheck reads a heartbeat file, not `pgrep`.

    The runtime image is python:3.12-slim, which ships no `procps`, so a
    `pgrep` healthcheck exits 127 and the container is unhealthy forever.
    The heartbeat is also a better probe: a supervisor whose loop has wedged
    stops stamping it, where the process still exists.
    """

    def setUp(self):
        self.build_family()
        cache.clear()
        self.beat = pathlib.Path(tempfile.mkdtemp()) / "heartbeat"

    def _run_one_pass(self, supervisor):
        original = supervisor.sync

        def once(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            finally:
                supervisor.stop()

        supervisor.sync = once
        supervisor.run_forever()

    def test_a_pass_stamps_the_heartbeat(self):
        supervisor = ListenerSupervisor(
            owner="test", poll_interval=0, heartbeat_path=str(self.beat),
        )
        self.assertFalse(self.beat.exists())
        self._run_one_pass(supervisor)
        self.assertTrue(self.beat.exists())
        # Recent enough that the 120s healthcheck window passes.
        self.assertLess(time.time() - self.beat.stat().st_mtime, 5)

    def test_a_pass_that_failed_still_heartbeats(self):
        # Waiting out a migration is alive. If this stopped stamping, every
        # deploy would restart the container mid-wait for no reason.
        from django.db import OperationalError

        supervisor = ListenerSupervisor(
            owner="test", poll_interval=0, heartbeat_path=str(self.beat),
        )
        with patch.object(
            ListenerSupervisor, "sync", side_effect=OperationalError("down"),
        ):
            self._run_one_pass(supervisor)
        self.assertTrue(self.beat.exists())

    def test_an_unwritable_path_does_not_take_the_listener_down(self):
        supervisor = ListenerSupervisor(
            owner="test", poll_interval=0,
            heartbeat_path="/nonexistent-dir/heartbeat",
        )
        self._run_one_pass(supervisor)  # must not raise


class SslContextTests(TestCase):
    """The LAN default path must actually build a context.

    ``ssl.create_default_context()`` starts with ``check_hostname=True`` and
    Python refuses ``CERT_NONE`` while it is on, so the order of those two
    assignments is load-bearing rather than stylistic.
    """

    def _config(self, **over):
        from apps.printing.transports.base import TransportConfig

        base = {
            "serial": "00M09A000000001", "host": "192.168.1.50",
            "verify_tls": False, "check_hostname": False,
            "max_tls_version": "1.2",
        }
        base.update(over)
        return TransportConfig(**base)

    def _context(self, config):
        from apps.printing.transports.base import PahoTransportBase

        transport = PahoTransportBase(config, on_payload=lambda payload: None)
        return transport._build_ssl_context()  # noqa: SLF001 - that is the unit

    def test_the_unverified_lan_default_builds(self):
        import ssl

        context = self._context(self._config())
        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)

    def test_a_verified_lan_context_still_skips_hostname_checking(self):
        # With Bambu's CA supplied we verify the chain, but the cert's CN is
        # the printer serial and we dial an IP, so hostname checking can never
        # pass.
        import ssl

        context = self._context(self._config(verify_tls=True, check_hostname=False))
        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_the_cloud_context_verifies_fully(self):
        import ssl

        context = self._context(self._config(
            verify_tls=True, check_hostname=True, max_tls_version="",
        ))
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertNotEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)

    def test_strict_x509_is_cleared_for_bambus_ca(self):
        import ssl

        strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
        if not strict:  # pragma: no cover - Python < 3.13
            self.skipTest("VERIFY_X509_STRICT not present on this Python")
        context = self._context(self._config(verify_tls=True))
        self.assertFalse(context.verify_flags & strict)


@override_settings(CACHES=LOCMEM)
class MissingCredentialsAreReportedTests(_Fixture, TestCase):
    def setUp(self):
        self.build_family()
        cache.clear()

    def test_sync_says_why_it_skipped_a_printer_with_no_access_code(self):
        supervisor = ListenerSupervisor(owner="test")
        supervisor.sync()

        self.printer.refresh_from_db()
        self.assertNotIn(self.printer.pk, supervisor.listeners)
        self.assertIn("LAN access code", self.printer.last_error)

    def test_a_cloud_printer_names_the_credentials_it_wants(self):
        self.printer.transport = PrinterProfile.Transport.CLOUD
        self.printer.save(update_fields=["transport"])

        ListenerSupervisor(owner="test").sync()

        self.printer.refresh_from_db()
        self.assertIn("access token", self.printer.last_error)

    def test_a_configured_printer_is_not_stamped_with_an_error(self):
        self.printer.set_secrets(access_code="12345678")
        self.printer.save(update_fields=["encrypted_secret"])

        # start() will fail without a broker; we only care that sync got past
        # the credential gate rather than short-circuiting on it.
        ListenerSupervisor(owner="test").sync()

        self.printer.refresh_from_db()
        self.assertNotIn("No LAN access code", self.printer.last_error)
