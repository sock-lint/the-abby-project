"""Fernet encryption for printer credentials at rest.

Mirrors ``apps/google_integration/services.py`` — same HKDF-from-SECRET_KEY
derivation, different ``salt``/``info`` labels so the two derived keys are
independent. There is no legacy-format fallback here because this app is
new: every stored blob has always been Fernet.

Rotating ``SECRET_KEY`` invalidates stored printer credentials — the parent
re-enters the access code in ``/manage``. Same operational property as the
Google integration, and it's why ``decrypt_secrets`` returns ``{}`` rather
than raising: a listener that can't decrypt should log and skip that
printer, not crash the supervisor loop for every other printer.
"""
from __future__ import annotations

import base64
import json
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    """Return a Fernet instance keyed off ``SECRET_KEY`` via HKDF."""
    key_bytes = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"abby:printing:fernet:v1",
        info=b"PrinterProfile.encrypted_secret",
    ).derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_secrets(values: dict) -> bytes:
    """Serialize + encrypt a credential dict."""
    payload = json.dumps(values, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(payload)


def decrypt_secrets(blob) -> dict:
    """Decrypt a credential blob, returning ``{}`` on any failure.

    ``blob`` may be ``bytes``, ``memoryview`` (what psycopg2 hands back for
    a BinaryField), or empty/None.
    """
    if not blob:
        return {}
    try:
        raw = _fernet().decrypt(bytes(blob))
    except (InvalidToken, TypeError, ValueError):
        logger.warning(
            "printing: could not decrypt printer credentials — has SECRET_KEY rotated?",
        )
        return {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("printing: printer credential blob is not valid JSON")
        return {}
    return decoded if isinstance(decoded, dict) else {}
