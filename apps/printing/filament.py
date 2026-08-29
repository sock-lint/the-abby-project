"""What is loaded in the AMS, turned into something a child can pick from.

The MQTT report carries the AMS's own view of every spool: material, colour
as RGBA hex, Bambu's filament id, and (for spools with an RFID tag) how much
is left. This module is the one place that knows that payload's shape — the
same division ``hms.py`` has, where ``report.py`` merely stores the block and
the decoder owns what it means.

Two things this module exists to get right:

**Merging.** The ``ams`` block is nested, so the flat "keep previous when the
key is absent" rule in ``report.py`` cannot reach inside it. Firmware
normally re-sends the whole structure, but partial tray updates have been
reported and we do not want to depend on which is true for a given release —
so :func:`merge_ams` merges by unit id and tray id. A full block merges to
itself, and a partial one keeps what it did not mention. Knowledge only
accumulates here; deciding what is *currently* in a bay is
:func:`describe_trays`' job, on the state of the moment.

**Absence.** Nearly every field here is optional in practice and the honest
answer is often "we don't know":

* ``remain`` is read off an RFID tag, so **third-party spools have no
  percentage at all** and report ``-1``. A picker that assumes a number
  renders "-1% left" on half a household's filament.
* ``tray_color`` is RGB**A**, and alpha ``00`` is how an unread or empty slot
  reads — distinct from ``000000FF``, which is real black filament.
* ``tray_weight`` is the spool's **nominal** weight (1000g), not what is
  left. It is deliberately not surfaced: it would read as a quantity and be
  wrong every time. Consumed filament is not in this payload at all — see
  "Where grams come from" in the subsystem's CLAUDE.md.
* An empty bay still reports a tray object, with the fields blanked.

So every uncertain field is ``None`` rather than a plausible-looking zero,
and callers are expected to render the absence.
"""
from __future__ import annotations

from dataclasses import dataclass

#: AMS units are lettered on the printer itself (A, B, C, D) and slots within
#: a unit are 1-based, so "A1" here is the label the child reads off the
#: hardware. Beyond D we fall back to the raw number rather than inventing a
#: letter — no such machine exists, but a KeyError in the listener would.
_UNIT_LETTERS = "ABCD"

#: ``vt_tray`` is the external spool holder: the filament path that bypasses
#: the AMS entirely, and the only one a printer without an AMS has.
EXTERNAL_SLOT_LABEL = "Ext"


@dataclass(frozen=True)
class FilamentSlot:
    """One loaded spool, as the printer reports it.

    ``hex`` and ``remain_percent`` are ``None`` when the printer did not tell
    us — an unread tag, an empty bay, a third-party spool. Callers must render
    that, not paper over it.
    """

    slot: str
    material: str
    label: str
    hex: str | None
    remain_percent: int | None
    is_external: bool
    filament_id: str = ""

    @property
    def display_name(self) -> str:
        """What to write on the chip: 'PLA Basic' or, failing that, 'PLA'."""
        return self.label or self.material or "Unknown filament"

    def as_dict(self) -> dict:
        return {
            "slot": self.slot,
            "material": self.material,
            "label": self.label,
            "display_name": self.display_name,
            "hex": self.hex,
            "remain_percent": self.remain_percent,
            "is_external": self.is_external,
            "filament_id": self.filament_id,
        }


def _as_str(value) -> str:
    return "" if value is None else str(value).strip()


def normalize_color(raw) -> str | None:
    """``"00AE42FF"`` → ``"#00AE42"``; unknown or unread → ``None``.

    The report gives eight hex digits, RGBA. Alpha is ``FF`` on every real
    spool, and ``00`` marks a bay whose tag has not been read — which is not
    the same as ``000000FF``, black filament, so the alpha check has to come
    before the "is it all zeroes" instinct.
    """
    text = _as_str(raw).lstrip("#").upper()
    if len(text) not in (6, 8) or any(char not in "0123456789ABCDEF" for char in text):
        return None
    if len(text) == 8 and text[6:] == "00":
        return None
    return f"#{text[:6]}"


def _remaining(raw) -> int | None:
    """Percent left, or ``None`` when the spool carries no RFID tag.

    Bambu spools report 0-100. Everything else reports ``-1`` — and some
    firmware has been seen returning other out-of-range values — so the range
    check, not an ``== -1`` test, is what decides.
    """
    try:
        value = int(float(_as_str(raw)))
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 100 else None


def _slot_name(unit_index: int, tray_index: int) -> str:
    if 0 <= unit_index < len(_UNIT_LETTERS):
        return f"{_UNIT_LETTERS[unit_index]}{tray_index + 1}"
    return f"{unit_index + 1}-{tray_index + 1}"


def _build_slot(tray: dict, *, slot: str, is_external: bool) -> FilamentSlot | None:
    """One tray dict → a slot, or ``None`` when the bay is empty.

    An empty bay is not an absent key: the AMS keeps reporting the tray with
    its fields blanked, which is also how a spool *removal* arrives. So
    emptiness is decided here, on the values, every time — never remembered
    from a previous report.
    """
    material = _as_str(tray.get("tray_type"))
    color = normalize_color(tray.get("tray_color"))
    if not material and color is None:
        return None
    return FilamentSlot(
        slot=slot,
        material=material,
        label=_as_str(tray.get("tray_sub_brands")) or material,
        hex=color,
        remain_percent=_remaining(tray.get("remain")),
        is_external=is_external,
        filament_id=_as_str(tray.get("tray_info_idx")),
    )


def merge_ams(previous: dict, incoming: dict) -> dict:
    """Merge an ``ams`` block onto what we already knew, by unit and tray id.

    Safe under either firmware behaviour: a full block merges to itself, and
    a partial one keeps the trays it did not mention rather than blanking the
    AMS. Ids come from the payload (``"0"``..``"3"``) and are compared as
    strings, because their JSON type is not stable across releases.

    The block's ``tray_exist_bits`` would be a second opinion on which bays
    are occupied, but its bit ordering across multiple units is not something
    we have verified against hardware, and :func:`describe_trays` already
    decides emptiness from the tray's own fields. Guessing at a bitfield to
    duplicate an answer we already have is how you get a picker that hides a
    spool that is really there.
    """
    if not isinstance(incoming, dict):
        return previous
    if not isinstance(previous, dict) or not previous:
        return dict(incoming)

    merged = {**previous, **incoming}
    previous_units = previous.get("ams")
    previous_units = previous_units if isinstance(previous_units, list) else []
    old_units = {_as_str(u.get("id")): u
                 for u in previous_units if isinstance(u, dict)}
    new_units = incoming.get("ams")
    if not isinstance(new_units, list):
        # The spread above already copied the junk in; put back what we knew.
        # Bays we can still see are worth more than a malformed report.
        merged["ams"] = previous_units
        return merged

    units = []
    for unit in new_units:
        if not isinstance(unit, dict):
            continue
        old = old_units.pop(_as_str(unit.get("id")), None)
        units.append(_merge_unit(old, unit) if old else unit)
    # A unit the delta didn't mention is still plugged in.
    units.extend(old_units.values())
    units.sort(key=lambda u: _as_str(u.get("id")))
    merged["ams"] = units
    return merged


def _merge_unit(previous: dict, incoming: dict) -> dict:
    merged = {**previous, **incoming}
    previous_trays = previous.get("tray")
    previous_trays = previous_trays if isinstance(previous_trays, list) else []
    old_trays = {_as_str(t.get("id")): t
                 for t in previous_trays if isinstance(t, dict)}
    new_trays = incoming.get("tray")
    if not isinstance(new_trays, list):
        merged["tray"] = previous_trays
        return merged

    trays = []
    for tray in new_trays:
        if not isinstance(tray, dict):
            continue
        old = old_trays.pop(_as_str(tray.get("id")), None)
        trays.append({**old, **tray} if old else tray)
    trays.extend(old_trays.values())
    trays.sort(key=lambda t: _as_str(t.get("id")))
    merged["tray"] = trays
    return merged


def describe_trays(ams: dict | None, vt_tray: dict | None) -> list[FilamentSlot]:
    """Every spool currently loaded, AMS bays first, external holder last.

    Empty bays are dropped. The external holder is included because on a
    printer with no AMS it is the *only* filament path, and even with one it
    is where the odd roll of something special goes.
    """
    slots: list[FilamentSlot] = []

    units = (ams or {}).get("ams")
    if isinstance(units, list):
        for unit_index, unit in enumerate(units):
            if not isinstance(unit, dict):
                continue
            trays = unit.get("tray")
            if not isinstance(trays, list):
                continue
            for tray_index, tray in enumerate(trays):
                if not isinstance(tray, dict):
                    continue
                slot = _build_slot(
                    tray,
                    slot=_slot_name(unit_index, tray_index),
                    is_external=False,
                )
                if slot is not None:
                    slots.append(slot)

    if isinstance(vt_tray, dict):
        external = _build_slot(
            vt_tray, slot=EXTERNAL_SLOT_LABEL, is_external=True,
        )
        if external is not None:
            slots.append(external)

    return slots
