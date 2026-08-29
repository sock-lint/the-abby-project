"""Turn a stream of Bambu MQTT reports into a coherent printer state.

**Reports are deltas.** This is the single most common source of wrong code
against this protocol, so it gets its own module.

The printer emits ``{"print": {..., "command": "push_status", "msg": 1}}``
roughly once per second, and a ``msg: 1`` payload contains **only the keys
that changed**. A legitimate report can be as small as
``{"print": {"nozzle_temper": 219.7, "layer_num": 10, "command":
"push_status", "msg": 1}}``. The merge rule is therefore
``self.field = data.get("field", self.field)`` — keep the previous value when
a key is absent — and never ``data.get("field", 0)``. A missing
``total_layer_num`` does not mean zero layers; a missing ``subtask_name``
does not mean the print ended.

``msg: 0`` (or absent) marks a **full snapshot**, which is what
``pushall`` returns and what seeds the state.

Nesting is the first trap's sharp edge. ``keep the previous value`` is a
rule about *keys*, and it cannot reach inside a nested block: assigning
``state.ams = block["ams"]`` looks like the same rule but silently blanks
every bay a partial delta didn't mention. ``ams`` is therefore merged by
``filament.merge_ams``, by unit and tray id.

Type instability is the second trap. Bambu mixes quoted strings and raw
numbers inconsistently across firmware versions — ``task_id``,
``gcode_start_time`` and ``mc_print_stage`` arrive as strings while
``layer_num`` and ``mc_percent`` arrive as ints, and which is which has
changed between releases. Everything here goes through :func:`_as_int` /
:func:`_as_str` rather than trusting the JSON type.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .filament import merge_ams

logger = logging.getLogger(__name__)

#: ``gcode_state`` values that mean "not printing". A transition out of this
#: set is a print START; a transition into it is an END. This is the reliable
#: bracket — ``mc_percent`` is NOT, because it can still read 100 from the
#: previous job at the instant a new one begins.
NOT_PRINTING_STATES = frozenset({"IDLE", "FINISH", "FAILED", "OFFLINE", "UNKNOWN", ""})

#: States that mean the print is up but not laying plastic.
PAUSED_STATES = frozenset({"PAUSE"})

#: ``/data/Metadata/plate_3.gcode`` → plate 3. The gcode path is the only
#: place the plate index is exposed.
_PLATE_RE = re.compile(r"plate_(\d+)\.gcode", re.IGNORECASE)

#: ``print_type`` values that are printer-internal routines, not user jobs.
#: Calibration runs should never open a PrintJob.
NON_USER_PRINT_TYPES = frozenset({"system"})


def _as_int(value, default=0) -> int:
    """Coerce a possibly-quoted, possibly-float number to int."""
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return default


def _as_str(value, default="") -> str:
    if value is None:
        return default
    return str(value).strip()


@dataclass
class PrinterState:
    """Accumulated state for one printer, merged across delta reports.

    Held in memory by the listener (and mirrored to Redis for fan-out). It is
    deliberately NOT a Django model: at ~1 message/second a database write per
    report would be ~86,000 writes per printer per day. Rows are written only
    on meaningful transitions.
    """

    serial: str = ""
    seeded: bool = False

    gcode_state: str = ""
    subtask_name: str = ""
    gcode_file: str = ""
    task_id: str = ""
    subtask_id: str = ""
    print_type: str = ""
    layer_num: int = 0
    total_layer_num: int = 0
    mc_percent: int = 0
    remaining_minutes: int = 0
    gcode_start_time: str = ""
    print_error: int = 0
    stg_cur: int = -1
    nozzle_temper: float = 0.0
    bed_temper: float = 0.0
    hms: list = field(default_factory=list)
    #: The AMS's own view of every bay: material, colour, remaining. Nested,
    #: so it is merged by ``filament.merge_ams`` rather than by the flat rule
    #: above — see that module for why the merge has to be by id.
    ams: dict = field(default_factory=dict)
    #: The external spool holder. Present on printers with no AMS at all, and
    #: a sibling of ``ams`` rather than a member of it.
    vt_tray: dict = field(default_factory=dict)
    #: Set once, from the print-start payload only — it is NOT in the pushall
    #: snapshot, so if we weren't listening when the print began it is
    #: unrecoverable for that job.
    ams_mapping: list = field(default_factory=list)
    #: True when the printer itself reported it went offline (cloud only).
    online: bool = True

    # -- derived ------------------------------------------------------------
    @property
    def is_printing(self) -> bool:
        return self.gcode_state not in NOT_PRINTING_STATES

    @property
    def is_paused(self) -> bool:
        return self.gcode_state in PAUSED_STATES

    @property
    def plate_index(self) -> int | None:
        match = _PLATE_RE.search(self.gcode_file or "")
        return int(match.group(1)) if match else None

    @property
    def filaments(self) -> list:
        """Loaded spools, normalised. Empty when the AMS hasn't reported yet."""
        from .filament import describe_trays

        return describe_trays(self.ams, self.vt_tray)

    @property
    def is_user_job(self) -> bool:
        """False for printer-internal routines like calibration gcode."""
        return (self.print_type or "").lower() not in NON_USER_PRINT_TYPES

    def snapshot(self) -> dict:
        """JSON-safe dict for the fan-out cache and the status endpoint."""
        return {
            "serial": self.serial,
            "online": self.online,
            "gcode_state": self.gcode_state,
            "subtask_name": self.subtask_name,
            "gcode_file": self.gcode_file,
            "plate_index": self.plate_index,
            "task_id": self.task_id,
            "print_type": self.print_type,
            "layer_num": self.layer_num,
            "total_layer_num": self.total_layer_num,
            "percent": self.mc_percent,
            "remaining_minutes": self.remaining_minutes,
            "nozzle_temper": self.nozzle_temper,
            "bed_temper": self.bed_temper,
            "print_error": self.print_error,
            "hms": list(self.hms),
            "filaments": [slot.as_dict() for slot in self.filaments],
            "stage": self.stg_cur,
            "seeded": self.seeded,
        }


def is_status_report(payload: dict) -> bool:
    """True only for unsolicited ``push_status`` reports.

    Command acknowledgements (``"command": "project_file"``, ``"pause"``,
    ``"gcode_line"``, …) also carry a ``print`` key. Merging one into state as
    if it were a status report corrupts the state, so ingest is gated here.

    The cloud broker additionally publishes ``{"event": {...}}`` envelopes
    with **no** ``print`` key at all — a parser that reaches for
    ``payload["print"]`` unconditionally raises KeyError on those.
    """
    block = payload.get("print")
    if not isinstance(block, dict):
        return False
    return block.get("command") == "push_status"


def is_full_snapshot(payload: dict) -> bool:
    """True when this payload is a complete state dump (the pushall reply)."""
    block = payload.get("print")
    if not isinstance(block, dict):
        return False
    return _as_int(block.get("msg"), 0) == 0


def connection_event(payload: dict) -> str | None:
    """Return ``"connected"``/``"disconnected"`` for a cloud lifecycle event.

    These arrive on the report topic with no ``print`` key and mean the
    physical printer powered on or off. Local connections never send them.
    """
    event = payload.get("event")
    if not isinstance(event, dict):
        return None
    name = _as_str(event.get("event"))
    if name == "client.connected":
        return "connected"
    if name == "client.disconnected":
        return "disconnected"
    return None


def merge(state: PrinterState, payload: dict) -> PrinterState:
    """Merge one report into ``state``, keeping previous values for absent keys.

    Returns the same object for convenience. Callers should have gated on
    :func:`is_status_report` first.
    """
    block = payload.get("print") or {}
    keep = state  # readability at the call sites below

    state.gcode_state = _as_str(block.get("gcode_state"), keep.gcode_state).upper()
    state.subtask_name = _as_str(block.get("subtask_name"), keep.subtask_name)
    state.gcode_file = _as_str(block.get("gcode_file"), keep.gcode_file)
    state.task_id = _as_str(block.get("task_id"), keep.task_id)
    state.subtask_id = _as_str(block.get("subtask_id"), keep.subtask_id)
    state.print_type = _as_str(block.get("print_type"), keep.print_type)
    state.gcode_start_time = _as_str(block.get("gcode_start_time"), keep.gcode_start_time)

    if "layer_num" in block:
        state.layer_num = _as_int(block["layer_num"], keep.layer_num)
    if "total_layer_num" in block:
        state.total_layer_num = _as_int(block["total_layer_num"], keep.total_layer_num)
    if "mc_percent" in block:
        state.mc_percent = max(0, min(100, _as_int(block["mc_percent"], keep.mc_percent)))
    if "mc_remaining_time" in block:
        # MINUTES, not seconds. Reading this as seconds is a classic 60x bug.
        state.remaining_minutes = _as_int(
            block["mc_remaining_time"], keep.remaining_minutes,
        )
    if "print_error" in block:
        state.print_error = _as_int(block["print_error"], 0)
    if "stg_cur" in block:
        # X1 reports -1 for idle, P1 reports 255, and a freshly-booted printer
        # can report 0 ("printing") while sitting idle. We only store it; the
        # job state machine trusts gcode_state.
        state.stg_cur = _as_int(block["stg_cur"], keep.stg_cur)
    if "nozzle_temper" in block:
        state.nozzle_temper = _as_float(block["nozzle_temper"], keep.nozzle_temper)
    if "bed_temper" in block:
        state.bed_temper = _as_float(block["bed_temper"], keep.bed_temper)
    if "hms" in block and isinstance(block["hms"], list):
        # hms IS reliably re-sent in deltas, including as [] when alerts
        # clear — so an empty list here genuinely means "all clear", unlike
        # most absent-key cases.
        state.hms = block["hms"]
    if "ams" in block and isinstance(block["ams"], dict):
        # Nested, so the flat keep-previous rule can't reach inside it: a
        # partial ``ams`` delta merged by assignment would blank the bays it
        # didn't mention. merge_ams merges by unit and tray id instead.
        state.ams = merge_ams(state.ams, block["ams"])
    if "vt_tray" in block and isinstance(block["vt_tray"], dict):
        # Flat, one tray, so plain assignment is the right merge here.
        state.vt_tray = {**state.vt_tray, **block["vt_tray"]}
    if "ams_mapping" in block and isinstance(block["ams_mapping"], list):
        state.ams_mapping = block["ams_mapping"]

    if is_full_snapshot(payload):
        state.seeded = True
    return state


def _as_float(value, default=0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default
