"""Transport factory — the one place that knows which broker to dial.

Everything above this package speaks :class:`PrinterTransport`. Moving a
household from the LAN broker to Bambu's cloud broker is a value change on
``PrinterProfile.transport``; no calling code changes.
"""
from __future__ import annotations

from ..models import PrinterProfile
from .base import (
    PahoTransportBase,
    PayloadHandler,
    PrinterTransport,
    StatusHandler,
    TransportAuthError,
    TransportConfig,
    TransportError,
)
from .cloud import CloudMqttTransport, build_cloud_config
from .local import LocalMqttTransport, build_local_config
from .memory import InMemoryTransport

__all__ = [
    "CloudMqttTransport",
    "InMemoryTransport",
    "LocalMqttTransport",
    "PahoTransportBase",
    "PayloadHandler",
    "PrinterTransport",
    "StatusHandler",
    "TransportAuthError",
    "TransportConfig",
    "TransportError",
    "build_transport",
]

_BUILDERS = {
    PrinterProfile.Transport.LOCAL: (build_local_config, LocalMqttTransport),
    PrinterProfile.Transport.CLOUD: (build_cloud_config, CloudMqttTransport),
}


def build_transport(printer, *, on_payload, on_status=None) -> PrinterTransport:
    """Return a started-but-not-connected transport for ``printer``.

    Raises :class:`TransportError` when the profile is missing the
    credentials its transport needs — the supervisor catches that, records it
    on ``PrinterProfile.last_error`` so the parent sees it on the printer
    card, and moves on to the next printer rather than dying.
    """
    try:
        build_config, transport_class = _BUILDERS[printer.transport]
    except KeyError:
        raise TransportError(
            f"Unknown transport {printer.transport!r} on {printer.name}.",
        ) from None
    return transport_class(
        build_config(printer), on_payload=on_payload, on_status=on_status,
    )
