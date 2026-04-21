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

import requests
from PIL import Image, UnidentifiedImageError
from django.conf import settings

from apps.accounts.models import User
from apps.rpg import sprite_authoring as svc
from apps.rpg.sprite_authoring import SpriteAuthoringError


MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB — plenty for any sprite PNG


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
# Disney/2D-game animation technique.
#
# v1.2.3: each phase explicitly forbids rotation because v1.2.2's
# "subject changes shape between frames" got pattern-matched to
# "coin flipping" — a rotation animation where the coin appears at
# different viewing angles across frames. The "face-on view never
# changes" language in every phase blocks that re-interpretation.
BOUNCE_CYCLE_TEMPLATE = (
    "neutral rest pose: subject at its natural resting shape and "
    "proportions, stationary in the exact center of the frame. The "
    "same face of the subject points straight at the viewer. This is "
    "the reference shape the other frames deform away from",
    "DRAMATIC anticipation squash: subject compressed vertically into "
    "a MARKEDLY WIDER-AND-SHORTER shape — approximately 30% shorter "
    "and 20% wider than the rest pose. This shape difference MUST be "
    "CLEARLY VISIBLE at a glance, not subtle. The subject stays "
    "stationary in the EXACT same frame position — do not shift it up, "
    "down, left, or right, and do NOT rotate, flip, spin, or turn it. "
    "The same face of the subject still points straight at the viewer. "
    "NOTE: the 'small incremental deltas' rule does NOT apply to this "
    "motion — squash-and-stretch REQUIRES visibly different proportions "
    "between keyframes",
    "DRAMATIC stretch release: subject stretched vertically into a "
    "MARKEDLY TALLER-AND-THINNER shape — approximately 30% taller and "
    "20% narrower than the rest pose. This shape difference MUST be "
    "CLEARLY VISIBLE at a glance, not subtle. The subject stays "
    "stationary in the EXACT same frame position and the SAME face "
    "still points at the viewer — do NOT rotate the subject, do NOT "
    "show it edge-on or from the side, do NOT tilt it. NOTE: the "
    "'small incremental deltas' rule does NOT apply to this motion",
    "recovery ease: subject returning toward normal proportions — "
    "roughly halfway between the stretch pose and the rest pose. Same "
    "frame position, same face-on viewing angle, easing back to the "
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
    "STRICT: the subject is the ONLY ENTITY in the frame. ABSOLUTELY "
    "NOTHING ELSE. Specifically forbidden: NO ground, floor, dirt, path, "
    "platform, tile, slab, pedestal, stand, or surface of any kind under "
    "the subject; NO shadow; NO dust, smoke, sparks, particles, or effect "
    "indicators; NO motion lines, speed marks, action arrows, or trajectory "
    "hints; NO borders, frames, boxes, or scene elements; NO second "
    "creatures, pets, companions, riders, or NPCs; NO furniture, beds, "
    "cushions, pillows, blankets, mats, or props; NO buildings, walls, "
    "fences, trees, plants, or terrain features; NO floating objects or "
    "panels above, below, or beside the subject; NO text, labels, numbers, "
    "captions, watermarks, logos, or UI. The character exists alone in "
    "empty space on solid magenta. Nothing else is in the frame. "
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


def _fetch_reference_image(url: str) -> bytes:
    """Download an image URL for use as a Gemini reference. Validates
    content type and size. Raises ``SpriteGenerationError`` on any
    failure so the caller can surface a single clean error class."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise SpriteGenerationError(
            f"failed to fetch reference image at {url!r}: {exc}",
        )
    ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if ctype not in ("image/png", "image/webp", "image/jpeg"):
        raise SpriteGenerationError(
            f"reference image Content-Type {ctype!r} not accepted; "
            f"expected image/png, image/webp, or image/jpeg",
        )
    if len(resp.content) > MAX_REFERENCE_IMAGE_BYTES:
        raise SpriteGenerationError(
            f"reference image exceeds {MAX_REFERENCE_IMAGE_BYTES} bytes",
        )
    return resp.content


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


def _keep_largest_component(png_bytes: bytes) -> bytes:
    """Keep only the largest connected opaque region; zero-alpha everything
    else. Used to scrub chroma-key fringe orphans and cross-cell bleed
    fragments that would otherwise flash as "cut-off portions from another
    frame" during animation. For our subjects (foxes, coins, items) the
    character is always a single connected blob, so this is safe. If we
    ever get multi-blob subjects we'd switch to a size-threshold variant.
    """
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteGenerationError(f"orphan-cleanup got an invalid image: {exc}")

    w, h = img.size
    pix = img.load()
    seen = [[False] * h for _ in range(w)]
    components: list[list[tuple[int, int]]] = []

    for sx in range(w):
        for sy in range(h):
            if seen[sx][sy] or pix[sx, sy][3] == 0:
                continue
            # BFS over 4-connected opaque neighborhood.
            stack = [(sx, sy)]
            comp: list[tuple[int, int]] = []
            seen[sx][sy] = True
            while stack:
                cx, cy = stack.pop()
                comp.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if (
                        0 <= nx < w and 0 <= ny < h
                        and not seen[nx][ny]
                        and pix[nx, ny][3] > 0
                    ):
                        seen[nx][ny] = True
                        stack.append((nx, ny))
            components.append(comp)

    if not components:
        # Nothing to prune; return the input unchanged (already transparent).
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    largest = max(components, key=len)
    keep = set(largest)
    new_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    new_pix = new_img.load()
    for px, py in keep:
        new_pix[px, py] = pix[px, py]

    out = io.BytesIO()
    new_img.save(out, format="PNG")
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


def _slice_and_ground_align_sheet(
    sheet_png: bytes,
    frame_count: int,
    tile_size: int,
) -> list[bytes]:
    """Slice a single Gemini-generated pose sheet into ``frame_count`` equal
    horizontal tiles, scale with a SHARED factor, then GROUND-ALIGN each
    tile's subject to a shared baseline near the tile's bottom.

    Ground-align is what classic hand-drawn sprite cycles use: the
    character's feet stay planted on one ground line across every frame,
    and variations in body height (walk-cycle passing poses rise, contact
    poses fall; squash-stretch bounce's top edge oscillates) show up as
    the subject's TOP being at different Y positions across frames. That
    subtle bob IS the perceived animation motion. v1.2.4's vertical-
    centering normalized every subject's bbox to the tile's midline,
    erasing the bob and producing the 'slideshow' feel across all
    motion types.

    Horizontal positioning is still centered. Shared-scale logic is
    unchanged — the largest subject's max dimension fills the tile's
    inner 80% window and everything else scales proportionally. Only
    the vertical placement rule differs.
    """
    try:
        src = Image.open(io.BytesIO(sheet_png)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteGenerationError(f"Gemini returned an invalid image: {exc}")

    sheet_w, sheet_h = src.size
    slice_w = sheet_w // frame_count

    # Pass 1: slice the sheet and record each subject's bbox.
    slices: list[tuple[Image.Image, Optional[tuple[int, int, int, int]]]] = []
    for i in range(frame_count):
        left = i * slice_w
        right = sheet_w if i == frame_count - 1 else (i + 1) * slice_w
        slice_img = src.crop((left, 0, right, sheet_h))
        slices.append((slice_img, slice_img.getbbox()))

    # Shared scale: fit the LARGEST subject into the inner 80% window.
    max_dim = 1
    for _, bbox in slices:
        if bbox is None:
            continue
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_dim = max(max_dim, w, h)
    inner = max(1, int(round(tile_size * (1 - 2 * AUTOCENTER_PADDING_FRAC))))
    shared_scale = inner / max_dim

    # Ground baseline: subject bottoms land at this Y in the tile. Matches
    # the top padding so every tile has equal transparent margin top and
    # bottom when the subject is tall; shorter subjects leave more empty
    # space ABOVE (which is the bob).
    padding_px = max(1, int(round(tile_size * AUTOCENTER_PADDING_FRAC)))
    baseline_y = tile_size - padding_px

    # Pass 2: crop to bbox, scale with shared factor, ground-align.
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
        # Horizontal: centered. Vertical: subject bottom at shared baseline.
        x = (tile_size - new_w) // 2
        y = baseline_y - new_h
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
    has_reference: bool = False,
) -> str:
    """Build the one-shot prompt asking Gemini to draw all ``frame_count``
    poses as a single horizontal sprite sheet. Giving Gemini the whole
    sequence in one composition is what makes character design, palette,
    scale, and background consistent across frames — per-frame calls
    couldn't deliver that no matter how strongly we prompted.

    When ``has_reference`` is True, the prompt tells Gemini to use the
    reference image (passed alongside) as the authoritative source for
    character appearance — the text prompt only describes motion."""
    pose_lines = "\n".join(
        f"  Frame {i + 1}: {template[i % len(template)]}"
        for i in range(frame_count)
    )
    style_clause = f" Style: {style_hint.strip()}." if style_hint.strip() else ""
    reference_clause = (
        "Every frame MUST depict the EXACT SAME CHARACTER shown in the "
        "REFERENCE IMAGE provided — same character design, same head "
        "shape, same body proportions, same color palette, same outline "
        "style, same pixel-art treatment. The text description below is "
        "supplementary; the reference image is the authoritative source "
        "for what the character looks like. Do NOT redesign or recolor.\n\n"
        if has_reference
        else ""
    )
    return (
        f"Generate a pixel-art SPRITE SHEET as a SINGLE IMAGE containing "
        f"{frame_count} frames arranged HORIZONTALLY in a strip, left to "
        f"right, equally spaced on one continuous transparent row.\n\n"
        f"{reference_clause}"
        f"Each frame shows: {subject.strip()}.{style_clause}\n\n"
        f"This is ONE animation cycle broken into {frame_count} "
        f"SEQUENTIAL KEYFRAMES. Each frame is a SMALL incremental step "
        f"in a continuous flowing motion — NOT an independent pose. "
        f"The differences between adjacent frames must be small: "
        f"frame N+1 should look like the natural continuation of frame "
        f"N with only a modest pose delta. Frames must INTERLOCK like "
        f"classic hand-drawn pixel-art sprite sheets (Stardew Valley, "
        f"Pokémon, Zelda: A Link to the Past) — each frame is a moment "
        f"in flowing motion, not a separate standalone drawing. "
        f"Frame {frame_count} must flow naturally back into frame 1 so "
        f"the loop plays seamlessly.\n\n"
        f"The {frame_count} frames, in sequential order:\n{pose_lines}\n\n"
        f"CRITICAL RULES:\n"
        f"- Every frame MUST show the EXACT same character — identical "
        f"head shape, body proportions, color palette, markings, "
        f"silhouette, and overall size. Only the pose changes.\n"
        f"- Adjacent-frame pose deltas must be SMALL and INCREMENTAL "
        f"— roughly what a human animator would call a tween keyframe. "
        f"If a pose change would look jarring when played at animation "
        f"speed, the change is too large.\n"
        f"- The subject's viewing angle and orientation NEVER change "
        f"across frames. Do NOT rotate, flip, spin, turn, or tilt the "
        f"subject between poses. The same face of the subject points "
        f"at the viewer in every single frame. Never show the subject "
        f"edge-on, from the side when the rest pose is front-on, or "
        f"at any angle different from the other frames.\n"
        f"- All {frame_count} frames MUST be at the exact same scale "
        f"and vertically aligned on a shared baseline.\n"
        f"- BACKGROUND: fill the entire sheet with SOLID BRIGHT MAGENTA "
        f"(RGB 255, 0, 255 / hex #ff00ff) as a flat solid color. DO NOT "
        f"draw a checkerboard transparency pattern. DO NOT use any "
        f"other background color. The subject itself must NOT contain "
        f"magenta — use completely different colors for the character.\n"
        f"- STRICT: the character is the ONLY ENTITY in each frame. "
        f"ABSOLUTELY NOTHING ELSE. Specifically forbidden in every "
        f"frame: NO ground, floor, dirt, path, platform, tile, slab, "
        f"pedestal, stand, or surface of any kind under the character; "
        f"NO shadow; NO dust, smoke, sparks, particles, or effect "
        f"indicators; NO motion lines, speed marks, action arrows, or "
        f"trajectory hints; NO borders, frames, or boxes around poses; "
        f"NO second creatures, pets, companions, riders, or NPCs; "
        f"NO furniture, beds, cushions, pillows, blankets, mats, "
        f"or props; NO buildings, walls, fences, trees, plants, or "
        f"terrain features; NO floating objects or panels above, "
        f"below, or beside the character. The character exists alone "
        f"in empty space on solid magenta. Nothing else is in the frame.\n"
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


REFERENCE_IMAGE_CLAUSE = (
    " A REFERENCE IMAGE is provided. The subject in the output MUST be "
    "VISUALLY IDENTICAL to the character shown in the reference image — "
    "same character design, same head shape, same body proportions, same "
    "color palette, same outline style, same pixel-art treatment, same "
    "level of detail. Do NOT redesign the character. Do NOT change its "
    "colors. Use the reference image as the authoritative source for "
    "what the subject looks like; use the text prompt only to describe "
    "any pose/motion changes requested. If text prompt and reference "
    "image conflict on character appearance, the reference wins."
)


def _build_prompt(
    *,
    subject: str,
    style_hint: str = "",
    frame_note: str = "",
    has_reference: bool = False,
) -> str:
    parts = [subject.strip()]
    if style_hint.strip():
        parts.append(style_hint.strip())
    if frame_note:
        parts.append(frame_note)
    base = ". ".join(p for p in parts if p) + "." + PROMPT_SUFFIX
    if has_reference:
        base += REFERENCE_IMAGE_CLAUSE
    return base


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
    reference_image_url: Optional[str] = None,
    overwrite: bool = False,
    actor: Optional[User] = None,
) -> dict[str, Any]:
    """Generate a sprite (static or animated) from a text prompt.

    Returns the same dict shape as ``sprite_authoring.register_sprite`` so
    callers can treat it as drop-in. ``motion`` picks the 4-phase
    template used for animated strips (see ``MOTION_TEMPLATES``) — it's
    silently ignored when ``frame_count == 1``.

    When ``reference_image_url`` is provided, the service downloads that
    URL's bytes and passes them to Gemini alongside the text prompt as
    a style + character anchor. The generated sprite then matches the
    reference image's character design, palette, and pixel-art style.
    Enables the self-anchored bulk-animation workflow: pass an
    existing static sprite's URL to produce an animated version with
    identical visual treatment.
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

    # When a reference image is provided, download it up front. Any
    # fetch failure raises before we spend a Gemini call.
    ref_bytes: Optional[bytes] = None
    if reference_image_url:
        ref_bytes = _fetch_reference_image(reference_image_url)

    frames: list[bytes] = []
    if frame_count == 1:
        # Static path: single call, chroma-key, autocenter, prune orphans.
        full_prompt = _build_prompt(
            subject=prompt,
            style_hint=style_hint,
            has_reference=ref_bytes is not None,
        )
        raw = _generate_frame(prompt=full_prompt, reference_png=ref_bytes)
        keyed = _chroma_key_to_transparent(raw)
        centered = _autocenter_frame(keyed, tile_size)
        frames.append(_keep_largest_component(centered))
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
            has_reference=ref_bytes is not None,
        )
        sheet_bytes = _generate_frame(prompt=sheet_prompt, reference_png=ref_bytes)
        keyed_sheet = _chroma_key_to_transparent(sheet_bytes)
        aligned_tiles = _slice_and_ground_align_sheet(keyed_sheet, frame_count, tile_size)
        # Per-tile orphan cleanup: chroma-key anti-alias fringes and any
        # cross-cell bleed fragments get filtered here, so each tile
        # contains only its single largest connected subject.
        frames = [_keep_largest_component(t) for t in aligned_tiles]

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
