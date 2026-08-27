"""Tunables and shared vocabulary for the 3D print request subsystem.

Values that an operator would plausibly want to change per deployment live
in ``config/settings.py`` (``PRINT_*``); the ones here are structural —
changing them changes behaviour, not policy.
"""

# --- Deterministic plate naming ------------------------------------------
# The slug the app mints on approval and asks the parent to save the sliced
# plate as. ``req-0042-dragon`` → ``req-0042-dragon.3mf``.
SLUG_PREFIX = "req"
SLUG_ID_WIDTH = 4
#: Max characters of the (slugified) title appended after the id.
SLUG_TITLE_MAX = 40
#: Extension we tell the parent to save the plate as. Bambu Studio's
#: "Export plate sliced file" writes ``.3mf``; ``.gcode.3mf`` and bare
#: ``.gcode`` are both normalised away by the matcher, so the instruction
#: staying ``.3mf`` costs nothing if Studio decorates the name.
PLATE_EXTENSION = ".3mf"

#: Extensions stripped (repeatedly, longest-first) from ``subtask_name``
#: before matching. Bambu firmware has shipped every one of these shapes
#: across Studio / Handy / SD-card starts, sometimes stacked
#: (``foo.gcode.3mf``).
STRIPPABLE_EXTENSIONS = (
    ".gcode.3mf",
    ".3mf",
    ".gcode",
    ".stl",
)

# --- Budget ---------------------------------------------------------------
#: Floor applied to the proportional debit for a failed print. A print that
#: dies on layer 1 still burned purge + a skirt, so we never debit zero.
FAILED_PRINT_MIN_FRACTION = 0.1

# --- Job tracking ---------------------------------------------------------
#: A job whose printer has said nothing for this long is considered stale
#: and is closed out as ``unknown`` by the reconcile task, so a request
#: never sticks in ``printing`` forever after a power cut.
STALE_JOB_MINUTES = 180

#: How long to wait for a name before opening a job with no ``subtask_name``.
#: The field routinely arrives a beat after ``gcode_state`` flips, so opening
#: immediately would produce a phantom unnamed job on every print. But it can
#: also be legitimately empty forever — ``print.project_file`` defaults it to
#: "" and a job started from the printer's own touchscreen may never set it —
#: and a print nobody can see is worse than one with a blank name, because the
#: parent can still link it by hand from the Forge.
UNNAMED_PRINT_GRACE_SECONDS = 90

#: Progress events are only written when the percentage moves at least this
#: much, so a 4-hour print writes ~20 timeline rows rather than thousands.
PROGRESS_EVENT_STEP_PERCENT = 5
