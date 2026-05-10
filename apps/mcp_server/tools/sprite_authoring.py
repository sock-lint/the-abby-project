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

from typing import Any

from apps.rpg import sprite_authoring as svc
from apps.rpg import sprite_generation as gen_svc
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import SpriteAuthoringError
from apps.rpg.sprite_generation import SpriteGenerationError

from ..context import require_parent, require_staff_parent, get_current_user
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    DeleteSpriteIn,
    GenerateSpriteSheetIn,
    GetSpriteIn,
    ListSpritesIn,
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
def get_sprite(params: GetSpriteIn) -> dict[str, Any]:
    """Fetch the full authoring shape for one sprite.

    Parent-only, read-only. Returns everything ``list_sprites`` returns
    plus the authoring inputs that were sent to Gemini: ``prompt``,
    ``original_intent``, ``motion``, ``style_hint``, ``tile_size``,
    ``reference_image_url``. Pair with ``get_sprite_prompting_playbook``
    when critiquing or rerolling — the playbook gives the prompt-
    engineering rules; this tool gives the row's actual inputs.
    """
    require_parent()
    try:
        a = SpriteAsset.objects.get(slug=params.slug)
    except SpriteAsset.DoesNotExist:
        raise MCPNotFoundError(f"Sprite {params.slug!r} not found.")
    return {
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
    tile_size = asset.tile_size or asset.frame_width_px or 64
    motion = asset.motion or "idle"
    return _wrap_svc_call(
        gen_svc.generate_sprite_sheet,
        slug=asset.slug,
        prompt=asset.prompt,
        frame_count=asset.frame_count,
        tile_size=tile_size,
        fps=asset.fps,
        pack=asset.pack,
        style_hint=asset.style_hint,
        motion=motion,
        reference_image_url=asset.reference_image_url or None,
        original_intent=asset.original_intent,
        return_debug_raw=params.return_debug_raw,
        overwrite=True,
        actor=get_current_user(),
    )
