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

# Chroma-key color that we ask Gemini to fill "transparent background"
# areas with. Pure bright magenta is the classic game-dev chroma-key
# choice because it essentially never appears in real subjects. We
# strip pixels close to this color to real alpha=0 transparency after
# every Gemini call — image models love to draw the Photoshop
# transparency-checkerboard pattern when asked for "transparent
# background," so we circumvent that by asking for a specific solid
# color we can reliably remove.
CHROMA_KEY_COLOR = (255, 0, 255)
# Per-channel tolerance in absolute 0–255 distance. Moderately generous
# so anti-aliased edges that blend toward magenta also get keyed out
# and don't leave purple halos on the subject.
CHROMA_KEY_TOLERANCE = 60

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

# Bounce: squash-and-stretch loop in PLACE — motion is implied by shape
# deformation, not vertical displacement. v1.2.1's vertical-displacement
# version invited Gemini to draw scene elements (motion trails, dust,
# ground) around the moving subject; squash-and-stretch keeps the
# subject stationary so there's nothing scene-like to draw. Classic
# Disney/2D-game animation technique. Good for items, coins, pickups.
BOUNCE_CYCLE_TEMPLATE = (
    "neutral rest pose: subject at its natural resting shape and "
    "proportions, stationary in the exact center of the frame",
    "anticipation squash: subject compressed vertically into a wider-"
    "and-shorter shape as if pressing down just before a jump. The "
    "subject stays stationary in the EXACT same frame position as the "
    "previous pose — do not shift it up, down, left, or right. Only "
    "the proportions change",
    "stretch release: subject stretched vertically into a taller-and-"
    "thinner shape as if springing upward. The subject stays stationary "
    "in the EXACT same frame position — do not lift it off the ground "
    "or shift it. Only the proportions change",
    "recovery ease: subject returning toward normal proportions with a "
    "slight residual stretch. Same frame position, easing back to the "
    "resting shape",
)

MOTION_TEMPLATES: dict[str, tuple[str, ...]] = {
    "idle": IDLE_CYCLE_TEMPLATE,
    "walk": WALK_CYCLE_TEMPLATE,
    "bounce": BOUNCE_CYCLE_TEMPLATE,
}
DEFAULT_MOTION = "idle"

PROMPT_SUFFIX = (
    " Pixel art style. "
    "BACKGROUND: fill the entire image with SOLID BRIGHT MAGENTA "
    "(RGB 255, 0, 255 / hex #ff00ff) as a flat solid color. "
    "DO NOT draw a checkerboard transparency pattern. DO NOT use any "
    "other background color. "
    "STRICT: the subject exists alone on the magenta. ABSOLUTELY NOTHING "
    "ELSE. Specifically forbidden: NO ground, floor, dirt, path, platform, "
    "tile, or surface of any kind under the subject; NO shadow; NO dust, "
    "smoke, sparks, particles, or effect indicators; NO motion lines, speed "
    "marks, action arrows, or trajectory hints; NO borders, frames, boxes, "
    "or scene elements; NO text, labels, numbers, captions, watermarks, "
    "logos, or UI. The character floats in empty space on solid magenta. "
    "The subject itself MUST NOT contain magenta anywhere — use completely "
    "different colors for the character. "
    "The subject MUST occupy the center of the frame with equal space on "
    "all sides; do not place the subject in any corner."
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


def _chroma_key_to_transparent(
    png_bytes: bytes,
    color: tuple[int, int, int] = CHROMA_KEY_COLOR,
    tolerance: int = CHROMA_KEY_TOLERANCE,
) -> bytes:
    """Convert all pixels close to ``color`` to alpha=0 transparent.

    Runs on every raw Gemini output before slicing or autocentering so
    the "transparent background" the model painted (as magenta at our
    request) becomes actual PNG alpha=0 transparency. Downstream bbox
    detection then sees only the subject, not the whole cell.
    """
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteGenerationError(f"chroma-key got an invalid image: {exc}")

    tr, tg, tb = color
    pixels = list(img.getdata())
    new_pixels = [
        (r, g, b, 0) if (
            abs(r - tr) <= tolerance
            and abs(g - tg) <= tolerance
            and abs(b - tb) <= tolerance
        ) else (r, g, b, a)
        for r, g, b, a in pixels
    ]
    img.putdata(new_pixels)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _autocenter_frame(png_bytes: bytes, tile_size: int) -> bytes:
    """Crop to the subject's alpha bounding box, scale to fit inside the
    tile with ``AUTOCENTER_PADDING_FRAC`` transparent border on each
    side, and paste onto a transparent canvas of exactly ``tile_size``
    squared. Used for single-frame (static) sprites — the animated
    path uses ``_slice_and_center_sheet`` which shares a scale across
    all frames to avoid per-frame size variance.
    """
    try:
        src = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteGenerationError(f"Gemini returned an invalid image: {exc}")

    canvas = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    bbox = src.getbbox()
    if bbox is None:
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


def _slice_and_center_sheet(
    sheet_png: bytes,
    frame_count: int,
    tile_size: int,
) -> list[bytes]:
    """Slice a single Gemini-generated pose sheet into ``frame_count`` equal
    horizontal tiles, then scale every tile's subject using a SHARED scale
    factor so size stays consistent across frames.

    The shared scale is computed from the MAX subject dimension across all
    slices — so the biggest pose fits inside the tile's inner 80% window,
    and smaller poses end up proportionally smaller (not scaled up to
    match, which was v1.1's size-variance bug). Each tile's subject is
    centered on its own transparent canvas.
    """
    try:
        src = Image.open(io.BytesIO(sheet_png)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteGenerationError(f"Gemini returned an invalid image: {exc}")

    sheet_w, sheet_h = src.size
    slice_w = sheet_w // frame_count

    # Pass 1: slice the sheet and record each subject's bbox (within the slice).
    slices: list[tuple[Image.Image, Optional[tuple[int, int, int, int]]]] = []
    for i in range(frame_count):
        left = i * slice_w
        right = sheet_w if i == frame_count - 1 else (i + 1) * slice_w
        slice_img = src.crop((left, 0, right, sheet_h))
        slices.append((slice_img, slice_img.getbbox()))

    # Compute the shared scale: fit the LARGEST subject into the inner 80%
    # window. All other slices scale at the SAME factor, preserving
    # relative size across frames.
    max_dim = 1
    for _, bbox in slices:
        if bbox is None:
            continue
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_dim = max(max_dim, w, h)
    inner = max(1, int(round(tile_size * (1 - 2 * AUTOCENTER_PADDING_FRAC))))
    shared_scale = inner / max_dim

    # Pass 2: crop each slice to its subject, scale with the shared factor,
    # center on a transparent tile canvas.
    tiles: list[bytes] = []
    for slice_img, bbox in slices:
        canvas = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
        if bbox is None:
            buf = io.BytesIO()
            canvas.save(buf, format="PNG")
            tiles.append(buf.getvalue())
            continue
        cropped = slice_img.crop(bbox)
        cw, ch = cropped.size
        new_w = max(1, int(round(cw * shared_scale)))
        new_h = max(1, int(round(ch * shared_scale)))
        scaled = cropped.resize((new_w, new_h), Image.LANCZOS)
        x = (tile_size - new_w) // 2
        y = (tile_size - new_h) // 2
        canvas.paste(scaled, (x, y))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        tiles.append(buf.getvalue())
    return tiles


def _build_pose_sheet_prompt(
    *,
    subject: str,
    template: tuple[str, ...],
    frame_count: int,
    style_hint: str = "",
) -> str:
    """Build the one-shot prompt asking Gemini to draw all ``frame_count``
    poses as a single horizontal sprite sheet. Giving Gemini the whole
    sequence in one composition is what makes character design, palette,
    scale, and background consistent across frames — per-frame calls
    couldn't deliver that no matter how strongly we prompted."""
    pose_lines = "\n".join(
        f"  Frame {i + 1}: {template[i % len(template)]}"
        for i in range(frame_count)
    )
    style_clause = f" Style: {style_hint.strip()}." if style_hint.strip() else ""
    return (
        f"Generate a pixel-art SPRITE SHEET as a SINGLE IMAGE containing "
        f"{frame_count} frames arranged HORIZONTALLY in a strip, left to "
        f"right, equally spaced on one continuous transparent row.\n\n"
        f"Each frame shows: {subject.strip()}.{style_clause}\n\n"
        f"The {frame_count} frames, in order:\n{pose_lines}\n\n"
        f"CRITICAL RULES:\n"
        f"- Every frame MUST show the EXACT same character — identical "
        f"head shape, body proportions, color palette, markings, "
        f"silhouette, and overall size. Only the pose changes.\n"
        f"- All {frame_count} frames MUST be at the exact same scale "
        f"and vertically aligned on a shared baseline.\n"
        f"- BACKGROUND: fill the entire sheet with SOLID BRIGHT MAGENTA "
        f"(RGB 255, 0, 255 / hex #ff00ff) as a flat solid color. DO NOT "
        f"draw a checkerboard transparency pattern. DO NOT use any "
        f"other background color. The subject itself must NOT contain "
        f"magenta — use completely different colors for the character.\n"
        f"- STRICT: the character exists ALONE on the magenta. "
        f"ABSOLUTELY NOTHING ELSE. Specifically forbidden in every "
        f"frame: NO ground, floor, dirt, path, platform, tile, or "
        f"surface of any kind under the character; NO shadow; NO dust, "
        f"smoke, sparks, particles, or effect indicators; NO motion "
        f"lines, speed marks, action arrows, or trajectory hints; "
        f"NO borders, frames, or boxes around poses.\n"
        f"- No horizontal dividers, frame borders, numbering, labels, "
        f"or gaps between poses — just the character poses on the "
        f"continuous magenta strip.\n"
        f"- No text, no UI, no watermark, no caption, no logos."
    )


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
        # Static path: single call, chroma-key, autocenter, done.
        full_prompt = _build_prompt(subject=prompt, style_hint=style_hint)
        raw = _generate_frame(prompt=full_prompt)
        keyed = _chroma_key_to_transparent(raw)
        frames.append(_autocenter_frame(keyed, tile_size))
    else:
        # Animated path: one-shot pose sheet + chroma-key + slice +
        # shared-scale center. A single Gemini call produces all N
        # poses in one composition, so character design / palette /
        # scale are consistent by construction. Chroma-key strips the
        # magenta fill we asked for as a background, converting it to
        # real alpha=0 transparency before slicing so each tile's
        # bbox detection sees only the subject.
        template = MOTION_TEMPLATES[motion]
        sheet_prompt = _build_pose_sheet_prompt(
            subject=prompt,
            template=template,
            frame_count=frame_count,
            style_hint=style_hint,
        )
        sheet_bytes = _generate_frame(prompt=sheet_prompt)
        keyed_sheet = _chroma_key_to_transparent(sheet_bytes)
        frames = _slice_and_center_sheet(keyed_sheet, frame_count, tile_size)

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
