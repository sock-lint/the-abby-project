"""Curated Bambu HMS + print_error message tables.

These are **data**, deliberately separated from the decoding logic in
``hms.py`` so the table can be extended (or regenerated) without touching
code — and so a diff that adds 40 codes reads as 40 added lines.

Provenance: Bambu's own error-text service at
``https://e.bambulab.com/query.php?lang=en&d=<serial-prefix>`` publishes the
full table (~5000 HMS entries + ~950 device_error entries). We deliberately
do **not** call it at runtime — that would put a third-party HTTP request on
the path of rendering a print's timeline. Instead we vendor the codes that
actually stop or interrupt a home print, in plain language a parent can act
on, and fall back to a severity + module summary plus a wiki link for
anything else (see ``hms.describe``).

The messages are rewritten, not copied: Bambu's strings are terse and
machine-flavoured ("Filament ran out; please load a new filament"). This is
a kid-facing timeline, so each one says what happened and what to do.
"""

# --------------------------------------------------------------------------- #
# Severity — group 3 of the canonical code (``code >> 16``).
# Severity 4 ("info") is defined by the protocol but has never been observed
# in the published table; keep it mapped so a future firmware doesn't render
# as "unknown".
# --------------------------------------------------------------------------- #
SEVERITY_LABELS = {
    1: "fatal",
    2: "serious",
    3: "common",
    4: "info",
}

#: Severities at which we treat an alert as "this stopped the print".
BLOCKING_SEVERITIES = ("fatal", "serious")

# --------------------------------------------------------------------------- #
# Module — high byte of group 1 (``attr >> 24``). Shared between the HMS and
# device_error namespaces, which is why print_error decoding reuses it.
# --------------------------------------------------------------------------- #
MODULE_LABELS = {
    0x03: "Motion controller",
    0x05: "Main board",
    0x07: "AMS",
    0x08: "Toolhead",
    0x0C: "Micro Lidar camera",
    0x10: "Slicer",
    0x12: "AMS Lite",
    0x18: "AMS HT",
}

#: Modules whose codes are per-unit and per-slot, so an unmatched code can be
#: normalised back to its unit-A/slot-1 form before giving up.
AMS_MODULES = (0x07, 0x12, 0x18)

#: Low bytes of group 1 that mean "external spool holder", not an AMS unit
#: index — must not be normalised away.
EXTERNAL_SPOOL_UNITS = (0xFE, 0xFF)

#: Group-2 families that encode a slot in their second byte (stride 0x0100).
SLOTTED_G2_FAMILIES = (0x1000, 0x2000, 0x4000, 0x6000, 0x7000)


# --------------------------------------------------------------------------- #
# HMS codes, canonical ``GGGG_GGGG_GGGG_GGGG`` form.
# --------------------------------------------------------------------------- #
HMS_MESSAGES: dict[str, str] = {
    # --- AMS: filament supply ---------------------------------------------
    "0700_2000_0002_0001": "The AMS slot ran out of filament. Load a new spool and resume.",
    "0700_2000_0002_0002": "The AMS slot is empty. Put a spool in it before printing.",
    "0700_2000_0002_0003": "The filament snapped inside the AMS. Open the AMS and pull the broken piece out.",
    "0700_2000_0002_0004": "The filament snapped inside the print head. The stub has to be pulled out of the toolhead.",
    "0700_2000_0002_0005": "The AMS slot ran out and the old filament didn't flush out cleanly. Check for filament stuck in the print head.",
    "0700_2000_0002_0009": "The printer couldn't push the filament through. The nozzle is probably clogged, or the filament is too soft.",
    "0700_2000_0002_000A": "The AMS filament buffer is jammed. Check the buffer box and the feed tube for a snag.",
    "0700_2000_0002_0016": "The AMS feed wheel is slipping. Pull the filament out, snip off the chewed-up section, and reload it.",
    "0700_7000_0002_0001": "The printer couldn't pull filament back out of the extruder. It's likely clogged, or a piece snapped off inside.",
    "0700_7000_0002_0003": "The printer couldn't push filament through. The extruder or nozzle is clogged.",
    "0700_7000_0002_0006": "Timed out flushing the old colour out. Filament is stuck, or the nozzle is clogged.",
    "0700_7000_0002_0007": "The AMS ran out of filament. Put a new spool in the same slot and resume.",
    "0700_1000_0002_0002": "The AMS feed motor is straining. The filament is tangled on the spool or snagged somewhere.",
    "0700_0100_0002_0002": "The AMS feed motor is straining. The filament is tangled on the spool or snagged somewhere.",
    "0700_4000_0002_0004": "The AMS filament buffer is reading wrong. The spring is stuck, or the filament is tangled.",
    "0700_5100_0003_0001": "The AMS is switched off for this print. Feed filament from the spool holder on the back instead.",
    "07FF_2000_0002_0001": "The spool on the external holder ran out. Load new filament.",
    "07FF_6000_0002_0001": "The external spool is tangled or jammed. Free the filament and resume.",
    "1200_2000_0002_0001": "The AMS Lite slot ran out of filament. Load a new spool.",
    "1800_2000_0002_0001": "The AMS HT slot ran out of filament. Load a new spool.",

    # --- Extruder / nozzle -------------------------------------------------
    "0300_1A00_0002_0002": "The nozzle is clogged.",
    "0300_1A00_0002_0001": "The nozzle is caked in filament, or the build plate is sitting crooked.",
    "0300_0900_0002_0001": "The extruder motor is straining. The nozzle is likely clogged, or filament is jammed in the print head.",
    "0300_0900_0002_0003": "The extruder isn't pushing filament properly. It's clogged, or the filament is slipping.",
    "0300_1200_0002_0001": "The front cover of the print head fell off. Clip it back on.",

    # --- Temperature -------------------------------------------------------
    "0300_0100_0001_0001": "Heated bed temperature fault — the bed heater may be short-circuited. Stop and have the printer checked.",
    "0300_0100_0001_0003": "The heated bed is overheating. The printer stopped itself for safety.",
    "0300_0200_0001_0001": "Nozzle temperature fault — the nozzle heater may be short-circuited. Stop and have the printer checked.",
    "0300_0200_0001_0003": "The nozzle is overheating. The printer stopped itself for safety.",
    "0300_0200_0001_0008": "The nozzle can't get up to temperature. The silicone sock around it may be fitted wrong.",
    "0300_A100_0001_0001": "The inside of the printer is too hot. Open the top cover and front door to let it cool down.",
    "0300_9000_0001_0002": "Chamber heating failed. The cover or door may be open, the room may be too cold, or a vent is blocked.",
    "0500_0400_0002_0007": "The bed is hotter than this filament likes and may clog the nozzle. Open the front door or turn the bed temperature down.",

    # --- Fans --------------------------------------------------------------
    "0300_0300_0001_0001": "The hot-end cooling fan has stopped or is very slow. It may be jammed or unplugged — printing without it can wreck the print head.",
    "0300_0400_0002_0001": "The part cooling fan has stopped or is very slow. Prints will droop and sag until it's fixed.",
    "0300_3100_0001_0001": "The part cooling fan has stopped or is very slow. It may be jammed or unplugged.",

    # --- Bed / motion ------------------------------------------------------
    "0300_0D00_0001_0003": "The build plate isn't seated properly. Reseat it flat on the bed and try again.",
    "0300_0D00_0001_000B": "The Z axis motor is stuck. Check for something jammed in the Z sliders or the belt wheels.",
    "0300_0D00_0001_000C": "Bed levelling readings look wrong. Clear any debris off the bed and the Z slider, then retry.",
    "0300_0D00_0002_0001": "Bed levelling had trouble — there may be a bump on the plate, or the nozzle tip is dirty. Wipe the nozzle and retry.",
    "0300_2D00_0001_0006": "Bed levelling failed — debris on the plate, or the bed is tilted. Clear it before printing.",
    "0300_2000_0001_0001": "The X axis couldn't find its home position. Something is blocking the print head.",
    "0300_1000_0002_0001": "The X axis belt reads loose. The printer needs a belt tension check and recalibration.",

    # --- Camera / lidar ----------------------------------------------------
    "0C00_0100_0001_0001": "The Micro Lidar sensor is offline. Check its cable connection.",
    "0C00_0100_0001_0004": "The Micro Lidar lens is dirty. Wipe it clean.",
    "0C00_0100_0002_0008": "The camera can't get a picture, so spaghetti and waste-chute checks are switched off for now.",
    "0C00_0300_0002_0002": "First layer inspection stopped early because the lidar data was bad. Check the first layer yourself.",
    "0C00_0300_0002_000E": "The camera thinks the nozzle is covered in jammed or melted filament. Clean the nozzle.",
    "0C00_0300_0002_0010": "The camera spotted something left on the bed. Clear the plate before printing.",
    "0C00_0300_0003_0006": "Purged filament has piled up in the waste chute. Clear it out.",
    "0C00_0300_0003_0007": "The camera thinks the first layer looks wrong. Check it and decide whether to stop the print.",
    "0C00_0300_0003_0008": "Spaghetti detected — the print has probably come loose from the plate. Check it and stop the job if it's a mess.",
    "0C00_0300_0003_0010": "The printer looks like it's moving but not laying any plastic down. Probably out of filament or clogged.",

    # --- Enclosure ---------------------------------------------------------
    "0300_9600_0001_0001": "The front door is open, so the print is paused. Close it and resume.",
    "0300_9600_0003_0001": "The front door is open.",
    "0300_9700_0003_0001": "The top cover is open.",

    # --- Communication -----------------------------------------------------
    "0500_0300_0001_0002": "The print head isn't responding. Restart the printer.",
    "0500_0300_0001_0003": "The AMS isn't responding. Restart the printer.",
    "0500_0400_0001_0049": "The printer lost communication with the AMS. Reseat the AMS cable, then restart the printer while it's idle.",
    "0300_A800_0001_0001": "AMS power problem — possibly a damaged AMS, a short in its port, or too many AMS units chained together.",
}


# --------------------------------------------------------------------------- #
# print_error — a SEPARATE namespace with its own table and its own encoding.
#
# Rendered as two hex groups (``0300_400C``), not four. It is NOT a truncated
# HMS code: Bambu ships ``device_hms`` (16 hex digits) and ``device_error``
# (8 hex digits) as sibling dictionaries and they barely overlap. Never look a
# print_error up in HMS_MESSAGES.
#
# Severity is NOT encoded here the way it is in HMS — the corresponding byte is
# only ever 0x40/0x80/0xC0, a sub-code space rather than a severity ladder. So
# every non-zero print_error means "the print stopped", and we carry no
# severity for it. The module byte IS shared, so module decoding is reused.
# --------------------------------------------------------------------------- #
PRINT_ERROR_MESSAGES: dict[str, str] = {
    "0300_4002": "Bed levelling failed, so the printer stopped the job.",
    "0300_4006": "The nozzle is clogged, so the printer stopped the job.",
    "0300_4008": "The AMS couldn't change filament, so the printer stopped the job.",
    "0300_400C": "The print was cancelled.",
    "0300_400D": "The printer couldn't resume after losing power.",
    "0300_404B": "The print was stopped because the front door or top cover was opened.",
    "0300_4057": "The Z axis lost steps, so the printer stopped the job.",
    "0700_8006": "Filament couldn't be fed into the extruder — it's tangled or the spool is stuck.",
}

#: ``0x0300400C`` is what the printer emits on a NORMAL user cancel. Without
#: this special case every cancelled print reads as a crash in the timeline.
CANCEL_PRINT_ERROR = 0x0300400C


# --------------------------------------------------------------------------- #
# Wiki links.
#
# There is no model-agnostic per-code URL: real pages live at
# ``/en/<series>/troubleshooting/hmscode/<CODE>`` and the same code sits under
# different series for different printers. We map the models we know about and
# fall back to the index, which lists every code with per-model links — the
# same fallback ha-bambulab uses.
# --------------------------------------------------------------------------- #
WIKI_INDEX_URL = "https://wiki.bambulab.com/en/hms/home"

MODEL_WIKI_SERIES = {
    "X1": "x1",
    "X1C": "x1",
    "X1E": "x1",
    "X1 CARBON": "x1",
    "P1P": "x1",   # P1 series codes are documented under the x1 tree.
    "P1S": "x1",
    "P2S": "p2s",
    "A1": "a1",
    "A1 MINI": "a1-mini",
    "H2": "h2",
    "H2D": "h2d",
    "H2S": "h2s",
    "H2C": "h2c",
    "X2D": "x2d",
}
