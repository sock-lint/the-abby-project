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


def _fetch_url(url: str) -> bytes:
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
    if len(resp.content) > MAX_IMAGE_BYTES:
        raise SpriteAuthoringError(
            f"fetched image exceeds {MAX_IMAGE_BYTES} bytes",
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
