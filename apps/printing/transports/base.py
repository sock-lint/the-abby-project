"""Transport interface for talking to a printer.

The listener is written entirely against :class:`PrinterTransport`. Swapping
the LAN broker for Bambu's cloud broker is a value change on
``PrinterProfile.transport`` — not a rewrite — because everything above this
line only ever sees "a stream of decoded JSON payloads".

Three implementations ship:

============  =====================================================
``local``     :class:`~apps.printing.transports.local.LocalMqttTransport`
              — the printer's own broker on the LAN, port 8883.
``cloud``     :class:`~apps.printing.transports.cloud.CloudMqttTransport`
              — ``us.mqtt.bambulab.com:8883`` with a Bambu account uid +
              access token. The fallback for a firmware release that locks
              the local broker down.
``memory``    :class:`~apps.printing.transports.memory.InMemoryTransport`
              — no network at all. Tests (and ``--replay``) push payloads
              through the same code path a real broker would.
============  =====================================================

Both MQTT transports use identical topics (``device/<serial>/report`` and
``device/<serial>/request``) and an identical payload schema; they differ
only in host, credentials and TLS policy. That commonality lives in
:class:`PahoTransportBase` so neither subclass re-implements the callback
plumbing, the backoff policy, or the not-authorized guard.
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

#: Payload handler: called with one decoded report dict per message.
PayloadHandler = Callable[[dict], None]
#: Status handler: called with (state, detail) on connection lifecycle changes.
#: ``state`` is one of "connected" / "disconnected" / "error".
StatusHandler = Callable[[str, str], None]


class TransportError(Exception):
    """Transport could not be built or started."""


class TransportAuthError(TransportError):
    """Credentials were rejected — retrying will not help.

    CONNACK reason code 5 ("Not authorized") means a wrong serial, a wrong
    access code, or the wrong IP. Reconnecting on a loop hammers the printer
    and, on the cloud broker, risks a multi-day account ban — so this is
    surfaced as a configuration error rather than a transient failure.
    """


@dataclass
class TransportConfig:
    """Everything a transport needs, with no Django model dependency.

    Keeping this a plain dataclass is what lets the tests drive a transport
    without a database.
    """

    serial: str
    host: str = ""
    port: int = 8883
    username: str = ""
    password: str = ""
    #: TLS verification policy. Local printers present a self-signed cert whose
    #: CN is the SERIAL, not the IP, so hostname checking can never pass;
    #: the cloud broker has an ordinary DigiCert cert that verifies normally.
    verify_tls: bool = True
    check_hostname: bool = True
    ca_cert_path: str = ""
    #: Some firmware never answers a TLS 1.3 ClientHello and hangs the
    #: handshake until timeout, so the local transport caps at 1.2.
    max_tls_version: str = ""
    keepalive: int = 30
    label: str = ""

    @property
    def report_topic(self) -> str:
        return f"device/{self.serial}/report"

    @property
    def request_topic(self) -> str:
        return f"device/{self.serial}/request"


class PrinterTransport(ABC):
    """One live connection to one printer.

    Implementations must be safe to ``stop()`` from another thread and must
    never raise out of their own network callbacks — a transport that dies on
    a malformed frame takes the whole listener with it.
    """

    def __init__(self, config: TransportConfig, *, on_payload: PayloadHandler,
                 on_status: StatusHandler | None = None):
        self.config = config
        self.on_payload = on_payload
        self.on_status = on_status or (lambda state, detail: None)

    @abstractmethod
    def start(self) -> None:
        """Connect and begin delivering payloads. Non-blocking."""

    @abstractmethod
    def stop(self) -> None:
        """Disconnect and release the socket. Idempotent."""

    @abstractmethod
    def publish(self, payload: dict) -> None:
        """Send a command to the printer's request topic."""

    def request_full_status(self) -> None:
        """Ask for a complete state snapshot.

        Reports are **deltas**: a routine ``msg: 1`` payload carries only the
        keys that changed since the last one, so a listener that connects
        mid-print never learns ``subtask_name`` or ``total_layer_num`` —
        those didn't change while it was listening. ``pushall`` forces one
        full snapshot (delivered as ``msg: 0``) to seed state.

        Rate-limited by convention, not by us: send it on connect and when a
        watchdog sees a stale stream, never on a short timer.
        """
        self.publish({
            "pushing": {
                "sequence_id": "0",
                "command": "pushall",
                "version": 1,
                "push_target": 1,
            },
        })


# --------------------------------------------------------------------------- #
# Shared paho implementation
# --------------------------------------------------------------------------- #
def _require_paho():
    try:
        import paho.mqtt.client as mqtt  # noqa: PLC0415 - optional dependency
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise TransportError(
            "paho-mqtt is not installed. Add `paho-mqtt` to requirements.txt "
            "(the listener process needs it; the web and celery containers "
            "never open an MQTT socket).",
        ) from exc
    return mqtt


class PahoTransportBase(PrinterTransport):
    """Common paho-mqtt 2.x plumbing for both Bambu brokers.

    Subclasses supply a :class:`TransportConfig`; everything below —
    callbacks, backoff, JSON tolerance, the not-authorized guard — is shared.
    """

    def __init__(self, config, *, on_payload, on_status=None):
        super().__init__(config, on_payload=on_payload, on_status=on_status)
        self._client = None
        self._stopped = threading.Event()
        self._fatal_auth_error = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        mqtt = _require_paho()
        from paho.mqtt.client import CallbackAPIVersion

        if not self.config.serial:
            raise TransportError("Printer serial is required to build the MQTT topic.")
        if not self.config.host:
            raise TransportError("No host configured for this printer.")

        # A RANDOM client id per process is load-bearing: two clients sharing
        # an id kick each other off the broker in a loop, which is the fastest
        # way to trip the printer's ~4-connection ceiling.
        client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=f"abby-{uuid.uuid4().hex[:12]}",
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        client.username_pw_set(self.config.username, self.config.password)
        client.tls_set_context(self._build_ssl_context())
        # Exponential backoff, capped. Never reconnect in a tight loop: Bambu
        # bans cloud accounts that thrash, and the ban locks the household out
        # of their own Studio and Handy apps for days.
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        self._client = client
        self._stopped.clear()
        client.connect_async(
            self.config.host, self.config.port, keepalive=self.config.keepalive,
        )
        client.loop_start()

    def stop(self) -> None:
        self._stopped.set()
        client, self._client = self._client, None
        if client is None:
            return
        try:
            client.disconnect()
        finally:
            client.loop_stop()

    def publish(self, payload: dict) -> None:
        if self._client is None:
            raise TransportError("Transport is not started.")
        self._client.publish(self.config.request_topic, json.dumps(payload), qos=0)

    # -- TLS ---------------------------------------------------------------
    def _build_ssl_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        if self.config.ca_cert_path:
            context.load_verify_locations(cafile=self.config.ca_cert_path)

        # Python 3.13+ turns on VERIFY_X509_STRICT by default and Bambu's CA
        # omits the keyUsage extension, which trips "CA cert does not include
        # key usage extension". Clearing the flag is the documented workaround.
        context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)

        # ORDER IS LOAD-BEARING. create_default_context() returns a context
        # with check_hostname=True, and Python refuses to set CERT_NONE while
        # it is still on ("Cannot set verify_mode to CERT_NONE when
        # check_hostname is enabled"). So check_hostname must be cleared
        # FIRST. Getting this backwards raises on every single connect, and
        # the LAN transport takes that branch by default — verify_tls is
        # False until PRINT_BAMBU_CA_CERT is configured.
        context.check_hostname = self.config.check_hostname and self.config.verify_tls
        if not self.config.verify_tls:
            context.verify_mode = ssl.CERT_NONE

        if self.config.max_tls_version == "1.2":
            context.maximum_version = ssl.TLSVersion.TLSv1_2
        return context

    # -- callbacks (paho 2.x VERSION2 signatures) --------------------------
    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        if reason_code != 0:
            detail = str(reason_code)
            # "Not authorized" is terminal: wrong serial, wrong access code or
            # wrong IP. Stop the auto-reconnect rather than hammering.
            if "not authorized" in detail.lower() or getattr(reason_code, "value", None) == 5:
                self._fatal_auth_error = True
                client.loop_stop()
                self.on_status("error", f"Access denied by the printer ({detail}).")
                logger.error("printing[%s]: %s", self.config.label, detail)
                return
            self.on_status("error", detail)
            return

        client.subscribe(self.config.report_topic, qos=0)
        self.on_status("connected", "")
        # Seed state immediately — see request_full_status().
        try:
            self.request_full_status()
        except Exception as exc:  # noqa: BLE001 - never raise out of a callback
            logger.warning("printing[%s]: pushall failed: %s", self.config.label, exc)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if self._stopped.is_set():
            return
        self.on_status("disconnected", str(reason_code))

    def _on_message(self, client, userdata, message):
        # Nothing may escape this method: paho will not restart the network
        # loop for us, so one unhandled exception silently ends the stream.
        try:
            payload = json.loads(message.payload.decode("utf-8", errors="replace"))
        except (ValueError, AttributeError):
            logger.debug("printing[%s]: dropped a malformed frame", self.config.label)
            return
        if not isinstance(payload, dict):
            return
        try:
            self.on_payload(payload)
        except Exception:  # noqa: BLE001 - log and keep the stream alive
            logger.exception("printing[%s]: payload handler raised", self.config.label)

    @property
    def has_fatal_auth_error(self) -> bool:
        return self._fatal_auth_error
