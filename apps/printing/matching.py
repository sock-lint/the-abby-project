"""Deterministic request ↔ job matching.

The whole point of this module: **nobody should ever hand-link a print.**

At approval we mint a slug that embeds the request's primary key
(``req-0042-dragon``) and tell the parent to save the sliced plate as
``req-0042-dragon.3mf``. Bambu firmware then reports that filename back to
us as ``print.subtask_name``, and matching is an equality check on a
normalised string — no fuzzy scoring, no heuristics, no "closest title".

The manual link endpoint exists only for plates started from Handy in a
hurry, where nobody renamed anything.

Normalisation exists because firmware is not consistent about what it puts
in ``subtask_name``. Across Studio / Handy / SD-card starts we have to cope
with: the bare name, the name with ``.3mf`` / ``.gcode`` / ``.gcode.3mf``,
a leading directory, a ``_plate_1`` suffix Studio adds when exporting a
single plate out of a multi-plate project, and a ``(1)`` copy suffix from
the file picker. All of those must land on the same key.
"""
from __future__ import annotations

import re

from django.utils.text import slugify

from .constants import (
    PLATE_EXTENSION,
    SLUG_ID_WIDTH,
    SLUG_PREFIX,
    SLUG_TITLE_MAX,
    STRIPPABLE_EXTENSIONS,
)

#: ``req-0042-...`` — the id is the authoritative half of the slug.
_SLUG_ID_RE = re.compile(rf"^{re.escape(SLUG_PREFIX)}-0*(\d+)(?:-|$)")

#: Studio's single-plate export suffix, in every separator flavour we've seen.
_PLATE_SUFFIX_RE = re.compile(r"[-_ ]*plate[-_ ]*\d+$")

#: A file-picker copy suffix: ``name(1)`` / ``name (2)``.
_COPY_SUFFIX_RE = re.compile(r"\s*\(\d+\)$")


def mint_slug(request_id: int, title: str) -> str:
    """Return the canonical slug for a request, e.g. ``req-0042-dragon``.

    The id is zero-padded to :data:`SLUG_ID_WIDTH` for readability but the
    matcher tolerates any width — ``req-42-dragon`` resolves to the same
    request. Titles that slugify to nothing (emoji-only, CJK) fall back to
    ``print`` so the slug is always ``req-<id>-<something>``; the id half is
    what actually identifies it.
    """
    title_part = slugify(title or "")[:SLUG_TITLE_MAX].strip("-")
    if not title_part:
        title_part = "print"
    return f"{SLUG_PREFIX}-{request_id:0{SLUG_ID_WIDTH}d}-{title_part}"


def plate_filename_for(slug: str) -> str:
    """Return the filename we instruct the parent to save the plate as."""
    return f"{slug}{PLATE_EXTENSION}"


def _strip_extensions(name: str) -> str:
    """Strip every known model/gcode extension, repeatedly and longest-first.

    ``foo.gcode.3mf`` → ``foo`` in one pass (``.gcode.3mf`` is listed first),
    but the loop also catches stacked or repeated extensions firmware might
    invent later.
    """
    lowered = name
    changed = True
    while changed:
        changed = False
        for ext in STRIPPABLE_EXTENSIONS:
            if lowered.lower().endswith(ext):
                lowered = lowered[: -len(ext)]
                changed = True
                break
    return lowered


def normalize_subtask_name(raw: str) -> str:
    """Normalise a reported ``subtask_name`` into a matchable key.

    Lossy and deliberately so: two names that differ only in separators,
    case, extension, plate suffix or copy suffix must produce the same key.
    Returns ``""`` for empty/whitespace input — callers treat that as
    "no identity yet", not as a match against a request with an empty slug.
    """
    if not raw:
        return ""
    name = str(raw).strip()
    if not name:
        return ""

    # Drop any directory component — gcode_file is a path, and subtask_name
    # occasionally picks one up on SD-card starts.
    name = name.replace("\\", "/").rsplit("/", 1)[-1]

    name = _strip_extensions(name)
    name = _COPY_SUFFIX_RE.sub("", name)
    name = name.strip().lower()
    name = _PLATE_SUFFIX_RE.sub("", name)

    # Unify separators, then keep only slug-safe characters.
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"[^a-z0-9-]+", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name


def request_id_from_name(normalized: str) -> int | None:
    """Extract the request id from a normalised name, if it carries one.

    ``req-0042-dragon`` → ``42``. This is the escape hatch for the case
    where the parent renamed the descriptive half of the plate but kept the
    ``req-NNNN`` prefix — still an exact identity match, not a guess.
    """
    match = _SLUG_ID_RE.match(normalized or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:  # pragma: no cover - regex guarantees digits
        return None


def find_request(normalized: str, *, family=None):
    """Resolve a normalised subtask name to a bindable ``PrintRequest``.

    Two exact strategies, in order:

    1. ``slug == normalized`` — the happy path, hit by every plate saved
       under the minted filename.
    2. The ``req-NNNN`` id prefix — covers a parent who kept the prefix but
       retyped the descriptive tail.

    Returns ``None`` when neither hits, or when the resolved request isn't in
    a bindable status (a rejected or cancelled request must never absorb a
    print). ``family`` scopes the lookup so a printer in one household can
    never bind to another household's request — the same cross-family rule
    every other lookup in this codebase follows.
    """
    from .models import PrintRequest

    if not normalized:
        return None

    qs = PrintRequest.objects.filter(status__in=PrintRequest.BINDABLE_STATUSES)
    if family is not None:
        qs = qs.filter(user__family=family)

    found = qs.filter(slug=normalized).first()
    if found is not None:
        return found

    request_id = request_id_from_name(normalized)
    if request_id is None:
        return None
    return qs.filter(pk=request_id).first()
