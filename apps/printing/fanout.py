"""Fan out printer state from our single connection.

The X1's embedded broker accepts only about **four** simultaneous MQTT
clients. Bambu Studio holds one while it's open, Handy holds one, and
Home Assistant's integration holds one — so a naive "just connect from
Django, and from Celery, and from the status endpoint" design blows past the
ceiling immediately. The failure mode is nasty and non-obvious: the broker
silently drops the newest (or an existing) client, so our listener and Home
Assistant end up fighting, each reconnecting as the other kicks it off.

So: **exactly one connection to the printer, ever**, owned by the listener
process, and everything else reads from here.

Three fan-out surfaces, in order of how much they matter:

1. **Cache snapshot** — the latest merged state under a well-known key. This
   is what ``GET /api/printers/<id>/status/`` serves, so the SPA's live view
   costs a Redis read rather than a printer connection.
2. **Redis pub/sub** — ``abby:printing:<serial>`` carries every snapshot as
   JSON, for anything that wants a push stream from us.
3. **Optional MQTT republish** — when ``PRINT_FANOUT_MQTT_URL`` names a
   broker (a household Mosquitto, say), snapshots are republished to
   ``abby/printers/<serial>/state``. Point Home Assistant at *that* instead
   of at the printer and the flapping stops.

Every publisher here is best-effort: fan-out failing must never break ingest.
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: How long a snapshot stays readable after the listener stops updating it.
#: Longer than the watchdog interval so a brief reconnect doesn't blank the UI,
#: short enough that a dead listener stops looking live.
SNAPSHOT_TTL_SECONDS = 300

CHANNEL_PREFIX = "abby:printing"
REPUBLISH_TOPIC = "abby/printers/{serial}/state"


def snapshot_key(serial: str) -> str:
    return f"printing:state:{serial}"


def channel_for(serial: str) -> str:
    return f"{CHANNEL_PREFIX}:{serial}"


def read_state(serial: str) -> dict | None:
    """Latest known snapshot for a printer, or ``None`` if the listener is cold."""
    return cache.get(snapshot_key(serial))


def publish_state(serial: str, snapshot: dict) -> None:
    """Push a snapshot to every fan-out surface. Never raises."""
    try:
        cache.set(snapshot_key(serial), snapshot, timeout=SNAPSHOT_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - a cache outage must not stop ingest
        logger.warning("printing: could not cache state for %s", serial, exc_info=True)

    _publish_redis(serial, snapshot)
    _publish_mqtt(serial, snapshot)


#: Latched so a LocMem cache (tests) or a Redis outage logs once per process
#: rather than once per report — at ~1 report/second that would be a lot of
#: identical lines saying nothing new.
_redis_unavailable = False


def _publish_redis(serial: str, snapshot: dict) -> None:
    global _redis_unavailable

    if _redis_unavailable:
        return
    try:
        from django_redis import get_redis_connection  # noqa: PLC0415
    except ImportError:
        _redis_unavailable = True
        return
    try:
        get_redis_connection("default").publish(
            channel_for(serial), json.dumps(snapshot),
        )
    except Exception:  # noqa: BLE001 - LocMem cache in tests, Redis down in prod
        _redis_unavailable = True
        logger.info(
            "printing: redis pub/sub fan-out unavailable — the cache snapshot "
            "and the status endpoint still work",
        )


# --------------------------------------------------------------------------- #
# Optional MQTT republish
# --------------------------------------------------------------------------- #
_republisher = None
_republisher_failed = False


def _publish_mqtt(serial: str, snapshot: dict) -> None:
    global _republisher, _republisher_failed

    url = getattr(settings, "PRINT_FANOUT_MQTT_URL", "") or ""
    if not url or _republisher_failed:
        return
    if _republisher is None:
        _republisher = _build_republisher(url)
        if _republisher is None:
            _republisher_failed = True
            return
    try:
        _republisher.publish(
            REPUBLISH_TOPIC.format(serial=serial),
            json.dumps(snapshot),
            qos=0,
            retain=True,
        )
    except Exception:  # noqa: BLE001
        logger.warning("printing: MQTT republish failed", exc_info=True)


def _build_republisher(url: str):
    """Connect to the household relay broker. Returns ``None`` on any failure."""
    try:
        import paho.mqtt.client as mqtt  # noqa: PLC0415
        from paho.mqtt.client import CallbackAPIVersion  # noqa: PLC0415
    except ImportError:
        logger.warning("printing: PRINT_FANOUT_MQTT_URL set but paho-mqtt is missing")
        return None

    parsed = urlparse(url)
    try:
        client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id="abby-fanout",
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        if parsed.username:
            client.username_pw_set(parsed.username, parsed.password or "")
        if parsed.scheme in ("mqtts", "ssl"):
            client.tls_set()
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.connect_async(parsed.hostname or "localhost", parsed.port or 1883, 30)
        client.loop_start()
        return client
    except Exception:  # noqa: BLE001
        logger.warning("printing: could not start MQTT republisher", exc_info=True)
        return None


def reset_republisher() -> None:
    """Drop the republisher connection. Used by tests and on shutdown."""
    global _republisher, _republisher_failed, _redis_unavailable
    _redis_unavailable = False
    client, _republisher = _republisher, None
    _republisher_failed = False
    if client is not None:
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:  # noqa: BLE001
            pass
