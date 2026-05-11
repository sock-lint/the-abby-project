"""MCP tools for runtime sprite authoring.

Replaces the build-time scripts/sprite_manifest.yaml flow with four
focused tools: register_sprite (single), register_sprite_batch (sheet →
many tiles), list_sprites, delete_sprite. All write through the
SpriteAsset model and the dedicated ``abby-sprites`` Ceph bucket.

The legacy ``register_sprite_assets`` tool in sprite_assets.py stays
wired for local-dev source-tree authoring until the Phase 3 cleanup
PR removes it.
"""
from __future__ import annotations

import base64
import mimetypes
from typing import Any

from apps.rpg import sprite_authoring as svc
from apps.rpg import sprite_generation as gen_svc
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import SpriteAuthoringError
from apps.rpg.sprite_generation import SpriteGenerationError

# Cap on the inline-image payload returned by ``get_sprite(include_image=True)``.
# Measured against the worst-case raw decoded size
# (frame_count × width × height × 4 RGBA bytes), not the PNG file size on disk
# — that way the LLM context-window estimate is an upper bound rather than a
# guess. Pixel-art sprites in this codebase top out around 24KB raw for a
# 4-frame 64×64 strip, so the cap leaves plenty of room while refusing to
# return e.g. a 1024×1024 16-frame sheet (~64 MB raw) inline.
_SPRITE_INLINE_MAX_BYTES = 200_000

from ..context import require_parent, require_staff_parent, get_current_user
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    DeleteSpriteIn,
    GenerateSpriteSheetIn,
    GetSpriteIn,
    ListSpritesIn,
    ProposeSpriteRerollIn,
    RegisterSpriteBatchIn,
    RegisterSpriteIn,
    RerollSpriteIn,
    UpdateSpriteMetadataIn,
)
from ..server import tool


def _wrap_svc_call(fn, **kwargs) -> dict[str, Any]:
    try:
        return fn(**kwargs)
    except (SpriteAuthoringError, SpriteGenerationError) as exc:
        raise MCPValidationError(str(exc))


@tool()
@safe_tool
def register_sprite(params: RegisterSpriteIn) -> dict[str, Any]:
    """Register one sprite (static or animation strip) from bytes or a URL.

    Staff-parent only (Audit C5 — sprite catalog is global content visible
    to every family). Returns the sprite's URL + dimensions + animation
    metadata so the LLM can confirm the upload and reference the slug in
    subsequent content YAML.
    """
    require_staff_parent()
    return _wrap_svc_call(
        svc.register_sprite,
        slug=params.slug,
        image_b64=params.image_b64,
        image_url=params.image_url,
        pack=params.pack,
        frame_count=params.frame_count,
        fps=params.fps,
        frame_layout=params.frame_layout,
        overwrite=params.overwrite,
        actor=get_current_user(),
    )


@tool()
@safe_tool
def register_sprite_batch(params: RegisterSpriteBatchIn) -> dict[str, Any]:
    """Upload one spritesheet and register many named tiles in one call.

    Staff-parent only (Audit C5). Per-tile errors surface in the
    ``skipped`` list without aborting the batch, so a partial sheet
    registration always completes. Source sheet is NOT persisted —
    re-authoring requires re-upload.
    """
    require_staff_parent()
    tiles = [t.model_dump() for t in params.tiles]
    return _wrap_svc_call(
        svc.register_sprite_batch,
        sheet_b64=params.sheet_b64,
        sheet_url=params.sheet_url,
        tile_size=params.tile_size,
        tiles=tiles,
        overwrite=params.overwrite,
        actor=get_current_user(),
    )


@tool()
@safe_tool
def list_sprites(params: ListSpritesIn) -> dict[str, Any]:
    """Enumerate registered sprites (parent-only, read-only).

    Used before authoring to check for slug collisions. Returns a list
    ordered by slug; filter by ``pack`` for quick narrowing.
    """
    require_parent()
    qs = SpriteAsset.objects.all()
    if params.pack:
        qs = qs.filter(pack=params.pack)
    qs = qs.order_by("slug")[: params.limit]
    return {
        "sprites": [
            {
                "slug": a.slug,
                "url": a.image.url,
                "pack": a.pack,
                "frame_count": a.frame_count,
                "fps": a.fps,
                "frame_width_px": a.frame_width_px,
                "frame_height_px": a.frame_height_px,
                "frame_layout": a.frame_layout,
            }
            for a in qs
        ],
    }


@tool()
@safe_tool
def get_sprite(params: GetSpriteIn) -> Any:
    """Fetch the full authoring shape for one sprite.

    Parent-only, read-only. Returns everything ``list_sprites`` returns
    plus the authoring inputs that were sent to Gemini: ``prompt``,
    ``original_intent``, ``motion``, ``style_hint``, ``tile_size``,
    ``reference_image_url``. Pair with ``get_sprite_prompting_playbook``
    when critiquing or rerolling — the playbook gives the prompt-
    engineering rules; this tool gives the row's actual inputs.

    With ``include_image=True`` the response is a 2-element list:
    ``[<authoring shape>, <ImageContent block>]``. FastMCP serializes
    the dict as a text JSON content block and passes the
    ``ImageContent`` through as-is, so the chat agent sees both the
    metadata and the rendered sprite in its context window without
    fetching the public Ceph URL. Refuses sprites whose raw decoded
    size (``frame_count × frame_width_px × frame_height_px × 4``)
    exceeds ``_SPRITE_INLINE_MAX_BYTES`` — caller should fall back
    to ``url`` for an out-of-band HTTP fetch on those.
    """
    require_parent()
    try:
        a = SpriteAsset.objects.get(slug=params.slug)
    except SpriteAsset.DoesNotExist:
        raise MCPNotFoundError(f"Sprite {params.slug!r} not found.")
    payload: dict[str, Any] = {
        "slug": a.slug,
        "url": a.image.url if a.image else "",
        "pack": a.pack,
        "frame_count": a.frame_count,
        "fps": a.fps,
        "frame_width_px": a.frame_width_px,
        "frame_height_px": a.frame_height_px,
        "frame_layout": a.frame_layout,
        "prompt": a.prompt,
        "original_intent": a.original_intent,
        "motion": a.motion,
        "style_hint": a.style_hint,
        "tile_size": a.tile_size,
        "reference_image_url": a.reference_image_url,
    }
    if not params.include_image:
        return payload

    if not a.image:
        raise MCPValidationError(
            f"sprite {a.slug!r} has no image bytes to return.",
        )
    raw_estimate = (a.frame_count or 1) * (a.frame_width_px or 0) * (a.frame_height_px or 0) * 4
    if raw_estimate > _SPRITE_INLINE_MAX_BYTES:
        raise MCPValidationError(
            f"sprite {a.slug!r} too large to inline "
            f"({raw_estimate} bytes raw > {_SPRITE_INLINE_MAX_BYTES} cap) — "
            f"fetch via the ``url`` field instead.",
        )
    # Import lazily so the module stays importable without the MCP SDK.
    from mcp.types import ImageContent
    with a.image.open("rb") as fh:
        data = fh.read()
    mime, _ = mimetypes.guess_type(a.image.name or "sprite.png")
    image_block = ImageContent(
        type="image",
        data=base64.b64encode(data).decode("ascii"),
        mimeType=mime or "image/png",
    )
    return [payload, image_block]


@tool()
@safe_tool
def generate_sprite_sheet(params: GenerateSpriteSheetIn) -> dict[str, Any]:
    """Generate a sprite (static or animated strip) from a text prompt.

    Parent-only. Calls Google's Gemini 3 Pro Image ("Nano Banana Pro") to
    produce pixel-art frames, then hands the result to ``register_sprite``
    so the new slug lands in the public sprite catalog immediately. For
    animations, each frame after the first passes the previous frame as a
    reference image so character design stays consistent across frames.

    Requires ``GEMINI_API_KEY`` in settings. ``frame_count`` is capped by
    ``SPRITE_GENERATION_MAX_FRAMES`` (default 8).

    Audit C5: gated on ``require_staff_parent`` to match the equivalent
    HTTP endpoint (``SpriteGenerateView`` uses ``IsStaffParent``). The
    sprite catalog is global content visible to every family; a self-signup
    parent must not be able to write to it via the MCP channel either.
    """
    require_staff_parent()
    return _wrap_svc_call(
        gen_svc.generate_sprite_sheet,
        slug=params.slug,
        prompt=params.prompt,
        frame_count=params.frame_count,
        tile_size=params.tile_size,
        fps=params.fps,
        pack=params.pack,
        style_hint=params.style_hint,
        motion=params.motion,
        reference_image_url=params.reference_image_url,
        original_intent=params.original_intent,
        return_debug_raw=params.return_debug_raw,
        overwrite=params.overwrite,
        actor=get_current_user(),
    )


@tool()
@safe_tool
def update_sprite_metadata(params: UpdateSpriteMetadataIn) -> dict[str, Any]:
    """Update metadata (fps, pack) on an existing sprite without
    regenerating the image.

    Staff-parent only (Audit C5). Use this to tune animation speed on an
    already-good sprite, or to reorganize sprites between packs during a
    curation pass. Frame dimensions and frame_count are NOT editable —
    those are tied to the underlying image content. To change them,
    re-register the sprite with a new image via ``register_sprite``
    or ``generate_sprite_sheet``.
    """
    require_staff_parent()
    return _wrap_svc_call(
        svc.update_sprite_metadata,
        slug=params.slug,
        fps=params.fps,
        pack=params.pack,
    )


@tool()
@safe_tool
def delete_sprite(params: DeleteSpriteIn) -> dict[str, Any]:
    """Remove a sprite (DB row + Ceph blob, blob-first).

    Staff-parent only (Audit C5 — sprite catalog is global content).
    Dangling ``sprite_key`` references in content YAML or model rows are
    NOT cleaned up — they emoji-fallback in the UI, which is the existing
    contract when a slug is unknown.
    """
    require_staff_parent()
    return _wrap_svc_call(svc.delete_sprite, slug=params.slug)


@tool()
@safe_tool
def reroll_sprite(params: RerollSpriteIn) -> dict[str, Any]:
    """Re-run generation for an existing sprite using its stored inputs.

    Audit C5: gated on ``require_staff_parent`` to match the equivalent
    HTTP endpoint (``SpriteRerollView`` uses ``IsStaffParent``). Reroll
    burns Gemini API budget on a global-content row — a regular signup
    parent must not be able to trigger it via the MCP channel.

    Mirrors ``POST /api/sprites/admin/<slug>/reroll/`` — replays the row's
    stored ``prompt / motion / style_hint / tile_size / reference_image_url
    / frame_count / fps / pack`` with ``overwrite=True``. Returns 400 if
    the sprite has no stored prompt (legacy upload — use
    ``generate_sprite_sheet`` directly).

    Optional overrides (``prompt``, ``motion``, ``style_hint``,
    ``tile_size``) layer on top of the stored row, enabling the chat-side
    critique loop: call ``propose_sprite_reroll`` to get a refined prompt,
    then pass the result back here. The generation service persists the
    inputs it ran with at the end of the pipeline, so the NEXT reroll
    resumes from the refined state automatically.

    The reroll path also passes ``tighten_reference=True`` to the
    generation service so the existing sprite's PNG (when used as the
    reference image for self-anchored animation or style preservation)
    gets autocropped before Gemini sees it — preventing the
    rerolls-keep-shrinking compounding bug.
    """
    require_staff_parent()
    try:
        asset = SpriteAsset.objects.get(slug=params.slug)
    except SpriteAsset.DoesNotExist:
        raise MCPNotFoundError(f"Sprite {params.slug!r} not found.")
    if not asset.prompt:
        raise MCPValidationError(
            "no stored prompt — use generate_sprite_sheet to author from scratch.",
        )
    final_prompt = params.prompt if params.prompt is not None else asset.prompt
    final_motion = params.motion if params.motion is not None else (asset.motion or "idle")
    final_style_hint = params.style_hint if params.style_hint is not None else (asset.style_hint or "")
    final_tile_size = params.tile_size if params.tile_size is not None else (
        asset.tile_size or asset.frame_width_px or 128
    )
    return _wrap_svc_call(
        gen_svc.generate_sprite_sheet,
        slug=asset.slug,
        prompt=final_prompt,
        frame_count=asset.frame_count,
        tile_size=final_tile_size,
        fps=asset.fps,
        pack=asset.pack,
        style_hint=final_style_hint,
        motion=final_motion,
        reference_image_url=asset.reference_image_url or None,
        original_intent=asset.original_intent,
        return_debug_raw=params.return_debug_raw,
        overwrite=True,
        tighten_reference=True,
        actor=get_current_user(),
    )


# ---------------------------------------------------------------------------
# Chat-side critique loop
# ---------------------------------------------------------------------------


# Rule-based refinement levers. Each entry maps to a (a) human-readable
# rationale shown in the proposal response and (b) a prompt-fragment
# transform applied to the stored prompt. The chat agent can either
# pass ``target_changes`` explicitly or let keyword detection in the
# critique infer the right levers.
_KEYWORD_TO_LEVERS: dict[str, list[str]] = {
    # Size symptoms
    "too small": ["larger_subject"],
    "tiny": ["larger_subject"],
    "small subject": ["larger_subject"],
    "lots of empty": ["larger_subject"],
    "too much empty": ["larger_subject"],
    "wide margin": ["larger_subject"],
    "too much margin": ["larger_subject"],
    # Pose symptoms
    "wrong pose": ["switch_motion"],
    "static": ["switch_motion"],
    "stiff": ["switch_motion"],
    "no motion": ["switch_motion"],
    "doesn't animate": ["switch_motion"],
    # Style symptoms
    "wrong color": ["strengthen_style"],
    "wrong palette": ["strengthen_style"],
    "off-style": ["strengthen_style"],
    "doesn't match": ["strengthen_style"],
    "style drift": ["strengthen_style"],
    # Reference symptoms
    "looks like the reference": ["drop_reference"],
    "copied the reference": ["drop_reference"],
    "wrong creature": ["drop_reference"],
    # Tile size
    "low detail": ["bigger_tile"],
    "blurry": ["bigger_tile"],
    "pixelated": ["bigger_tile"],
}

_LEVER_RATIONALES: dict[str, str] = {
    "larger_subject": (
        "Subject reads as too small in the tile. Strengthens the OCCUPANCY "
        "clause: explicit '≥90% of canvas, edge-to-edge' wording on top of "
        "the prompt's existing size instructions."
    ),
    "switch_motion": (
        "Motion template likely doesn't match the subject. Suggests "
        "switching to 'idle' (most forgiving) or a domain-matched motion."
    ),
    "strengthen_style": (
        "Style drift detected. Appends a stronger style hint emphasizing "
        "the pack's existing palette."
    ),
    "drop_reference": (
        "Reference image is causing creature-class over-copy. Suggests "
        "rerolling WITHOUT the reference — but ``reroll_sprite`` reads "
        "the stored reference_image_url. To actually drop it, the caller "
        "must PATCH the asset row first or use ``generate_sprite_sheet`` "
        "directly with ``reference_image_url=None``."
    ),
    "bigger_tile": (
        "Tile too small for the level of detail Gemini is drawing. "
        "Suggests bumping tile_size from 32 → 64 or 64 → 128."
    ),
}


def _detect_levers(critique: str) -> list[str]:
    """Return the deduped, ordered list of refinement levers implied by
    free-form keyword detection. Order matches first-occurrence in the
    critique so the highest-priority symptom comes first.
    """
    lowered = critique.lower()
    seen: list[str] = []
    for keyword, levers in _KEYWORD_TO_LEVERS.items():
        if keyword in lowered:
            for lever in levers:
                if lever not in seen:
                    seen.append(lever)
    return seen


# Reusable occupancy clause appended to the prompt when ``larger_subject``
# fires. Stronger than the suffix's default wording — kid-friendly
# "BIGGER" emphasis that Gemini's instruction-following respects.
_OCCUPANCY_BOOST_CLAUSE = (
    " IMPORTANT — SIZE: the subject MUST be drawn AT LEAST 90% of the "
    "canvas size in its longest dimension. The character should fill "
    "the frame nearly edge-to-edge with only a hairline magenta margin. "
    "Do NOT draw a small subject in the middle of a large empty canvas. "
    "Bigger is better — when in doubt, draw it LARGER."
)


def _refine_prompt(base_prompt: str, levers: list[str]) -> str:
    """Return ``base_prompt`` augmented with the prompt-side adjustments
    implied by each lever in ``levers``. Levers that aren't prompt-side
    (e.g. ``bigger_tile``, ``switch_motion``) leave the prompt alone."""
    refined = base_prompt
    if "larger_subject" in levers and _OCCUPANCY_BOOST_CLAUSE not in refined:
        refined = refined.rstrip() + _OCCUPANCY_BOOST_CLAUSE
    return refined


def _propose_tile_size(current: int, levers: list[str]) -> int:
    """Apply ``bigger_tile`` lever to the current tile_size when relevant."""
    if "bigger_tile" not in levers:
        return current
    if current == 32:
        return 64
    if current == 64:
        return 128
    return current  # already at 128 — can't go bigger


def _propose_motion(current: str, levers: list[str]) -> str:
    """Apply ``switch_motion`` lever — defaults to 'idle' (safest) when
    the chat hasn't picked a specific replacement.
    """
    if "switch_motion" not in levers:
        return current
    if current == "idle":
        # Already at the safest motion; the issue probably isn't motion.
        return current
    return "idle"


def _propose_style_hint(current: str, levers: list[str]) -> str:
    """Apply ``strengthen_style`` lever — appends a one-liner the chat
    can edit further. Keeps the existing hint when present."""
    if "strengthen_style" not in levers:
        return current
    addendum = " match the pack's existing palette closely"
    if current and addendum.strip() not in current:
        return (current + ";" + addendum).strip()
    if not current:
        return "match the pack's existing palette closely"
    return current


_VALID_LEVERS = set(_LEVER_RATIONALES.keys())


@tool()
@safe_tool
def propose_sprite_reroll(params: ProposeSpriteRerollIn) -> dict[str, Any]:
    """Construct a refined reroll plan for an existing sprite.

    Parent-only, **does NOT call Gemini** — purely a prompt-construction
    helper. Pair with ``get_sprite(include_image=True)`` (so the chat
    agent can see the rendered sprite for vision critique) and
    ``get_sprite_prompting_playbook`` (which describes the failure
    modes this tool's rules cover). The chat agent then passes the
    proposed inputs to ``reroll_sprite`` to actually regenerate.

    Returns the current authoring inputs, the proposed inputs, the
    refinement levers selected, and a per-lever rationale so the chat
    agent can show its work to the user before triggering the reroll.

    Levers can be supplied explicitly via ``target_changes`` (overrides
    keyword detection) or inferred from the critique text — see the
    ``_KEYWORD_TO_LEVERS`` map for the recognized phrasings. Unknown
    explicit levers raise ``MCPValidationError``.
    """
    require_parent()
    try:
        asset = SpriteAsset.objects.get(slug=params.slug)
    except SpriteAsset.DoesNotExist:
        raise MCPNotFoundError(f"Sprite {params.slug!r} not found.")
    if not asset.prompt:
        raise MCPValidationError(
            "no stored prompt — propose_sprite_reroll needs a baseline to "
            "refine. Use generate_sprite_sheet directly for legacy uploads.",
        )

    if params.target_changes:
        unknown = [t for t in params.target_changes if t not in _VALID_LEVERS]
        if unknown:
            raise MCPValidationError(
                f"unknown target_changes: {unknown}. Valid levers: "
                f"{sorted(_VALID_LEVERS)}",
            )
        levers = list(dict.fromkeys(params.target_changes))  # dedupe, preserve order
    else:
        levers = _detect_levers(params.critique)

    current_tile_size = asset.tile_size or asset.frame_width_px or 128
    current_motion = asset.motion or "idle"
    current_style_hint = asset.style_hint or ""

    proposed_prompt = _refine_prompt(asset.prompt, levers)
    proposed_tile_size = _propose_tile_size(current_tile_size, levers)
    proposed_motion = _propose_motion(current_motion, levers)
    proposed_style_hint = _propose_style_hint(current_style_hint, levers)

    rationale = [
        {"lever": lever, "explanation": _LEVER_RATIONALES[lever]}
        for lever in levers
    ]

    return {
        "slug": asset.slug,
        "current_prompt": asset.prompt,
        "original_intent": asset.original_intent,
        "current_motion": current_motion,
        "current_style_hint": current_style_hint,
        "current_tile_size": current_tile_size,
        "proposed_prompt": proposed_prompt,
        "proposed_motion": proposed_motion,
        "proposed_style_hint": proposed_style_hint,
        "proposed_tile_size": proposed_tile_size,
        "levers": levers,
        "rationale": rationale,
        "critique": params.critique,
    }
