"""Bambu Cloud transport — the fallback if the local broker gets locked down.

Same topics, same payload schema, same delta semantics as
:mod:`~apps.printing.transports.local`. Only three things differ:

* Host is ``us.mqtt.bambulab.com`` (``cn.mqtt.bambulab.com`` for a
  China-region account — region is a property of the *account*, not the
  printer, and a China account will not authenticate against the US host).
* Username is ``u_<uid>`` — a literal ``u``, an underscore, and the **decimal
  numeric Bambu user id**. Not the email, not the serial. Password is the
  full ``accessToken``, verbatim, with no ``Bearer`` prefix.
* TLS verifies normally. The cloud broker's certificate is DigiCert-issued
  with CN ``*.mqtt.bambulab.com``, which matches the host — so the system
  trust store and hostname checking are both correct here. **Do not** copy
  the local transport's relaxed policy.

Obtaining the credentials (a one-time manual step the parent does, and why
this is a config change rather than an integration):

1. ``POST https://api.bambulab.com/v1/user-service/user/login`` with
   ``{"account": <email>, "password": <password>}`` → ``accessToken``.
   A ``loginType`` of ``verifyCode`` means the account uses an e-mailed code:
   request one at ``/v1/user-service/user/sendemail/code`` and repeat the
   login with ``code`` instead of ``password``.
2. ``GET https://api.bambulab.com/v1/design-user-service/my/preference`` with
   ``Authorization: Bearer <accessToken>`` → ``uid``.

Tokens last roughly three months (``expiresIn: 7776000``). The refresh
endpoint returns 401 in practice, so on expiry the parent re-runs the login
and pastes a new token — the listener surfaces the auth failure on the
printer card rather than retrying, for the reason below.

Ban risk, which is why the backoff in :class:`PahoTransportBase` matters
more here than on the LAN: Bambu issues 24-hour-to-7-day account bans for
exceeding ~50 concurrent connections, and a reconnect loop in a third-party
client is the documented cause. During a ban the household cannot use
Bambu Studio or Handy either. One connection, exponential backoff, and a
hard stop on "not authorized" are not optional.
"""
from __future__ import annotations

from django.conf import settings

from .base import PahoTransportBase, TransportConfig, TransportError

DEFAULT_CLOUD_HOST = "us.mqtt.bambulab.com"
DEFAULT_CLOUD_PORT = 8883


def build_cloud_config(printer) -> TransportConfig:
    secrets = printer.get_secrets()
    uid = str(secrets.get("cloud_user_id") or "").strip()
    token = (secrets.get("cloud_token") or "").strip()
    if not uid or not token:
        raise TransportError(
            f"{printer.name} is set to the cloud transport but has no Bambu "
            f"user id / access token saved. Add them in Manage → Printers.",
        )

    return TransportConfig(
        serial=printer.serial,
        host=getattr(settings, "PRINT_BAMBU_CLOUD_HOST", DEFAULT_CLOUD_HOST),
        port=getattr(settings, "PRINT_BAMBU_CLOUD_PORT", DEFAULT_CLOUD_PORT),
        username=f"u_{uid}",
        password=token,
        # Public CA, matching CN — full verification, and no TLS-version cap.
        verify_tls=True,
        check_hostname=True,
        ca_cert_path="",
        max_tls_version="",
        keepalive=30,
        label=f"{printer.serial}@cloud",
    )


class CloudMqttTransport(PahoTransportBase):
    """MQTT to Bambu's hosted broker."""
