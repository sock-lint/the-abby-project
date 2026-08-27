"""LAN transport — the printer's own embedded MQTT broker.

Connection facts, all of which are load-bearing:

* Host is the printer's LAN IP. It does not register mDNS reliably, so this
  is configured by hand on the ``PrinterProfile``.
* Port 8883, TLS mandatory — there is no plaintext port.
* Username is the literal string ``bblp``. Password is the 8-character **LAN
  Access Code** from the printer's touchscreen (Settings → Network) — not the
  serial, not the Bambu account password. It rotates if the user regenerates
  it on screen.
* LAN-Only Mode is **not** required: the local broker keeps pushing status
  while the printer is in Cloud mode, and reading status is all a listener
  needs. (Sending *control* commands is a different story — firmware
  01.08.02+ rejects unsigned third-party writes with
  ``HMS_0500_0500_0001_0007`` unless the printer is in LAN-Only + Developer
  Mode. We only ever publish ``pushall``, which is a read.)
* The certificate is self-signed by Bambu's own CA **and its CN is the
  printer serial, not the IP**, so hostname verification can never succeed
  against ``192.168.x.x``. We therefore always set ``check_hostname=False``.
  With ``PRINT_BAMBU_CA_CERT`` pointed at Bambu's CA PEM the chain is still
  verified; without it we fall back to an unverified TLS session on the
  local network, which is what every mainstream integration does.
"""
from __future__ import annotations

from django.conf import settings

from .base import PahoTransportBase, TransportConfig, TransportError

#: The printer's local broker only ever accepts this username.
LOCAL_USERNAME = "bblp"


def build_local_config(printer) -> TransportConfig:
    secrets = printer.get_secrets()
    access_code = secrets.get("access_code") or ""
    if not access_code:
        raise TransportError(
            f"{printer.name} has no LAN access code saved. Add it in "
            f"Manage → Printers (it's on the printer screen under "
            f"Settings → Network).",
        )
    if not printer.host:
        raise TransportError(f"{printer.name} has no LAN IP address configured.")

    ca_path = getattr(settings, "PRINT_BAMBU_CA_CERT", "") or ""
    return TransportConfig(
        serial=printer.serial,
        host=printer.host,
        port=printer.port or 8883,
        username=LOCAL_USERNAME,
        password=access_code,
        # Verify the chain when we've been given Bambu's CA; never verify the
        # hostname, because the CN is the serial and we dial an IP.
        verify_tls=bool(ca_path),
        check_hostname=False,
        ca_cert_path=ca_path,
        max_tls_version="1.2",
        keepalive=30,
        label=printer.serial,
    )


class LocalMqttTransport(PahoTransportBase):
    """MQTT over the LAN to the printer's embedded broker."""
