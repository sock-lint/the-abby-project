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
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import SpriteAuthoringError

from ..context import require_parent, require_staff_parent, get_current_user
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    DeleteSpriteIn,
    GetSpriteIn,
    ListSpritesIn,
    RegisterSpriteBatchIn,
    RegisterSpriteIn,
    UpdateSpriteMetadataIn,
)
from ..server import tool


# Cap on the inline-image payload returned by ``get_sprite(include_image=True)``.
# Measured against the worst-case raw decoded size
# (frame_count × width × height × 4 RGBA bytes), not the PNG file size on disk
# — that way the LLM context-window estimate is an upper bound rather than a
# guess. Pixel-art sprites in this codebase top out around 24KB raw for a
# 4-frame 64×64 strip, so the cap leaves plenty of room while refusing to
# return e.g. a 1024×1024 16-frame sheet (~64 MB raw) inline.
_SPRITE_INLINE_MAX_BYTES = 200_000


def _wrap_svc_call(fn, **kwargs) -> dict[str, Any]:
    try:
        return fn(**kwargs)
    except SpriteAuthoringError as exc:
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
    plus any historical authoring inputs retained on the catalog row.
    Generation has been retired; these fields remain read-only history.

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
def update_sprite_metadata(params: UpdateSpriteMetadataIn) -> dict[str, Any]:
    """Update metadata (fps, pack) on an existing sprite without
    regenerating the image.

    Staff-parent only (Audit C5). Use this to tune animation speed on an
    already-good sprite, or to reorganize sprites between packs during a
    curation pass. Frame dimensions and frame_count are NOT editable —
    those are tied to the underlying image content. To change them,
    re-register prepared artwork via ``register_sprite``.
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
