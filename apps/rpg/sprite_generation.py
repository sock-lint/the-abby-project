"""Text-to-sprite-sheet generation via Gemini 3 Pro Image (Nano Banana Pro).

Parent-only authoring service invoked from the MCP tool layer. Produces
either a single static sprite or a horizontal animation strip, then hands
the resulting PNG to the existing ``sprite_authoring.register_sprite``
service — so storage, hashing, Ceph upload, and DB upsert all reuse the
already-tested write path.

Animation uses **iterative** generation: frame 1 is prompted from text
only; frames 2..N are prompted with the previous frame as a reference
image so Nano Banana Pro's multi-turn character consistency keeps the
subject recognisable across the strip.

Tests mock ``_generate_frame`` — the single API seam. No other symbol
should call into ``google.genai`` directly.
"""
from __future__ import annotations

import base64
import io
from typing import Any, Optional

from PIL import Image, UnidentifiedImageError
from django.conf import settings

from apps.accounts.models import User
from apps.rpg import sprite_authoring as svc
from apps.rpg.sprite_authoring import SpriteAuthoringError


DEFAULT_MAX_FRAMES = 8
ALLOWED_TILE_SIZES = (32, 64, 128)

WALK_CYCLE_TEMPLATE = (
    "neutral stance, weight on both legs",
    "right leg forward, mid-stride",
    "mid-stride, weight centered",
    "left leg forward, mid-stride",
)

PROMPT_SUFFIX = (
    " Pixel art style. Transparent background. Centered subject, "
    "full body visible. No text, no UI, no borders, no watermark."
)


class SpriteGenerationError(Exception):
    """Raised on any user-visible failure in the generation service.

    Callers (MCP tools, ad-hoc scripts) translate this to their surface's
    error type — the MCP tool wraps it in ``MCPValidationError`` to match
    the existing sprite-authoring tools.
    """


def _get_client() -> Any:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise SpriteGenerationError(
            "GEMINI_API_KEY is not configured; set it in .env to enable "
            "sprite generation.",
        )
    try:
        from google import genai
    except ImportError as exc:
        raise SpriteGenerationError(
            f"google-genai package not installed: {exc}",
        )
    return genai.Client(api_key=api_key)


def _extract_png_bytes(response: Any) -> bytes:
    """Pull the first inline image payload out of a Gemini response."""
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        if content is None:
            continue
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline is not None else None
            if data:
                return data
    raise SpriteGenerationError(
        "Gemini response did not contain an image part.",
    )


def _generate_frame(
    *,
    prompt: str,
    reference_png: Optional[bytes] = None,
) -> bytes:
    """Ask Gemini for one frame. Sole API seam — tests mock this function."""
    client = _get_client()
    try:
        from google.genai import types  # noqa: F401 — used only when referenced
    except ImportError as exc:
        raise SpriteGenerationError(f"google-genai types unavailable: {exc}")

    model = getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")
    contents: list[Any] = []
    if reference_png is not None:
        contents.append(types.Part.from_bytes(data=reference_png, mime_type="image/png"))
    contents.append(prompt)

    try:
        response = client.models.generate_content(model=model, contents=contents)
    except Exception as exc:  # noqa: BLE001
        raise SpriteGenerationError(f"Gemini API call failed: {exc}")
    return _extract_png_bytes(response)


def _resize_to_tile(png_bytes: bytes, tile_size: int) -> bytes:
    try:
        src = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteGenerationError(f"Gemini returned an invalid image: {exc}")
    tile = src.resize((tile_size, tile_size), Image.LANCZOS)
    out = io.BytesIO()
    tile.save(out, format="PNG")
    return out.getvalue()


def _stitch_strip(frames: list[bytes], tile_size: int) -> bytes:
    n = len(frames)
    canvas = Image.new("RGBA", (tile_size * n, tile_size), (0, 0, 0, 0))
    for i, frame_bytes in enumerate(frames):
        frame = Image.open(io.BytesIO(frame_bytes)).convert("RGBA")
        canvas.paste(frame, (i * tile_size, 0))
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def _build_prompt(
    *,
    subject: str,
    style_hint: str = "",
    frame_note: str = "",
) -> str:
    parts = [subject.strip()]
    if style_hint.strip():
        parts.append(style_hint.strip())
    if frame_note:
        parts.append(frame_note)
    return ". ".join(p for p in parts if p) + "." + PROMPT_SUFFIX


def generate_sprite_sheet(
    *,
    slug: str,
    prompt: str,
    frame_count: int = 1,
    tile_size: int = 64,
    fps: int = 0,
    pack: str = "ai-generated",
    style_hint: str = "",
    overwrite: bool = False,
    actor: Optional[User] = None,
) -> dict[str, Any]:
    """Generate a sprite (static or animated) from a text prompt.

    Returns the same dict shape as ``sprite_authoring.register_sprite`` so
    callers can treat it as drop-in.
    """
    max_frames = getattr(settings, "SPRITE_GENERATION_MAX_FRAMES", DEFAULT_MAX_FRAMES)
    if frame_count < 1 or frame_count > max_frames:
        raise SpriteGenerationError(
            f"frame_count must be between 1 and {max_frames}; got {frame_count}.",
        )
    if tile_size not in ALLOWED_TILE_SIZES:
        raise SpriteGenerationError(
            f"tile_size must be one of {ALLOWED_TILE_SIZES}; got {tile_size}.",
        )
    if frame_count > 1 and fps < 1:
        raise SpriteGenerationError(
            "animated sprites (frame_count > 1) require fps >= 1.",
        )
    if frame_count == 1 and fps != 0:
        raise SpriteGenerationError(
            "static sprites (frame_count == 1) require fps == 0.",
        )

    frames: list[bytes] = []
    if frame_count == 1:
        full_prompt = _build_prompt(subject=prompt, style_hint=style_hint)
        raw = _generate_frame(prompt=full_prompt)
        frames.append(_resize_to_tile(raw, tile_size))
    else:
        # Frame 1 — text-only prompt, no reference.
        first_note = f"Frame 1 of {frame_count}: {WALK_CYCLE_TEMPLATE[0]}"
        first_raw = _generate_frame(prompt=_build_prompt(
            subject=prompt, style_hint=style_hint, frame_note=first_note,
        ))
        frames.append(_resize_to_tile(first_raw, tile_size))
        # Frames 2..N — each passes the previous (already tile-sized) frame.
        for i in range(1, frame_count):
            motion = WALK_CYCLE_TEMPLATE[i % len(WALK_CYCLE_TEMPLATE)]
            frame_note = (
                f"Frame {i + 1} of {frame_count}: {motion}. "
                "Keep the same character design, palette, and proportions "
                "as the reference frame — only adjust the pose."
            )
            raw = _generate_frame(
                prompt=_build_prompt(
                    subject=prompt, style_hint=style_hint, frame_note=frame_note,
                ),
                reference_png=frames[-1],
            )
            frames.append(_resize_to_tile(raw, tile_size))

    sheet_bytes = frames[0] if frame_count == 1 else _stitch_strip(frames, tile_size)

    try:
        return svc.register_sprite(
            slug=slug,
            image_b64=base64.b64encode(sheet_bytes).decode(),
            pack=pack,
            frame_count=frame_count,
            fps=fps,
            frame_layout="horizontal",
            overwrite=overwrite,
            actor=actor,
        )
    except SpriteAuthoringError as exc:
        raise SpriteGenerationError(str(exc))
