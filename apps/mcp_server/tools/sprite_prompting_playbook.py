"""MCP tool exposing the Gemini sprite-prompting playbook.

This is the in-chat lookup for the failure-mode catalog and prompt-
engineering rules that used to live only in CLAUDE.md's "Sprite
generation from text" gotcha. By turning the catalog into a structured
document a tool can return on demand, Claude Code can pull the rules
when refining a parent's plain-English intent into a Gemini-ready
prompt — without forcing every parent to read the gotcha first.

The motion section is composed from ``MOTION_TEMPLATES`` in
``apps.rpg.sprite_generation`` so adding a new motion slug there
automatically surfaces it here. One-line motion blurbs live in the
``MOTION_GUIDE`` dict below; mismatches fall back to a generic
"no description" line so the playbook never crashes on a slug that
exists in templates but hasn't been described yet.
"""
from __future__ import annotations

from typing import Any

from apps.rpg.sprite_generation import MOTION_TEMPLATES

from ..context import require_parent
from ..errors import safe_tool
from ..schemas import GetSpritePromptingPlaybookIn
from ..server import tool


MOTION_GUIDE: dict[str, str] = {
    "idle": "subtle breathing / micro-motion — most forgiving for Gemini, the safe default",
    "walk": "4-phase quadruped or biped walk cycle, side view",
    "bounce": "squash-and-stretch in place — subject stays stationary, only proportions deform",
    "bubble": "liquid swirl inside a container — potions, cauldrons, bottles",
    "flicker": "flame oscillation — torches, campfires, candles",
    "glow": "pulsing halo — chests, magic items, runes",
    "wobble": "gentle rock side-to-side — eggs about to hatch, jiggling jellies",
    "sway": "plants, flags, banners — slow lateral motion",
}


_FAILURE_MODES = """
## Failure modes (and remedies)

1. **2×2 grid instead of horizontal strip.** Gemini sometimes draws a
   2×2 grid even when the prompt asks for a 1×N horizontal strip. The
   pipeline's layout-aware extractor handles this automatically (finds
   N components, sorts into reading order). No prompt change needed —
   if frames look out of order, re-roll.

2. **Hallucinated scene elements** (pink panels, ground strips, motion
   lines, shadows, props) despite enumerated bans in the system suffix.
   Re-roll with ``overwrite=True``. Persistent hallucination on a
   specific subject is a prompt-engineering bug — strengthen the
   "subject is the ONLY ENTITY in the frame" wording.

3. **"Stack" / "pile" misinterpreted as multiple tiny copies in a row.**
   Replace with: *"ONE single [subject] filling most of the frame, NOT
   multiple tiny [subjects] in a row."* This pattern is the difference
   between "a pile of coins" rendering as 1 fat coin vs 8 mini coins.

4. **Reference image's background bleeds into output as a style cue.**
   The pipeline pre-composites every reference image onto magenta in
   ``_preprocess_reference_image`` to block this. If you still see the
   reference's background tint in the output, the reference probably
   has a colored background AND a transparent layer above — flatten
   the reference first.

5. **Bounce subtle at 4 frames.** The sequential-keyframe rule clashes
   with squash-stretch — the bounce template already includes explicit
   "this rule does NOT apply to this motion" override. If bounce still
   reads flat, increase ``frame_count`` to 6 or 8 for more deformation
   range.

6. **Reference image creature-class over-copy.** Gemini over-copies
   creature class from references. Rules of thumb: (a) for creatures
   Gemini already knows well (fox, cat, dog), OMIT the reference and
   rely on text — a bear-anchored "fox" will draw a bear. (b) for
   items / stylized content, anchor against ``apple-d6446566.png`` (a
   clean pack sprite) for style transfer without shape bias. (c) for
   self-animating an existing sprite, pass that sprite's own URL as
   the reference.
""".strip()


_SUBJECT_RULES = """
## Subject specificity rules

- **One subject, filling most of the frame.** "ONE single X filling
  most of the frame, NOT multiple tiny X in a row." Always.
- **Be specific about the species/class.** "A fox" is better than "a
  small mammal". "A red fox sitting" is better than "a fox".
- **Pose / motion goes after subject.** "A red fox sleeping curled
  up like a comma" reads cleanly. "Sleeping fox" can drift to "a
  bedroom".
- **Color and material on the subject only.** Avoid color words for
  scene elements that aren't there ("a fox on a green meadow" still
  attempts the meadow despite scene-isolation suffix).
- **Scale cue if the subject is small or large by default.** Gemini's
  default scale guess is "fits the frame"; for items like coins or
  potions add "centered, large enough to fill the frame".
""".strip()


_REFERENCE_RULES = """
## Reference image rules

- **Default: no reference.** For common creatures (fox, cat, dog, bear,
  dragon) Gemini's text understanding is strong. Adding a reference
  often *hurts* — the creature-class over-copy bug.
- **Use a reference for style anchoring** when authoring a new pack
  member that should match an existing pack's look. Pass the URL of a
  clean existing sprite (``apple-d6446566.png`` is the canonical neutral
  anchor — generic shape, clean palette).
- **Self-anchor for animating an existing static sprite.** Pass the
  static sprite's own URL as the reference, set ``frame_count`` > 1.
  Character design / palette / scale carry over by construction.
- **Do not pass a reference of a different creature class.** A bear
  reference for "fox" produces a bear that's been told it's a fox.
- **Reference backgrounds are pre-composited onto magenta** by the
  pipeline so the chroma-key step works. You don't need to flatten
  the reference yourself unless it has multiple visible layers.
""".strip()


_TILE_AND_FRAME_RULES = """
## Tile size and frame count

- **128×128**: the default. Hero portraits, mounts, detailed creatures,
  items at full presentation scale. The frontend renders most sprites
  at 32-48px, so the 4× downsample preserves detail without sharpness
  loss. Use this as your starting point.
- **64×64**: when the subject is genuinely simple (single-pixel-feel
  pickups, tiny utility tiles) and 128 feels overkill.
- **32×32**: rare — only for genuinely tiny pickups or single-pixel
  items.
- **frame_count=1**: static. ``fps=0``. The model invariant
  enforces this.
- **frame_count=4**: standard animated cycle. ``fps=8`` is the
  conventional default — visually smooth without chewing storage.
- **frame_count=6 or 8**: when a 4-frame cycle reads flat
  (especially for ``bounce`` or ``walk``). Capped at 8 by
  ``SPRITE_GENERATION_MAX_FRAMES``.
- **Each animated frame is one Gemini call** (~$0.04 at current AI
  Studio pricing). Choose deliberately — an 8-frame strip costs ~8×
  more than a static.
""".strip()


_SIZE_DIAGNOSIS = """
## Diagnosing "subject too small"

The most common reroll trigger. Check in this order:

1. **Check ``pipeline_warnings`` first.** The generation service
   measures the largest output frame's bbox vs ``tile_size`` and
   attaches a warning when occupancy is below 70%. If the response
   carries ``pipeline_warnings``, the pipeline itself flagged the
   issue — proceed to the reroll-with-refinement steps below.

2. **Inspect the raw Gemini output** by re-running with
   ``return_debug_raw=True``. The response includes ``debug.raw_gemini_url``
   and ``debug.post_chroma_key_url`` Ceph URLs. If the raw output
   already shows a small subject in a vast magenta sea, the prompt
   isn't pushing Gemini hard enough on occupancy. If the raw is fine
   but the post-chroma is small, suspect orphan-blob bbox inflation
   (the static path was reordered to prune-before-autocenter, but a
   stubborn case can still appear when Gemini draws several
   significant scene fragments).

3. **Refine via the chat critique loop.** Call
   ``propose_sprite_reroll(slug, critique="too small")`` to get a
   refined prompt with the stronger OCCUPANCY clause attached, then
   pass the proposed inputs to ``reroll_sprite``. Generation
   persists the refined prompt onto the row, so subsequent rerolls
   start from the better baseline.

4. **Consider a bigger tile.** If detail is the problem (not just
   apparent size), bump ``tile_size`` from 64 → 128 — Gemini gets
   4× more pixels to work with and the frontend will downsample to
   its rendering size anyway.

5. **Last resort: drop the reference.** When the sprite is being
   self-anchored on its own prior output, even the reroll path's
   ``tighten_reference=True`` autocrop can't fully escape Gemini's
   tendency to copy the prior framing. Replace via
   ``generate_sprite_sheet`` with ``reference_image_url=None`` to
   start fresh from text only.
""".strip()


def _compose_playbook() -> str:
    """Build the full playbook markdown from the live module constants.

    Reads the motion slug list directly from ``MOTION_TEMPLATES`` so
    adding a new motion in ``sprite_generation.py`` automatically
    surfaces it in the playbook (with a generic blurb if no entry
    exists in ``MOTION_GUIDE`` yet).
    """
    motion_lines = []
    for slug in MOTION_TEMPLATES:
        blurb = MOTION_GUIDE.get(slug, "(no description — extend MOTION_GUIDE)")
        motion_lines.append(f"- **`{slug}`** — {blurb}")
    motion_section = (
        "## Motion templates\n\n"
        "Pick the motion slug that matches the subject's behavior. "
        "Each is a 4-phase cyclic sequence where frame 4 leads back "
        "into frame 1 for seamless looping.\n\n"
        + "\n".join(motion_lines)
    )

    return "\n\n".join([
        "# Sprite prompting playbook",
        "How to ask Gemini for pixel-art sprites that survive the pipeline. "
        "Pull this when refining a plain-English intent into a "
        "`generate_sprite_sheet` call.",
        _FAILURE_MODES,
        motion_section,
        _SUBJECT_RULES,
        _REFERENCE_RULES,
        _TILE_AND_FRAME_RULES,
        _SIZE_DIAGNOSIS,
    ])


@tool()
@safe_tool
def get_sprite_prompting_playbook(params: GetSpritePromptingPlaybookIn) -> dict[str, Any]:
    """Return the failure-mode catalog and prompt-engineering rules.

    Parent-only, read-only. The playbook is a single markdown
    document covering: documented Gemini failure modes and their
    remedies, the motion-template menu, subject specificity rules,
    reference image rules, and tile size / frame count guidance. Use
    this in chat when refining a parent's plain-English description
    into a Gemini-ready ``generate_sprite_sheet`` call, or when
    critiquing a generated sprite against the rules.

    Returns ``{playbook, motions, failure_mode_count}`` — the markdown
    plus structured fields callers can branch on.
    """
    require_parent()
    return {
        "playbook": _compose_playbook(),
        "motions": list(MOTION_TEMPLATES.keys()),
        "failure_mode_count": 6,
    }
