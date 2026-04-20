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

# Fraction of the tile left as transparent border on each side after
# autocenter. 0.10 means the subject occupies the middle 80% of the tile.
AUTOCENTER_PADDING_FRAC = 0.10

# Motion templates — each is a 4-phase cyclic sequence keyed so frame 4
# naturally leads back to frame 1. The ``motion`` arg to
# ``generate_sprite_sheet`` picks one. Add new motions here and expose
# them via the pydantic enum in ``apps/mcp_server/schemas.py``.

# Idle: subtle breathing + tail/ear micro-motion. Most forgiving pose for
# Gemini because the per-frame deltas are small — less composition drift
# across the strip. Default motion for the tool.
IDLE_CYCLE_TEMPLATE = (
    "neutral idle pose: all four legs planted evenly, chest at resting "
    "size, tail curved downward and slightly to one side, ears relaxed",
    "light inhale: chest slightly expanded upward, body raised a hair, "
    "tail tip twitching up, ears perked very slightly",
    "full inhale peak: chest at widest, body at its highest point of "
    "the breath cycle, tail raised in a gentle mid-wag, ears fully alert",
    "exhale returning: chest settling back down, body lowering, tail "
    "curving back toward the neutral position, ears easing toward relaxed",
)

# Walk: 4-phase cyclic walk for quadrupeds (foxes have 4 legs, not 2).
# "Passing" is the pose that precedes each "contact" — so the loop is
# right-contact → passing → left-contact → passing → right-contact.
WALK_CYCLE_TEMPLATE = (
    "right-contact pose: right front leg planted forward, left rear leg "
    "planted back, body weight shifted onto the right side, tail slightly raised",
    "passing pose: all four legs passing under the body, weight centered, "
    "mid-bounce with the body at its highest point of the stride",
    "left-contact pose: left front leg planted forward, right rear leg "
    "planted back, body weight shifted onto the left side, tail slightly raised",
    "passing pose: all four legs passing under the body, weight centered, "
    "mid-bounce with the body at its highest point of the stride (opposite "
    "leg set from the previous passing pose)",
)

# Bounce: vertical hop loop — useful for items, power-ups, coins, pickups.
# No legs required, so this works for anything the subject prompt describes.
BOUNCE_CYCLE_TEMPLATE = (
    "baseline pose: subject at its resting position, neutral stance, "
    "body centered vertically in the frame",
    "mid-rise stretched: subject lifted a few pixels upward with body "
    "stretched slightly taller, as if launching into a jump",
    "peak: subject at the highest point of the bounce, body at its most "
    "stretched, with a hint of transparent space below suggesting airborne",
    "falling compressed: subject descending back toward baseline, body "
    "slightly compressed/squashed as it anticipates landing",
)

MOTION_TEMPLATES: dict[str, tuple[str, ...]] = {
    "idle": IDLE_CYCLE_TEMPLATE,
    "walk": WALK_CYCLE_TEMPLATE,
    "bounce": BOUNCE_CYCLE_TEMPLATE,
}
DEFAULT_MOTION = "idle"

PROMPT_SUFFIX = (
    " Pixel art style. Fully transparent background — no scene, no ground, "
    "no shadow. The subject MUST occupy the center of the frame with equal "
    "space on all sides; do not place the subject in any corner. The subject "
    "MUST be at the same scale as any reference image provided (do not zoom "
    "in or out). No text, no UI, no borders, no watermark, no caption."
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


def _autocenter_frame(png_bytes: bytes, tile_size: int) -> bytes:
    """Crop to the subject's alpha bounding box, scale to fit inside the
    tile with ``AUTOCENTER_PADDING_FRAC`` transparent border on each
    side, and paste onto a transparent canvas of exactly ``tile_size``
    squared. Deterministic post-processing that fixes composition drift
    in Gemini's per-frame output — the reference image passed to the
    next call is always subject-centered at the same scale, so
    iterative generation has a stable spatial grounding.
    """
    try:
        src = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteGenerationError(f"Gemini returned an invalid image: {exc}")

    canvas = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    bbox = src.getbbox()
    if bbox is None:
        # Fully transparent input — return an empty tile rather than crash.
        out = io.BytesIO()
        canvas.save(out, format="PNG")
        return out.getvalue()

    cropped = src.crop(bbox)
    cw, ch = cropped.size
    inner = max(1, int(round(tile_size * (1 - 2 * AUTOCENTER_PADDING_FRAC))))
    scale = inner / max(cw, ch)
    new_w = max(1, int(round(cw * scale)))
    new_h = max(1, int(round(ch * scale)))
    scaled = cropped.resize((new_w, new_h), Image.LANCZOS)

    x = (tile_size - new_w) // 2
    y = (tile_size - new_h) // 2
    canvas.paste(scaled, (x, y))

    out = io.BytesIO()
    canvas.save(out, format="PNG")
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
    motion: str = DEFAULT_MOTION,
    overwrite: bool = False,
    actor: Optional[User] = None,
) -> dict[str, Any]:
    """Generate a sprite (static or animated) from a text prompt.

    Returns the same dict shape as ``sprite_authoring.register_sprite`` so
    callers can treat it as drop-in. ``motion`` picks the 4-phase
    template used for animated strips (see ``MOTION_TEMPLATES``) — it's
    silently ignored when ``frame_count == 1``.
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
    # motion only matters for animated sprites, but validate unconditionally
    # so callers get a clear error regardless of frame_count.
    if motion not in MOTION_TEMPLATES:
        raise SpriteGenerationError(
            f"motion must be one of {sorted(MOTION_TEMPLATES)}; got {motion!r}.",
        )

    frames: list[bytes] = []
    if frame_count == 1:
        full_prompt = _build_prompt(subject=prompt, style_hint=style_hint)
        raw = _generate_frame(prompt=full_prompt)
        frames.append(_autocenter_frame(raw, tile_size))
    else:
        template = MOTION_TEMPLATES[motion]
        # Frame 1 — text-only prompt, no reference.
        first_note = f"Frame 1 of {frame_count}: {template[0]}"
        first_raw = _generate_frame(prompt=_build_prompt(
            subject=prompt, style_hint=style_hint, frame_note=first_note,
        ))
        frames.append(_autocenter_frame(first_raw, tile_size))
        # Frames 2..N — each passes the previous autocentered frame as
        # reference. Autocenter BEFORE using as reference so Gemini sees
        # a subject-centered image, giving consistent spatial grounding
        # across frames (prevents composition drift + makes the loop cycle).
        for i in range(1, frame_count):
            phase = template[i % len(template)]
            frame_note = (
                f"Frame {i + 1} of {frame_count}: {phase}. "
                "This MUST be the EXACT same character from the reference "
                "image — identical head shape, body proportions, color "
                "palette, markings, and silhouette. Only the pose changes "
                "to match the described phase. The character must occupy "
                "the same central position and the same size as the "
                "reference. Do not zoom, pan, or redesign the character."
            )
            raw = _generate_frame(
                prompt=_build_prompt(
                    subject=prompt, style_hint=style_hint, frame_note=frame_note,
                ),
                reference_png=frames[-1],
            )
            frames.append(_autocenter_frame(raw, tile_size))

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
