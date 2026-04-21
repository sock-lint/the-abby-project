"""Service layer for runtime sprite authoring.

Orchestrates: decode/download PNG bytes → validate with Pillow → compute
content hash → upload to the sprite bucket (via SpriteAsset.image) →
upsert the DB row. Callable from both the MCP tool layer and from the
data-migration that imports legacy sprites.

The service intentionally does NOT check permissions — callers (MCP tools,
API views, migrations) enforce their own auth. This mirrors the
project's other service modules (e.g., apps/rpg/services.py).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
from typing import Any, Optional

import requests
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from apps.accounts.models import User
from apps.rpg.models import SpriteAsset


MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB cap for single-sprite uploads
MAX_DIMENSION_PX = 4096


class SpriteAuthoringError(Exception):
    """Raised on any user-visible validation failure in the service layer.

    Callers translate this to their surface's error type — MCP tools wrap
    it in MCPValidationError, API views return 400.
    """


def _decode_b64(b64: str) -> bytes:
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SpriteAuthoringError(f"image_b64 is not valid base64: {exc}")


def _validate_png(png_bytes: bytes) -> tuple[int, int, str]:
    if len(png_bytes) > MAX_IMAGE_BYTES:
        raise SpriteAuthoringError(
            f"image exceeds {MAX_IMAGE_BYTES} bytes "
            f"({len(png_bytes)} received).",
        )
    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.verify()  # raises on corrupt images
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteAuthoringError(f"not a valid PNG/WebP image: {exc}")
    # Pillow verify() closes the image; reopen for dimensions.
    img = Image.open(io.BytesIO(png_bytes))
    if img.format not in ("PNG", "WEBP"):
        raise SpriteAuthoringError(f"format {img.format!r} not supported; use PNG or WebP")
    if img.width > MAX_DIMENSION_PX or img.height > MAX_DIMENSION_PX:
        raise SpriteAuthoringError(
            f"image dimensions {img.width}x{img.height} exceed "
            f"{MAX_DIMENSION_PX}px limit.",
        )
    return img.width, img.height, img.format  # return format too


def _fetch_url(url: str, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise SpriteAuthoringError(f"failed to fetch image: {exc}")
    ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if ctype not in ("image/png", "image/webp"):
        raise SpriteAuthoringError(
            f"Content-Type {ctype!r} not accepted; must be image/png or image/webp",
        )
    if len(resp.content) > max_bytes:
        raise SpriteAuthoringError(
            f"fetched image exceeds {max_bytes} bytes",
        )
    return resp.content


def register_sprite(
    *,
    slug: str,
    image_b64: Optional[str] = None,
    image_url: Optional[str] = None,
    pack: str = "user-authored",
    frame_count: int = 1,
    fps: int = 0,
    frame_layout: str = "horizontal",
    overwrite: bool = False,
    actor: Optional[User] = None,
) -> dict[str, Any]:
    """Register a single sprite (static or animation strip) from bytes.

    Exactly one of ``image_b64`` / ``image_url`` must be provided.
    Returns a structured dict matching the MCP tool's contract.
    """
    if bool(image_b64) == bool(image_url):
        raise SpriteAuthoringError(
            "exactly one of image_b64 or image_url must be provided.",
        )

    if image_b64:
        png_bytes = _decode_b64(image_b64)
    else:
        png_bytes = _fetch_url(image_url)

    total_w, total_h, fmt = _validate_png(png_bytes)

    # Compute per-frame dimensions for animation strips.
    if frame_count == 1:
        frame_w, frame_h = total_w, total_h
    elif frame_layout == "horizontal":
        if total_w % frame_count != 0:
            raise SpriteAuthoringError(
                f"animated strip width {total_w}px is not divisible by "
                f"frame_count={frame_count}.",
            )
        frame_w, frame_h = total_w // frame_count, total_h
    else:  # vertical
        if total_h % frame_count != 0:
            raise SpriteAuthoringError(
                f"animated strip height {total_h}px is not divisible by "
                f"frame_count={frame_count}.",
            )
        frame_w, frame_h = total_w, total_h // frame_count

    ext = "webp" if fmt == "WEBP" else "png"
    digest = hashlib.sha256(png_bytes).hexdigest()[:8]
    filename = f"{slug}-{digest}.{ext}"

    existing = SpriteAsset.objects.filter(slug=slug).first()
    if existing and not overwrite:
        raise SpriteAuthoringError(
            f"sprite {slug!r} already exists; pass overwrite=True to replace.",
        )
    if existing:
        existing.image.delete(save=False)  # Ceph blob first, per storage-deletes invariant

    asset = existing or SpriteAsset(slug=slug)
    asset.pack = pack
    asset.frame_count = frame_count
    asset.fps = fps
    asset.frame_width_px = frame_w
    asset.frame_height_px = frame_h
    asset.frame_layout = frame_layout
    asset.created_by = actor
    asset.full_clean()  # triggers SpriteAsset.clean() → validates frame/fps combo
    asset.image.save(filename, ContentFile(png_bytes), save=False)
    asset.save()

    return {
        "slug": asset.slug,
        "url": asset.image.url,
        "pack": asset.pack,
        "frame_count": asset.frame_count,
        "fps": asset.fps,
        "frame_width_px": asset.frame_width_px,
        "frame_height_px": asset.frame_height_px,
        "frame_layout": asset.frame_layout,
    }


MAX_SHEET_BYTES = 20 * 1024 * 1024  # sheets can be up to 20 MB


def register_sprite_batch(
    *,
    sheet_b64: Optional[str] = None,
    sheet_url: Optional[str] = None,
    tile_size: int,
    tiles: list[dict[str, Any]],
    overwrite: bool = False,
    actor: Optional[User] = None,
) -> dict[str, Any]:
    """Slice a spritesheet into many named tile sprites in one call.

    Each tile dict accepts: ``slug`` (required), ``col`` (required),
    ``row`` (required), ``frame_count`` (default 1 — animation frames
    extend rightward from col), ``fps`` (default 0), ``pack`` (default
    "user-authored"). Per-tile failures are collected in the ``skipped``
    list rather than aborting the whole batch.
    """
    if bool(sheet_b64) == bool(sheet_url):
        raise SpriteAuthoringError("exactly one of sheet_b64 or sheet_url must be provided.")

    if tile_size <= 0:
        raise SpriteAuthoringError(
            f"tile_size must be a positive integer; got {tile_size!r}",
        )

    if sheet_b64:
        sheet_bytes = _decode_b64(sheet_b64)
        if len(sheet_bytes) > MAX_SHEET_BYTES:
            raise SpriteAuthoringError(f"sheet exceeds {MAX_SHEET_BYTES} bytes")
    else:
        sheet_bytes = _fetch_url(sheet_url, max_bytes=MAX_SHEET_BYTES)

    try:
        sheet_img = Image.open(io.BytesIO(sheet_bytes))
        sheet_img.load()  # force decode to catch corruption
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteAuthoringError(f"sheet is not a valid image: {exc}")

    if sheet_img.format not in ("PNG", "WEBP"):
        raise SpriteAuthoringError(f"sheet format {sheet_img.format!r} not supported")

    cols_max = sheet_img.width // tile_size
    rows_max = sheet_img.height // tile_size

    registered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for tile in tiles:
        missing = [k for k in ("slug", "col", "row") if k not in tile]
        if missing:
            skipped.append({
                "slug": tile.get("slug", "<unknown>"),
                "reason": f"missing required keys: {missing}",
            })
            continue
        slug = tile["slug"]
        col = tile["col"]
        row = tile["row"]
        fc = tile.get("frame_count", 1)
        fps = tile.get("fps", 0)
        pack = tile.get("pack", "user-authored")

        # Bounds check: tile extends `fc` columns to the right from (col, row)
        if col < 0 or row < 0 or row >= rows_max or col + fc > cols_max:
            skipped.append({
                "slug": slug,
                "reason": f"tile out of bounds (col={col}, row={row}, fc={fc}; sheet is {cols_max}x{rows_max} tiles)",
            })
            continue

        # Crop the tile region and re-encode as standalone PNG
        left = col * tile_size
        top = row * tile_size
        right = (col + fc) * tile_size
        bottom = (row + 1) * tile_size
        crop = sheet_img.crop((left, top, right, bottom))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        tile_bytes = buf.getvalue()
        tile_b64 = base64.b64encode(tile_bytes).decode()

        try:
            result = register_sprite(
                slug=slug,
                image_b64=tile_b64,
                pack=pack,
                frame_count=fc,
                fps=fps,
                frame_layout="horizontal",
                overwrite=overwrite,
                actor=actor,
            )
            registered.append(result)
        except SpriteAuthoringError as exc:
            skipped.append({"slug": slug, "reason": str(exc)})

    return {"registered": registered, "skipped": skipped}


def update_sprite_metadata(
    *,
    slug: str,
    fps: Optional[int] = None,
    pack: Optional[str] = None,
) -> dict[str, Any]:
    """Change metadata fields on an existing sprite without touching
    the image blob. Image content stays on Ceph at the same URL —
    only the ``SpriteAsset`` row changes.

    Validates via ``full_clean()`` before saving, so updates that
    would violate ``SpriteAsset``'s fps/frame_count invariants
    (e.g. setting fps=8 on a static sprite) raise
    ``SpriteAuthoringError`` and the row is left unchanged.
    """
    try:
        asset = SpriteAsset.objects.get(slug=slug)
    except SpriteAsset.DoesNotExist:
        raise SpriteAuthoringError(f"sprite {slug!r} not found")

    if fps is None and pack is None:
        raise SpriteAuthoringError(
            "update_sprite_metadata requires at least one of fps / pack",
        )
    if fps is not None:
        asset.fps = fps
    if pack is not None:
        asset.pack = pack

    try:
        asset.full_clean()
    except ValidationError as exc:
        # Don't save — the row on disk stays valid.
        messages = "; ".join(
            f"{field}: {', '.join(errs)}"
            for field, errs in exc.message_dict.items()
        )
        raise SpriteAuthoringError(f"invalid metadata update: {messages}")
    asset.save(update_fields=["fps", "pack", "updated_at"])

    return {
        "slug": asset.slug,
        "url": asset.image.url,
        "pack": asset.pack,
        "frame_count": asset.frame_count,
        "fps": asset.fps,
        "frame_width_px": asset.frame_width_px,
        "frame_height_px": asset.frame_height_px,
        "frame_layout": asset.frame_layout,
    }


def delete_sprite(*, slug: str) -> dict[str, Any]:
    """Remove a sprite's DB row AND its Ceph blob.

    Blob deletion runs first (per the project's storage-deletes
    invariant): if Ceph rejects the delete, the DB row stays and we
    don't end up with a live blob + missing row.
    """
    try:
        asset = SpriteAsset.objects.get(slug=slug)
    except SpriteAsset.DoesNotExist:
        raise SpriteAuthoringError(f"sprite {slug!r} not found")

    asset.image.delete(save=False)  # blob first
    asset.delete()
    return {"slug": slug, "deleted": True}


def get_catalog() -> dict[str, Any]:
    """Return the full slug → metadata map for the frontend catalog API.

    Response shape matches the ``GET /api/sprites/catalog/`` contract.
    The ``etag`` is a stable hash of (slug, image-key) pairs so a client
    can send If-None-Match on subsequent fetches.
    """
    assets = SpriteAsset.objects.order_by("slug").only(
        "slug", "image", "frame_count", "fps",
        "frame_width_px", "frame_height_px", "frame_layout",
    )
    sprites: dict[str, dict[str, Any]] = {}
    etag_parts: list[str] = []
    for a in assets:
        sprites[a.slug] = {
            "url": a.image.url,
            "frames": a.frame_count,
            "fps": a.fps,
            "w": a.frame_width_px,
            "h": a.frame_height_px,
            "layout": a.frame_layout,
        }
        etag_parts.append(f"{a.slug}:{a.image.name}")
    etag = hashlib.sha256("|".join(etag_parts).encode()).hexdigest()[:16]
    return {"sprites": sprites, "etag": etag}
