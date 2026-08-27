"""Decode Bambu HMS alerts and print errors into readable failure reasons.

This is the module that makes a print's timeline say *"The AMS slot ran out
of filament (unit A, slot 3)"* instead of *"0700_2200_0002_0001"*.

Two namespaces, two encodings — do not mix them:

``hms``  is an array of ``{"attr": int, "code": int}``. The canonical string
         is four hex groups: ``attr>>16 _ attr&0xFFFF _ code>>16 _ code&0xFFFF``.
         Group 3 is the severity (1 fatal / 2 serious / 3 common / 4 info) and
         the high byte of group 1 is the module.

``print_error`` is a single 32-bit int rendered as **two** groups
         (``0300_400C``) against a completely different table. Its module byte
         is the same space; its severity is not — treat any non-zero value as
         "the print stopped". It also **latches for only a couple of seconds**,
         so the listener records it on the edge rather than polling for it.

When a code isn't in our table we still return something useful: severity and
module decode from the bits alone, and most misses are just a different AMS
unit or slot of a code we do have, so we normalise and retry before giving up.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .hms_codes import (
    AMS_MODULES,
    BLOCKING_SEVERITIES,
    CANCEL_PRINT_ERROR,
    EXTERNAL_SPOOL_UNITS,
    HMS_MESSAGES,
    MODEL_WIKI_SERIES,
    MODULE_LABELS,
    PRINT_ERROR_MESSAGES,
    SEVERITY_LABELS,
    SLOTTED_G2_FAMILIES,
    WIKI_INDEX_URL,
)

UNKNOWN = "unknown"

#: AMS unit index → the letter Bambu Studio shows on the unit.
_UNIT_LETTERS = "ABCDEFGH"


@dataclass
class DecodedAlert:
    """One decoded printer alert, ready to be written to a timeline row."""

    code: str
    message: str
    severity: str = UNKNOWN
    module: str = UNKNOWN
    #: True when this alert is the kind that stops or holds a print.
    blocking: bool = False
    #: True only for the specific "user cancelled" print_error.
    cancelled: bool = False
    wiki_url: str = WIKI_INDEX_URL
    #: Raw ints, kept so a future table extension can be back-filled offline.
    raw: dict = field(default_factory=dict)

    def as_context(self) -> dict:
        """The JSON blob stored on ``PrintJobEvent.context``."""
        return {
            "code": self.code,
            "severity": self.severity,
            "module": self.module,
            "blocking": self.blocking,
            "wiki_url": self.wiki_url,
            **self.raw,
        }


# --------------------------------------------------------------------------- #
# Bit-level helpers
# --------------------------------------------------------------------------- #
def format_hms_code(attr: int, code: int) -> str:
    """Render ``(attr, code)`` as the canonical four-group HMS string."""
    return (
        f"{(attr >> 16) & 0xFFFF:04X}_{attr & 0xFFFF:04X}_"
        f"{(code >> 16) & 0xFFFF:04X}_{code & 0xFFFF:04X}"
    )


def format_print_error(value: int) -> str:
    """Render a ``print_error`` int as its two-group string, e.g. ``0300_400C``.

    Uses an explicit 8-wide zero pad rather than the ``'0' + hex`` trick some
    integrations use — that only works while the high nibble happens to be
    zero, which is not guaranteed by anything.
    """
    return f"{value & 0xFFFFFFFF:08X}"[:4] + "_" + f"{value & 0xFFFFFFFF:08X}"[4:]


def severity_of(code: int) -> str:
    """Severity label from group 3. ``unknown`` for 0 or an unmapped value."""
    return SEVERITY_LABELS.get((code >> 16) & 0xFFFF, UNKNOWN)


def module_of(attr: int) -> str:
    """Module label from the high byte of group 1. ``unknown`` if unmapped."""
    return MODULE_LABELS.get((attr >> 24) & 0xFF, UNKNOWN)


def wiki_url_for(code_string: str, model_name: str = "") -> str:
    """Best available wiki link for a code.

    Returns the model-specific troubleshooting page when we recognise the
    printer model, and the code index otherwise. The URL uses underscores
    even though the page renders the code with dashes.
    """
    series = MODEL_WIKI_SERIES.get((model_name or "").strip().upper())
    if not series:
        return WIKI_INDEX_URL
    return f"https://wiki.bambulab.com/en/{series}/troubleshooting/hmscode/{code_string}"


# --------------------------------------------------------------------------- #
# AMS unit/slot normalisation
# --------------------------------------------------------------------------- #
def _split(code_string: str) -> tuple[int, int, int, int]:
    g1, g2, g3, g4 = code_string.split("_")
    return int(g1, 16), int(g2, 16), int(g3, 16), int(g4, 16)


def _join(g1: int, g2: int, g3: int, g4: int) -> str:
    return f"{g1:04X}_{g2:04X}_{g3:04X}_{g4:04X}"


def ams_location(g1: int, g2: int) -> str:
    """Human suffix describing which AMS unit and slot a code came from.

    Returns ``""`` when the code isn't AMS-shaped, so callers can append it
    unconditionally.
    """
    module_byte = (g1 >> 8) & 0xFF
    if module_byte not in AMS_MODULES:
        return ""
    unit_byte = g1 & 0xFF
    if unit_byte in EXTERNAL_SPOOL_UNITS:
        return " (external spool)"

    parts = []
    if unit_byte < len(_UNIT_LETTERS):
        parts.append(f"unit {_UNIT_LETTERS[unit_byte]}")
    if (g2 & 0xF000) in SLOTTED_G2_FAMILIES:
        parts.append(f"slot {((g2 >> 8) & 0x0F) + 1}")
    return f" ({', '.join(parts)})" if parts else ""


def _lookup_candidates(code_string: str) -> list[str]:
    """Exact code first, then its unit- and slot-normalised forms.

    Most table misses are the same fault on a different AMS unit or slot —
    Bambu publishes each permutation as its own code, which is how ~250 real
    AMS faults become ~2000 code strings. Collapsing the unit byte and the
    slot nibble lets one vendored entry answer for all of them.
    """
    try:
        g1, g2, g3, g4 = _split(code_string)
    except (ValueError, AttributeError):
        return [code_string]

    candidates = [code_string]
    module_byte = (g1 >> 8) & 0xFF
    if module_byte not in AMS_MODULES:
        return candidates

    unit_byte = g1 & 0xFF
    unit_normalised = g1 & 0xFF00 if unit_byte not in EXTERNAL_SPOOL_UNITS else g1
    slot_normalised = g2 & 0xF000 if (g2 & 0xF000) in SLOTTED_G2_FAMILIES else g2

    for candidate_g1, candidate_g2 in (
        (unit_normalised, g2),
        (g1, slot_normalised),
        (unit_normalised, slot_normalised),
    ):
        candidate = _join(candidate_g1, candidate_g2, g3, g4)
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def describe(attr: int, code: int, *, model_name: str = "") -> DecodedAlert:
    """Decode one ``hms`` array entry."""
    code_string = format_hms_code(attr, code)
    severity = severity_of(code)
    module = module_of(attr)
    g1, g2 = (attr >> 16) & 0xFFFF, attr & 0xFFFF
    location = ams_location(g1, g2)

    message = ""
    for candidate in _lookup_candidates(code_string):
        if candidate in HMS_MESSAGES:
            message = HMS_MESSAGES[candidate] + location
            break

    if not message:
        # Never render a bare "unknown error" — severity alone tells a parent
        # whether to walk over to the printer.
        module_part = module if module != UNKNOWN else "The printer"
        message = (
            f"{module_part} reported an alert we don't have text for "
            f"({code_string}, {severity})."
        )

    return DecodedAlert(
        code=code_string,
        message=message,
        severity=severity,
        module=module,
        blocking=severity in BLOCKING_SEVERITIES,
        wiki_url=wiki_url_for(code_string, model_name),
        raw={"attr": attr, "raw_code": code},
    )


def describe_all(hms_array, *, model_name: str = "") -> list[DecodedAlert]:
    """Decode a whole ``hms`` array, skipping malformed entries.

    Firmware occasionally emits an entry with a missing key or a string where
    an int belongs; one bad row must not lose the rest of the array, and must
    never take down the listener.
    """
    decoded: list[DecodedAlert] = []
    for entry in hms_array or []:
        if not isinstance(entry, dict):
            continue
        try:
            attr = int(entry["attr"])
            code = int(entry["code"])
        except (KeyError, TypeError, ValueError):
            continue
        decoded.append(describe(attr, code, model_name=model_name))
    return decoded


def describe_print_error(value, *, model_name: str = "") -> DecodedAlert | None:
    """Decode a ``print_error`` int. Returns ``None`` for 0 / unparseable.

    ``print_error`` is usually the more valuable of the two fields for a
    failure feed: the ``hms`` array carries the underlying symptom, while
    ``print_error`` is the one that says the job actually died.
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    if not value:
        return None

    code_string = format_print_error(value)
    cancelled = value == CANCEL_PRINT_ERROR
    message = PRINT_ERROR_MESSAGES.get(code_string)
    module = module_of(value)
    if not message:
        module_part = module if module != UNKNOWN else "The printer"
        message = f"{module_part} stopped the print (error {code_string})."

    return DecodedAlert(
        code=code_string,
        message=message,
        # device_error does not encode a severity ladder — any non-zero value
        # means the print stopped, so we say so rather than inventing a tier.
        severity="" if cancelled else "fatal",
        module=module,
        blocking=not cancelled,
        cancelled=cancelled,
        wiki_url=WIKI_INDEX_URL,
        raw={"print_error": value},
    )


def summarize_failure(alerts, print_error_alert=None) -> DecodedAlert | None:
    """Pick the single alert that best explains why a print stopped.

    ``print_error`` wins when present — it's the fatal outcome, where the
    ``hms`` entries are usually the symptoms leading up to it. Otherwise take
    the most severe blocking HMS alert, preferring the first one seen at that
    severity (firmware appends, so earlier entries are the earlier causes).
    """
    if print_error_alert is not None:
        return print_error_alert
    ranked = [a for a in alerts or [] if a.blocking]
    if not ranked:
        return None
    order = {"fatal": 0, "serious": 1, "common": 2, "info": 3, UNKNOWN: 4}
    return min(ranked, key=lambda a: order.get(a.severity, 5))
