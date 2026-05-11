"""Storage accessor for the sprite bucket.

Kept in its own module so model files stay clean, and so the S3 backend
can be swapped for FileSystemStorage in tests via override_settings
without touching model definitions.
"""
from django.core.files.storage import storages

# Sentinel key used by ``probe_storage`` — never written, only HEAD'd,
# so it doesn't matter that no such object exists. Prefixed with ``_``
# so any future bucket-listing UI groups it visually with internal keys.
_PROBE_KEY = "_sprite-storage-probe"


def sprite_storage():
    """Return the storage backend dedicated to the sprite bucket.

    Resolves to ``STORAGES["sprites"]`` via Django's storage registry.
    Use this in ImageField's ``storage=`` argument so the field picks up
    the current dict at runtime — not at import time — which makes
    ``override_settings(STORAGES={...})`` work in tests.
    """
    return storages["sprites"]


def probe_storage() -> tuple[bool, str]:
    """Quick reachability check for the sprite storage backend.

    Returns ``(ok, message)``. Issues a HEAD-equivalent ``.exists()``
    call against a sentinel key — the storage SDK raises on transport
    failures (Cloudflare 521, DNS, timeout, S3 auth errors, etc.) which
    we trap into ``ok=False`` so callers can fail-fast before burning
    paid resources (most importantly, Gemini API calls inside
    ``generate_sprite_sheet``).

    Cost: one HEAD round-trip against S3 (~50-200ms typical) when the
    backend is S3, or a no-op ``os.path.exists`` for FileSystemStorage
    in dev / tests. Cheap enough for the sprite generation pre-flight,
    too expensive for every Coolify ``/health`` poll — hence the deep-
    mode opt-in on the health endpoint.
    """
    try:
        sprite_storage().exists(_PROBE_KEY)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 — any transport error = unreachable
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"
