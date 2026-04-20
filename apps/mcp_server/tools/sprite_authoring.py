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

from ..context import require_parent, get_current_user
from ..errors import MCPValidationError, safe_tool
from ..schemas import (
    DeleteSpriteIn,
    GenerateSpriteSheetIn,
    ListSpritesIn,
    RegisterSpriteBatchIn,
    RegisterSpriteIn,
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

    Parent-only. Returns the sprite's URL + dimensions + animation metadata
    so the LLM can confirm the upload and reference the slug in
    subsequent content YAML.
    """
    require_parent()
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

    Parent-only. Per-tile errors surface in the ``skipped`` list without
    aborting the batch, so a partial sheet registration always completes.
    Source sheet is NOT persisted — re-authoring requires re-upload.
    """
    require_parent()
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
def generate_sprite_sheet(params: GenerateSpriteSheetIn) -> dict[str, Any]:
    """Generate a sprite (static or animated strip) from a text prompt.

    Parent-only. Calls Google's Gemini 3 Pro Image ("Nano Banana Pro") to
    produce pixel-art frames, then hands the result to ``register_sprite``
    so the new slug lands in the public sprite catalog immediately. For
    animations, each frame after the first passes the previous frame as a
    reference image so character design stays consistent across frames.

    Requires ``GEMINI_API_KEY`` in settings. ``frame_count`` is capped by
    ``SPRITE_GENERATION_MAX_FRAMES`` (default 8).
    """
    require_parent()
    return _wrap_svc_call(
        gen_svc.generate_sprite_sheet,
        slug=params.slug,
        prompt=params.prompt,
        frame_count=params.frame_count,
        tile_size=params.tile_size,
        fps=params.fps,
        pack=params.pack,
        style_hint=params.style_hint,
        overwrite=params.overwrite,
        actor=get_current_user(),
    )


@tool()
@safe_tool
def delete_sprite(params: DeleteSpriteIn) -> dict[str, Any]:
    """Remove a sprite (DB row + Ceph blob, blob-first).

    Parent-only. Dangling ``sprite_key`` references in content YAML or
    model rows are NOT cleaned up — they emoji-fallback in the UI, which
    is the existing contract when a slug is unknown.
    """
    require_parent()
    return _wrap_svc_call(svc.delete_sprite, slug=params.slug)
