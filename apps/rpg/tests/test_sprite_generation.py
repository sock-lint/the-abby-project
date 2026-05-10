"""Tests for sprite_generation (text → Gemini → sprite sheet).

Gemini is mocked at the single ``_generate_frame`` seam so no real API
traffic fires in tests and the ``google-genai`` package need not be
installed for this test module to pass.
"""
import io
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_generation import (
    SpriteGenerationError,
    _autocenter_frame,
    _chroma_key_to_transparent,
    _extract_png_bytes,
    _keep_largest_component,
    generate_sprite_sheet,
)


def _png_bytes(size=(128, 128), color=(200, 50, 50, 255)):
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@override_settings(GEMINI_API_KEY="test-key")
class StaticSpriteGenerationTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p1", password="pw", role="parent")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_static_frame_persists_as_single_sprite(self, mock_frame):
        mock_frame.return_value = _png_bytes(size=(512, 512))

        result = generate_sprite_sheet(
            slug="fox-sit",
            prompt="pixel-art red fox sitting",
            frame_count=1,
            tile_size=64,
            fps=0,
            actor=self.parent,
        )

        self.assertEqual(result["slug"], "fox-sit")
        self.assertEqual(result["frame_count"], 1)
        self.assertEqual(result["fps"], 0)
        self.assertEqual(result["frame_width_px"], 64)
        self.assertEqual(result["frame_height_px"], 64)
        self.assertEqual(mock_frame.call_count, 1)
        self.assertIsNone(mock_frame.call_args.kwargs.get("reference_png"))
        self.assertIn(
            "pixel-art red fox sitting",
            mock_frame.call_args.kwargs["prompt"],
        )
        self.assertTrue(SpriteAsset.objects.filter(slug="fox-sit").exists())

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_style_hint_injected_into_prompt(self, mock_frame):
        mock_frame.return_value = _png_bytes(size=(256, 256))

        generate_sprite_sheet(
            slug="styled",
            prompt="a wolf",
            frame_count=1,
            tile_size=64,
            fps=0,
            style_hint="gameboy palette, 4-color",
            actor=self.parent,
        )

        prompt = mock_frame.call_args.kwargs["prompt"]
        self.assertIn("a wolf", prompt)
        self.assertIn("gameboy palette", prompt)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_authoring_inputs_persist_for_reroll(self, mock_frame):
        """The generation service must write prompt/motion/style_hint/tile_size
        back onto SpriteAsset so a future reroll can replay those inputs.
        """
        mock_frame.return_value = _png_bytes(size=(256, 256))

        generate_sprite_sheet(
            slug="archivable",
            prompt="a stoic gargoyle",
            frame_count=1,
            tile_size=64,
            fps=0,
            style_hint="dark stone, moss tint",
            motion="idle",
            actor=self.parent,
        )

        asset = SpriteAsset.objects.get(slug="archivable")
        self.assertEqual(asset.prompt, "a stoic gargoyle")
        self.assertEqual(asset.style_hint, "dark stone, moss tint")
        self.assertEqual(asset.motion, "idle")
        self.assertEqual(asset.tile_size, 64)
        self.assertEqual(asset.reference_image_url, "")
        # Default when caller doesn't pass one — empty string, not NULL.
        self.assertEqual(asset.original_intent, "")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_original_intent_persists_for_reroll(self, mock_frame):
        """When the caller passes original_intent, the generation
        service writes it onto SpriteAsset alongside the refined prompt
        so a future reroll can re-refine from the same starting point."""
        mock_frame.return_value = _png_bytes(size=(256, 256))

        generate_sprite_sheet(
            slug="intent-roundtrip",
            prompt="pixel-art red fox sleeping curled in a comma shape",
            frame_count=1,
            tile_size=64,
            fps=0,
            original_intent="a sleeping fox curled up like a comma",
            actor=self.parent,
        )

        asset = SpriteAsset.objects.get(slug="intent-roundtrip")
        self.assertEqual(asset.original_intent, "a sleeping fox curled up like a comma")
        # Refined prompt is independent of the intent — both persist.
        self.assertEqual(
            asset.prompt,
            "pixel-art red fox sleeping curled in a comma shape",
        )


@override_settings(GEMINI_API_KEY="test-key")
class AnimatedSheetOutputShapeTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p2", password="pw", role="parent")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_4_frame_sheet_stitches_to_256x64_strip(self, mock_frame):
        # Gemini returns one 4-cell horizontal sheet (1024×256 is a typical
        # Gemini image output size). Each cell has a centered subject.
        def _sheet():
            sheet = Image.new("RGBA", (1024, 256), (0, 0, 0, 0))
            for i in range(4):
                subject = Image.new("RGBA", (180, 180), (180, 60, 60, 255))
                sheet.paste(subject, (i * 256 + 38, 38))
            buf = io.BytesIO()
            sheet.save(buf, format="PNG")
            return buf.getvalue()

        mock_frame.return_value = _sheet()

        result = generate_sprite_sheet(
            slug="fox-walk",
            prompt="pixel-art red fox walking side view",
            frame_count=4,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )

        self.assertEqual(result["frame_count"], 4)
        self.assertEqual(result["fps"], 8)
        self.assertEqual(result["frame_width_px"], 64)
        self.assertEqual(result["frame_height_px"], 64)
        self.assertEqual(result["frame_layout"], "horizontal")

        row = SpriteAsset.objects.get(slug="fox-walk")
        with row.image.open("rb") as fh:
            img = Image.open(fh)
            img.load()
        self.assertEqual(img.width, 256)
        self.assertEqual(img.height, 64)


@override_settings(GEMINI_API_KEY="test-key")
class SpriteGenerationErrorSurfaceTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p3", password="pw", role="parent")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_api_failure_rolls_back_cleanly(self, mock_frame):
        mock_frame.side_effect = SpriteGenerationError("upstream API down")

        with self.assertRaises(SpriteGenerationError):
            generate_sprite_sheet(
                slug="aborted",
                prompt="pixel-art fox",
                frame_count=4,
                tile_size=64,
                fps=8,
                actor=self.parent,
            )
        self.assertFalse(SpriteAsset.objects.filter(slug="aborted").exists())

    def test_frame_count_over_cap_raises_before_api(self):
        with patch("apps.rpg.sprite_generation._generate_frame") as mock_frame:
            with self.assertRaises(SpriteGenerationError):
                generate_sprite_sheet(
                    slug="x",
                    prompt="a",
                    frame_count=99,
                    tile_size=64,
                    fps=8,
                    actor=self.parent,
                )
            mock_frame.assert_not_called()

    @override_settings(SPRITE_GENERATION_MAX_FRAMES=2)
    def test_honors_configured_max(self):
        with patch("apps.rpg.sprite_generation._generate_frame") as mock_frame:
            with self.assertRaises(SpriteGenerationError):
                generate_sprite_sheet(
                    slug="x",
                    prompt="a",
                    frame_count=3,
                    tile_size=64,
                    fps=8,
                    actor=self.parent,
                )
            mock_frame.assert_not_called()

    def test_animated_with_zero_fps_raises_before_api(self):
        with patch("apps.rpg.sprite_generation._generate_frame") as mock_frame:
            with self.assertRaises(SpriteGenerationError):
                generate_sprite_sheet(
                    slug="x",
                    prompt="a",
                    frame_count=4,
                    tile_size=64,
                    fps=0,
                    actor=self.parent,
                )
            mock_frame.assert_not_called()


@override_settings(GEMINI_API_KEY="")
class MissingApiKeyTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p4", password="pw", role="parent")

    def test_missing_key_raises_clear_error(self):
        with self.assertRaises(SpriteGenerationError) as ctx:
            generate_sprite_sheet(
                slug="x",
                prompt="a",
                frame_count=1,
                tile_size=64,
                fps=0,
                actor=self.parent,
            )
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


class KeepLargestComponentTests(TestCase):
    """Chroma-key leaves small near-magenta pixels opaque at anti-alias
    edges; equal-width slicing can also drag cross-cell fragments into
    a tile. Both show as "cut off portions from another frame" during
    animation — ghosts that flash briefly. Connected-components
    filtering keeps only the largest opaque cluster per tile, which
    for our subjects (foxes, coins, items) is always the actual
    character. Orphan clusters get alpha=0."""

    def _png(self, w, h, opaque_regions):
        """Build a PNG with ``opaque_regions`` = list of (x, y, w, h) rects
        to paint as opaque red on an otherwise transparent canvas."""
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for x, y, rw, rh in opaque_regions:
            subject = Image.new("RGBA", (rw, rh), (200, 50, 50, 255))
            img.paste(subject, (x, y))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_single_large_component_passes_through_unchanged(self):
        # A single 30x30 subject with no orphans — nothing to remove.
        png = self._png(64, 64, [(10, 10, 30, 30)])
        out = _keep_largest_component(png)
        before = Image.open(io.BytesIO(png)).convert("RGBA")
        after = Image.open(io.BytesIO(out)).convert("RGBA")
        # Same opaque-pixel count (the whole subject is one component).
        before_opaque = sum(1 for p in before.getdata() if p[3] > 0)
        after_opaque = sum(1 for p in after.getdata() if p[3] > 0)
        self.assertEqual(before_opaque, after_opaque)
        self.assertEqual(before_opaque, 30 * 30)

    def test_large_subject_plus_small_orphans_removes_orphans(self):
        # 30x30 main subject + three small orphan clusters.
        png = self._png(64, 64, [
            (15, 15, 30, 30),   # main subject: 900 pixels
            (0, 0, 3, 3),       # orphan 1: 9 pixels
            (60, 0, 2, 2),      # orphan 2: 4 pixels
            (0, 62, 1, 1),      # orphan 3: 1 pixel
        ])
        out = _keep_largest_component(png)
        after = Image.open(io.BytesIO(out)).convert("RGBA")
        after_opaque = sum(1 for p in after.getdata() if p[3] > 0)
        # Only the main subject (900 pixels) should remain.
        self.assertEqual(after_opaque, 900)
        # Verify the orphan regions are now transparent.
        self.assertEqual(after.getpixel((0, 0))[3], 0)
        self.assertEqual(after.getpixel((60, 0))[3], 0)
        self.assertEqual(after.getpixel((0, 62))[3], 0)
        # And the main subject is still there.
        self.assertEqual(after.getpixel((20, 20))[3], 255)

    def test_fully_transparent_input_passes_through(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out = _keep_largest_component(buf.getvalue())
        after = Image.open(io.BytesIO(out)).convert("RGBA")
        self.assertEqual(after.size, (64, 64))
        self.assertIsNone(after.getbbox())

    def test_invalid_image_raises(self):
        with self.assertRaises(SpriteGenerationError):
            _keep_largest_component(b"not a png")

    def test_orphan_bigger_than_half_main_still_gets_removed(self):
        """Edge case: even a sizeable orphan (smaller than main but not
        tiny) still gets removed. Catches the real bounce v1.2.5 case
        where a 168-pixel orphan appeared alongside a 956-pixel main."""
        # Non-overlapping coords: main is rows 10-49, cols 10-49;
        # orphan is rows 0-20, cols 0-7 (gap of 2 rows and 2 cols
        # between them so BFS treats them as separate components).
        png = self._png(64, 64, [
            (10, 10, 40, 40),   # main: 1600 pixels
            (0, 0, 8, 21),      # orphan: 8 × 21 = 168 pixels
        ])
        out = _keep_largest_component(png)
        after = Image.open(io.BytesIO(out)).convert("RGBA")
        after_opaque = sum(1 for p in after.getdata() if p[3] > 0)
        self.assertEqual(after_opaque, 1600)
        # Orphan pixels are now transparent.
        self.assertEqual(after.getpixel((0, 0))[3], 0)
        self.assertEqual(after.getpixel((5, 10))[3], 0)


class ChromaKeyTests(TestCase):
    """Image models trained on web-scraped screenshots often draw the
    Photoshop/Figma transparency CHECKERBOARD when asked for
    'transparent background' — they've pattern-matched the visual
    indicator of transparency as if it were transparency itself. We
    work around this by prompting Gemini for SOLID MAGENTA
    (RGB 255, 0, 255) and chroma-keying that color to real alpha=0
    pixels after the fact. Magenta is the classic game-dev chroma-key
    color because it essentially never appears in real subjects.
    """

    def _png_with_pixels(self, w, h, pixels_rgba):
        """Build a PNG with the given (width*h) flat list of RGBA tuples."""
        img = Image.new("RGBA", (w, h))
        img.putdata(pixels_rgba)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_pure_magenta_becomes_transparent(self):
        # 2×1 image: [magenta, red]
        png = self._png_with_pixels(2, 1, [
            (255, 0, 255, 255),
            (200, 50, 50, 255),
        ])
        out = _chroma_key_to_transparent(png)
        result = list(Image.open(io.BytesIO(out)).getdata())
        self.assertEqual(result[0][3], 0)  # magenta → alpha 0
        self.assertEqual(result[1][3], 255)  # red → alpha preserved

    def test_non_magenta_subject_pixels_preserved(self):
        # A pixel that is NOT magenta — common subject colors.
        png = self._png_with_pixels(4, 1, [
            (255, 0, 0, 255),    # red
            (0, 255, 0, 255),    # green
            (0, 0, 255, 255),    # blue
            (255, 255, 0, 255),  # yellow
        ])
        out = _chroma_key_to_transparent(png)
        result = list(Image.open(io.BytesIO(out)).getdata())
        for pixel in result:
            self.assertEqual(pixel[3], 255, f"subject pixel {pixel} got keyed out")

    def test_near_magenta_within_tolerance_is_keyed(self):
        # Anti-aliased edges blend toward magenta. These should also
        # be caught by the chroma-key so we don't get purple halos.
        png = self._png_with_pixels(3, 1, [
            (250, 20, 250, 255),  # near-magenta (anti-alias fringe)
            (230, 40, 230, 255),  # slightly further
            (100, 100, 100, 255),  # gray (NOT magenta) — must stay opaque
        ])
        out = _chroma_key_to_transparent(png)
        result = list(Image.open(io.BytesIO(out)).getdata())
        self.assertEqual(result[0][3], 0)    # near-magenta → transparent
        self.assertEqual(result[1][3], 0)    # fringe → transparent
        self.assertEqual(result[2][3], 255)  # gray → preserved

    def test_already_transparent_pixels_stay_transparent(self):
        # If a pixel was already alpha=0, chroma-key leaves it alone.
        png = self._png_with_pixels(2, 1, [
            (0, 0, 0, 0),        # fully transparent (color doesn't matter)
            (100, 100, 100, 255),  # gray opaque
        ])
        out = _chroma_key_to_transparent(png)
        result = list(Image.open(io.BytesIO(out)).getdata())
        self.assertEqual(result[0][3], 0)
        self.assertEqual(result[1][3], 255)

    def test_invalid_image_raises(self):
        with self.assertRaises(SpriteGenerationError):
            _chroma_key_to_transparent(b"not a png")


@override_settings(GEMINI_API_KEY="test-key")
class ChromaKeyIntegrationTests(TestCase):
    """Verify the chroma-key runs as part of generate_sprite_sheet's
    pipeline, not only as a standalone function."""

    def setUp(self):
        self.parent = User.objects.create_user(username="p_chroma", password="pw", role="parent")

    def _magenta_sheet_with_subject(self, frame_count=4):
        """Build a sheet where each slice is filled with magenta, with
        a single red subject rect in each cell. After chroma-key, the
        magenta should become transparent, leaving just the red subject
        — then autocenter can do its job properly."""
        sheet = Image.new("RGBA", (256 * frame_count, 256), (255, 0, 255, 255))
        for i in range(frame_count):
            subject = Image.new("RGBA", (100, 100), (200, 50, 50, 255))
            x = i * 256 + (256 - 100) // 2
            y = (256 - 100) // 2
            sheet.paste(subject, (x, y))
        buf = io.BytesIO()
        sheet.save(buf, format="PNG")
        return buf.getvalue()

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_magenta_background_is_stripped_before_slicing(self, mock_frame):
        """The whole point of v1.2.1: magenta fill from Gemini becomes
        alpha=0, so bbox detection sees only the red subject — not
        the full magenta cell."""
        mock_frame.return_value = self._magenta_sheet_with_subject(4)

        generate_sprite_sheet(
            slug="chroma-check",
            prompt="pixel-art red fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )

        # Read the stored strip and check each tile:
        # - Should have transparent areas (no magenta fill bleeding through)
        # - Subject bbox in each tile should be ~ 80% of the 64 tile
        #   (because autocenter scales the 100×100 subject to fit)
        row = SpriteAsset.objects.get(slug="chroma-check")
        with row.image.open("rb") as fh:
            strip = Image.open(fh)
            strip.load()

        # Scan tile 0's pixels — there should be NO magenta visible.
        tile = strip.crop((0, 0, 64, 64))
        data = list(tile.getdata())
        magenta_pixels = [p for p in data if p[0] > 200 and p[1] < 60 and p[2] > 200 and p[3] > 0]
        self.assertEqual(
            len(magenta_pixels), 0,
            f"found {len(magenta_pixels)} magenta pixels — chroma-key didn't run",
        )

        # And the subject bbox should fit the inner ~80% window.
        bbox = tile.getbbox()
        self.assertIsNotNone(bbox)
        max_dim = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
        self.assertGreaterEqual(max_dim, 48)
        self.assertLessEqual(max_dim, 56)


class ExtractPngBytesTests(TestCase):
    def test_missing_inline_data_raises(self):
        empty = SimpleNamespace(candidates=[])
        with self.assertRaises(SpriteGenerationError):
            _extract_png_bytes(empty)

    def test_extracts_first_inline_data_payload(self):
        inline = SimpleNamespace(data=b"fake-png-bytes", mime_type="image/png")
        part = SimpleNamespace(inline_data=inline)
        content = SimpleNamespace(parts=[part])
        candidate = SimpleNamespace(content=content)
        resp = SimpleNamespace(candidates=[candidate])
        self.assertEqual(_extract_png_bytes(resp), b"fake-png-bytes")


class AutocenterFrameTests(TestCase):
    """Deterministic post-processing that fixes off-centered Gemini output.

    Finds the subject's alpha bounding box, scales it to fit inside the
    tile with ~10% padding on each side, and pastes onto a transparent
    canvas. This runs on every frame before it's used as a reference
    for the next call, so iterative generation gets a normalized
    reference position and Gemini doesn't drift across frames.
    """

    def _png(self, size, subject_rect, color=(255, 0, 0, 255)):
        """Build a PNG where a subject rect is filled; rest is transparent."""
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        subject = Image.new("RGBA", (subject_rect[2], subject_rect[3]), color)
        img.paste(subject, (subject_rect[0], subject_rect[1]))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_output_is_tile_sized(self):
        png = self._png((256, 256), (10, 10, 64, 64))
        result = _autocenter_frame(png, tile_size=64)
        out = Image.open(io.BytesIO(result))
        self.assertEqual(out.size, (64, 64))

    def test_off_center_subject_gets_centered(self):
        # Subject in top-left quadrant only — heavily off-center.
        png = self._png((256, 256), (0, 0, 80, 80))
        result = _autocenter_frame(png, tile_size=64)
        out = Image.open(io.BytesIO(result))

        bbox = out.getbbox()
        self.assertIsNotNone(bbox)
        left, top, right, bottom = bbox
        subject_w = right - left
        subject_h = bottom - top
        # Left padding should equal right padding (within 1px rounding),
        # same for top/bottom. That's the definition of centered.
        self.assertLessEqual(abs(left - (64 - right)), 1)
        self.assertLessEqual(abs(top - (64 - bottom)), 1)
        # Subject should occupy ~80% of tile (padding fraction = 0.10).
        self.assertGreaterEqual(max(subject_w, subject_h), 48)
        self.assertLessEqual(max(subject_w, subject_h), 58)

    def test_preserves_aspect_ratio_for_tall_subject(self):
        # 32 wide × 128 tall subject → should stay tall after scaling.
        png = self._png((256, 256), (50, 10, 32, 128))
        result = _autocenter_frame(png, tile_size=64)
        out = Image.open(io.BytesIO(result))

        bbox = out.getbbox()
        self.assertIsNotNone(bbox)
        sw = bbox[2] - bbox[0]
        sh = bbox[3] - bbox[1]
        self.assertGreater(sh, sw)  # still taller than wide
        # Aspect ratio preserved within rounding tolerance.
        self.assertAlmostEqual(sw / sh, 32 / 128, delta=0.05)

    def test_fully_transparent_input_returns_empty_tile(self):
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        result = _autocenter_frame(buf.getvalue(), tile_size=64)
        out = Image.open(io.BytesIO(result))
        self.assertEqual(out.size, (64, 64))
        self.assertIsNone(out.getbbox())  # still fully transparent

    def test_invalid_image_raises(self):
        with self.assertRaises(SpriteGenerationError):
            _autocenter_frame(b"not a png", tile_size=64)


@override_settings(GEMINI_API_KEY="test-key")
class MotionTemplateTests(TestCase):
    """The ``motion`` param selects which 4-phase template drives frame
    notes. Default is ``idle`` — the most forgiving and most common
    sprite animation. ``walk`` and ``bounce`` are built-ins."""

    def setUp(self):
        self.parent = User.objects.create_user(username="p_motion", password="pw", role="parent")

    def _single_sheet_png(self, frame_count=4):
        sheet = Image.new("RGBA", (256 * frame_count, 256), (0, 0, 0, 0))
        for i in range(frame_count):
            subject = Image.new("RGBA", (128, 128), (180, 80, 80, 255))
            sheet.paste(subject, (i * 256 + 64, 64))
        buf = io.BytesIO()
        sheet.save(buf, format="PNG")
        return buf.getvalue()

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_default_motion_uses_idle_template(self, mock_frame):
        mock_frame.return_value = self._single_sheet_png()

        generate_sprite_sheet(
            slug="default-motion",
            prompt="pixel-art red fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            actor=self.parent,
            # motion not passed — must default to "idle"
        )

        prompt = mock_frame.call_args.kwargs["prompt"]
        self.assertIn("idle", prompt.lower())

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_walk_uses_walk_template(self, mock_frame):
        mock_frame.return_value = self._single_sheet_png()

        generate_sprite_sheet(
            slug="walk-motion",
            prompt="pixel-art red fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="walk",
            actor=self.parent,
        )

        prompt = mock_frame.call_args.kwargs["prompt"]
        self.assertIn("contact", prompt.lower())

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_bounce_uses_bounce_template(self, mock_frame):
        mock_frame.return_value = self._single_sheet_png()

        generate_sprite_sheet(
            slug="bounce-motion",
            prompt="pixel-art coin",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="bounce",
            actor=self.parent,
        )

        prompt = mock_frame.call_args.kwargs["prompt"]
        # Squash-and-stretch is the v1.2.2 bounce template — motion via
        # shape deformation, not vertical displacement.
        self.assertIn("squash", prompt.lower())
        self.assertIn("stretch", prompt.lower())

    def _run_motion_and_get_prompt(self, motion, slug, mock_frame):
        """Helper: fire a generation with the given motion and return
        the prompt string (already lowercased) that Gemini saw."""
        mock_frame.return_value = self._single_sheet_png()
        generate_sprite_sheet(
            slug=slug,
            prompt="pixel-art subject",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion=motion,
            actor=self.parent,
        )
        return mock_frame.call_args.kwargs["prompt"].lower()

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_bubble_uses_bubble_template(self, mock_frame):
        # Bubble template for liquid containers (potions, cauldrons).
        prompt = self._run_motion_and_get_prompt("bubble", "bub-check", mock_frame)
        self.assertIn("bubble", prompt)
        self.assertIn("liquid", prompt)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_flicker_uses_flicker_template(self, mock_frame):
        # Flicker template for flames (cauldron-on-fire, torches).
        prompt = self._run_motion_and_get_prompt("flicker", "fli-check", mock_frame)
        self.assertIn("flame", prompt)
        self.assertIn("ember", prompt)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_glow_uses_glow_template(self, mock_frame):
        # Glow template for chests, magical items, rewards.
        prompt = self._run_motion_and_get_prompt("glow", "glow-check", mock_frame)
        self.assertIn("halo", prompt)
        self.assertIn("glow", prompt)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_wobble_uses_wobble_template(self, mock_frame):
        # Wobble template for eggs, unstable objects.
        prompt = self._run_motion_and_get_prompt("wobble", "wob-check", mock_frame)
        self.assertIn("tilted", prompt)
        self.assertIn("lean", prompt)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_sway_uses_sway_template(self, mock_frame):
        # Sway template for plants, flags.
        prompt = self._run_motion_and_get_prompt("sway", "sway-check", mock_frame)
        self.assertIn("leaning", prompt)
        self.assertIn("base", prompt)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_prompt_frames_task_as_sequential_keyframes(self, mock_frame):
        """v1.2.3 slideshow fix: frame the task to Gemini as a SEQUENCE
        of interlocking keyframes, not 4 independent poses. Name-check
        hand-drawn-sprite-sheet references Gemini has in its training
        data so it pattern-matches the right mental model. Pin the
        language so it can't drift during future prompt cleanups."""
        mock_frame.return_value = self._single_sheet_png()

        generate_sprite_sheet(
            slug="seq-check",
            prompt="pixel-art fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="walk",
            actor=self.parent,
        )
        prompt = mock_frame.call_args.kwargs["prompt"].lower()

        for phrase in (
            "sequential",
            "keyframe",
            "incremental",
            "interlock",
        ):
            self.assertIn(phrase, prompt, f"prompt missing keyframe-framing phrase '{phrase}'")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_bounce_prompt_forbids_rotation(self, mock_frame):
        """v1.2.2's squash-and-stretch bounce got pattern-matched by
        Gemini to coin rotation (drawing the coin at different viewing
        angles — rest → rotating → edge-on → rest — like a Mario coin
        flip). v1.2.3 enumerates anti-rotation bans in both the pose
        sheet prompt and every BOUNCE_CYCLE_TEMPLATE phase."""
        mock_frame.return_value = self._single_sheet_png()

        generate_sprite_sheet(
            slug="rot-check",
            prompt="pixel-art coin",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="bounce",
            actor=self.parent,
        )

        prompt = mock_frame.call_args.kwargs["prompt"].lower()
        # Every anti-rotation verb that should show up at least once.
        for banned in ("rotate", "flip", "spin"):
            self.assertIn(banned, prompt, f"bounce prompt missing ban on '{banned}'")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_prompt_enumerates_scene_element_bans(self, mock_frame):
        """Gemini got creative with ground strips + motion trails in v1.2.1
        because the negative prompt was too generic. v1.2.2 enumerates
        the specific bans; this test pins that list so the bans don't
        get silently dropped during future prompt cleanups."""
        mock_frame.return_value = self._single_sheet_png()

        generate_sprite_sheet(
            slug="ban-check-anim",
            prompt="pixel-art fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )
        animated_prompt = mock_frame.call_args.kwargs["prompt"].lower()

        mock_frame.reset_mock()
        mock_frame.return_value = self._single_sheet_png(frame_count=1)
        # Static path — also needs to enumerate bans.
        generate_sprite_sheet(
            slug="ban-check-static",
            prompt="pixel-art fox",
            frame_count=1,
            tile_size=64,
            fps=0,
            actor=self.parent,
        )
        static_prompt = mock_frame.call_args.kwargs["prompt"].lower()

        # Each ban keyword must appear in BOTH prompts. Mix of
        # under-the-subject bans (ground/shadow/dust), motion-indicator
        # bans (motion line), and companion-object bans (bed, second
        # creature, floating panel) added in v1.2.4 after Gemini started
        # drawing cushions/tiles above idle subjects.
        for banned in (
            "ground", "shadow", "dust", "motion line",
            "bed", "pillow", "cushion", "slab",
            "second creature", "floating object",
        ):
            self.assertIn(banned, animated_prompt, f"animated prompt missing ban on '{banned}'")
            self.assertIn(banned, static_prompt, f"static prompt missing ban on '{banned}'")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_bounce_prompt_demands_dramatic_shape_change(self, mock_frame):
        """v1.2.3's sequential-keyframe 'small incremental deltas' rule
        flattened bounce because squash-and-stretch needs visibly
        different shapes across frames. v1.2.4 overrides that for
        bounce via explicit magnitude hints (30% shorter/taller) and
        a direct 'DOES NOT apply' clause in the bounce template. Pin
        the magnitude language so it doesn't silently get dropped."""
        mock_frame.return_value = self._single_sheet_png()

        generate_sprite_sheet(
            slug="bounce-mag-check",
            prompt="pixel-art coin",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="bounce",
            actor=self.parent,
        )
        prompt = mock_frame.call_args.kwargs["prompt"].lower()

        # Magnitude hints: percentage + "clearly visible" + explicit
        # override of the small-delta rule.
        self.assertIn("30%", prompt)
        self.assertIn("clearly visible", prompt)
        self.assertIn("does not apply", prompt)

    def test_unknown_motion_raises_before_api(self):
        with patch("apps.rpg.sprite_generation._generate_frame") as mock_frame:
            with self.assertRaises(SpriteGenerationError):
                generate_sprite_sheet(
                    slug="bad-motion",
                    prompt="x",
                    frame_count=4,
                    tile_size=64,
                    fps=8,
                    motion="teleport",
                    actor=self.parent,
                )
            mock_frame.assert_not_called()

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_ignored_for_static_sprites(self, mock_frame):
        """frame_count=1 doesn't need a motion template — the prompt
        should not contain any of the template phrases."""
        mock_frame.return_value = _png_bytes((128, 128))

        generate_sprite_sheet(
            slug="static-ignores-motion",
            prompt="pixel-art red fox",
            frame_count=1,
            tile_size=64,
            fps=0,
            motion="walk",  # should be silently ignored
            actor=self.parent,
        )

        prompt = mock_frame.call_args.kwargs["prompt"]
        # No frame-N-of-N phrasing on static prompts.
        self.assertNotIn("Frame 1 of", prompt)
        self.assertNotIn("contact", prompt.lower())


@override_settings(GEMINI_API_KEY="test-key")
class DebugArtifactTests(TestCase):
    """v1.3.1: when ``return_debug_raw=True``, the service also writes
    the raw Gemini output and the post-chroma-key output to the
    sprites bucket under a ``debug/`` prefix, and includes their URLs
    in the response. Enables inspection of intermediate pipeline
    artifacts — what did Gemini actually produce vs what ends up in
    the final sprite sheet."""

    def setUp(self):
        self.parent = User.objects.create_user(username="dbg_parent", password="pw", role="parent")

    def _sheet_png(self):
        img = Image.new("RGBA", (256, 64), (255, 0, 255, 255))
        for i in range(4):
            sub = Image.new("RGBA", (40, 40), (80, 180, 80, 255))
            img.paste(sub, (i * 64 + 12, 12))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_debug_flag_off_by_default_no_debug_in_response(self, mock_frame):
        mock_frame.return_value = self._sheet_png()

        result = generate_sprite_sheet(
            slug="no-debug",
            prompt="pixel-art thing",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            actor=self.parent,
        )

        self.assertNotIn("debug", result)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_debug_flag_on_returns_raw_and_post_chroma_urls(self, mock_frame):
        mock_frame.return_value = self._sheet_png()

        result = generate_sprite_sheet(
            slug="with-debug",
            prompt="pixel-art thing",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            return_debug_raw=True,
            actor=self.parent,
        )

        self.assertIn("debug", result)
        self.assertIn("raw_gemini_url", result["debug"])
        self.assertIn("post_chroma_key_url", result["debug"])
        self.assertTrue(result["debug"]["raw_gemini_url"])
        self.assertTrue(result["debug"]["post_chroma_key_url"])

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_debug_flag_on_also_works_for_static_sprites(self, mock_frame):
        mock_frame.return_value = self._sheet_png()

        result = generate_sprite_sheet(
            slug="static-debug",
            prompt="pixel-art thing",
            frame_count=1,
            tile_size=64,
            fps=0,
            return_debug_raw=True,
            actor=self.parent,
        )

        self.assertIn("debug", result)
        self.assertIn("raw_gemini_url", result["debug"])
        self.assertIn("post_chroma_key_url", result["debug"])


@override_settings(GEMINI_API_KEY="test-key")
class ReferenceImageUrlTests(TestCase):
    """v1.3.0a: when the caller provides ``reference_image_url``, the
    service downloads that URL's bytes and passes them to Gemini
    alongside the text prompt as a style + character anchor. Enables
    the self-anchored bulk animation workflow (animate an existing
    static sprite by passing its own URL as the reference — Gemini
    preserves character design and pack style by construction)."""

    def setUp(self):
        self.parent = User.objects.create_user(username="ref_parent", password="pw", role="parent")

    def _make_ref_png(self):
        img = Image.new("RGBA", (32, 32), (255, 100, 50, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _sheet_png(self, w=256, h=64):
        # 4-frame horizontal sheet with generic content.
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for i in range(4):
            sub = Image.new("RGBA", (40, 40), (100, 200, 100, 255))
            img.paste(sub, (i * 64 + 12, 12))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @patch("apps.rpg.sprite_generation._fetch_reference_image")
    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_reference_url_is_fetched_and_passed_to_gemini(self, mock_frame, mock_fetch):
        ref_bytes = self._make_ref_png()
        mock_fetch.return_value = ref_bytes
        mock_frame.return_value = self._sheet_png()

        generate_sprite_sheet(
            slug="ref-anim",
            prompt="pixel-art turtle",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            reference_image_url="https://s3.neato.digital/abby-sprites/rpg-sprites/turtle-abc.png",
            actor=self.parent,
        )

        # Service must have downloaded the URL.
        self.assertEqual(mock_fetch.call_count, 1)
        self.assertEqual(
            mock_fetch.call_args.args[0],
            "https://s3.neato.digital/abby-sprites/rpg-sprites/turtle-abc.png",
        )
        # And passed the downloaded bytes as reference_png to Gemini.
        self.assertEqual(mock_frame.call_args.kwargs["reference_png"], ref_bytes)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_no_reference_url_means_no_reference_png(self, mock_frame):
        """Default behavior unchanged — if caller doesn't pass
        reference_image_url, the single-shot Gemini call must NOT
        include a reference_png (pre-v1.3.0 behavior)."""
        mock_frame.return_value = self._sheet_png()

        generate_sprite_sheet(
            slug="no-ref",
            prompt="pixel-art thing",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            actor=self.parent,
        )

        self.assertIsNone(mock_frame.call_args.kwargs.get("reference_png"))

    @patch("apps.rpg.sprite_generation._fetch_reference_image")
    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_prompt_references_the_reference_image(self, mock_frame, mock_fetch):
        mock_fetch.return_value = self._make_ref_png()
        mock_frame.return_value = self._sheet_png()

        generate_sprite_sheet(
            slug="ref-prompt",
            prompt="pixel-art turtle",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            reference_image_url="https://example.com/turtle.png",
            actor=self.parent,
        )

        prompt = mock_frame.call_args.kwargs["prompt"].lower()
        # Prompt must explicitly instruct Gemini to use the reference
        # image as the authoritative character + style source.
        self.assertIn("reference", prompt)
        # And should emphasize identical character (not a new creature).
        self.assertTrue(
            "same character" in prompt or "exact character" in prompt or "identical" in prompt,
            "prompt should require the generated subject to match the reference character",
        )

    @patch("apps.rpg.sprite_generation._fetch_reference_image")
    def test_fetch_failure_raises_generation_error(self, mock_fetch):
        mock_fetch.side_effect = SpriteGenerationError("reference image fetch failed")

        with self.assertRaises(SpriteGenerationError):
            generate_sprite_sheet(
                slug="fetch-fails",
                prompt="x",
                frame_count=4,
                tile_size=64,
                fps=6,
                motion="idle",
                reference_image_url="https://bad.example.com/missing.png",
                actor=self.parent,
            )

    @patch("apps.rpg.sprite_generation._fetch_reference_image")
    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_reference_is_composited_onto_magenta_before_gemini(self, mock_frame, mock_fetch):
        """v1.3.2: when a reference image has transparent pixels, Gemini
        treats the implied (display-rendered) background as a style cue
        and outputs on that color — overriding the text prompt's
        'magenta background' instruction. The v1.3.0 turtle PoC proved
        this: reference had transparent background, Gemini output on
        white, chroma-key did nothing, final sprites came out tiny.

        Fix: composite the reference onto a solid magenta canvas BEFORE
        passing to Gemini. The model sees the character already on
        magenta, replicates that, and the existing chroma-key step
        cleans it normally."""
        # Reference image: a 32×32 PNG with a red subject in the middle
        # and transparent corners — mimics a typical core-pack sprite.
        ref = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        subj = Image.new("RGBA", (16, 16), (220, 60, 60, 255))
        ref.paste(subj, (8, 8))
        buf = io.BytesIO()
        ref.save(buf, format="PNG")
        raw_ref_bytes = buf.getvalue()
        mock_fetch.return_value = raw_ref_bytes
        mock_frame.return_value = self._sheet_png()

        generate_sprite_sheet(
            slug="composite-check",
            prompt="pixel-art subject",
            frame_count=4,
            tile_size=64,
            fps=4,
            motion="idle",
            reference_image_url="https://example.com/ref.png",
            actor=self.parent,
        )

        # Inspect the bytes that were actually passed to Gemini.
        sent_ref = mock_frame.call_args.kwargs["reference_png"]
        self.assertIsNotNone(sent_ref)
        # Must NOT be the raw reference — pre-composite should have
        # modified it (filled transparent → magenta).
        self.assertNotEqual(
            sent_ref, raw_ref_bytes,
            "reference must be composited onto magenta before being "
            "sent to Gemini; raw bytes were passed through unchanged",
        )
        # Decode and verify: every pixel is now opaque and the
        # previously-transparent corners are magenta (255, 0, 255).
        composited = Image.open(io.BytesIO(sent_ref)).convert("RGBA")
        self.assertEqual(composited.size, (32, 32))
        corner = composited.getpixel((0, 0))  # was transparent
        self.assertEqual(corner[:3], (255, 0, 255), f"corner should be magenta; got {corner}")
        self.assertEqual(corner[3], 255, "corner must be fully opaque (no alpha)")
        # Subject pixel (middle) stays its original color.
        center = composited.getpixel((16, 16))
        self.assertEqual(center[:3], (220, 60, 60), f"subject should be preserved; got {center}")

    @patch("apps.rpg.sprite_generation._fetch_reference_image")
    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_reference_url_also_works_for_static_sprites(self, mock_frame, mock_fetch):
        """Static sprite generation with a reference — useful for
        producing a new static in the style of an existing sprite
        (future use case). Should pass the ref through the same way."""
        ref_bytes = self._make_ref_png()
        mock_fetch.return_value = ref_bytes
        mock_frame.return_value = self._make_ref_png()

        generate_sprite_sheet(
            slug="static-with-ref",
            prompt="pixel-art new subject",
            frame_count=1,
            tile_size=64,
            fps=0,
            reference_image_url="https://example.com/ref.png",
            actor=self.parent,
        )

        self.assertEqual(mock_fetch.call_count, 1)
        self.assertEqual(mock_frame.call_args.kwargs["reference_png"], ref_bytes)


@override_settings(GEMINI_API_KEY="test-key")
class LayoutAwareExtractionTests(TestCase):
    """v1.3.3: Gemini doesn't reliably respect 'horizontal strip' prompts —
    it sometimes arranges sprites in a 2×2 grid, sometimes in a 4×1
    vertical strip, etc. Our extractor finds connected opaque
    components in the chroma-keyed sheet and sorts them into reading
    order (top-to-bottom, then left-to-right) regardless of layout.

    This replaces the fixed-column ``_slice_and_ground_align_sheet``
    approach for the main path (old function kept as a fallback when
    CC detection finds fewer than ``frame_count`` components)."""

    def setUp(self):
        self.parent = User.objects.create_user(username="lay_parent", password="pw", role="parent")

    def _sheet_2x2_grid(self, size=512):
        """Build a 1024×1024 sheet with 4 distinct subjects in a 2×2
        grid, each a different color so we can verify extraction order
        by inspecting colors of the output tiles."""
        img = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
        # Top-left (red), top-right (green), bottom-left (blue), bottom-right (yellow)
        subjects = [
            (100, 100, 200, 200, (220, 50, 50, 255)),    # TL red
            (700, 100, 200, 200, (50, 220, 50, 255)),    # TR green
            (100, 700, 200, 200, (50, 50, 220, 255)),    # BL blue
            (700, 700, 200, 200, (220, 220, 50, 255)),   # BR yellow
        ]
        for x, y, w, h, color in subjects:
            sub = Image.new("RGBA", (w, h), color)
            img.paste(sub, (x, y))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _sheet_1x4_horizontal(self):
        """4 subjects in a horizontal row."""
        img = Image.new("RGBA", (1024, 256), (0, 0, 0, 0))
        colors = [(220, 50, 50, 255), (50, 220, 50, 255),
                  (50, 50, 220, 255), (220, 220, 50, 255)]
        for i, color in enumerate(colors):
            sub = Image.new("RGBA", (180, 180), color)
            img.paste(sub, (i * 256 + 38, 38))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_2x2_grid_is_extracted_in_reading_order(self, mock_frame):
        """Sheet has 4 colored subjects in a 2×2 grid. Output tiles
        must be in reading order: TL → TR → BL → BR."""
        mock_frame.return_value = self._sheet_2x2_grid()

        generate_sprite_sheet(
            slug="grid-order",
            prompt="x",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            actor=self.parent,
        )

        row = SpriteAsset.objects.get(slug="grid-order")
        with row.image.open("rb") as fh:
            strip = Image.open(fh)
            strip.load()
        # Verify each tile has the correct color (reading order).
        expected_colors = [
            (220, 50, 50),   # TL red → tile 0
            (50, 220, 50),   # TR green → tile 1
            (50, 50, 220),   # BL blue → tile 2
            (220, 220, 50),  # BR yellow → tile 3
        ]
        for i, expected in enumerate(expected_colors):
            tile = strip.crop((i * 64, 0, (i + 1) * 64, 64))
            bbox = tile.getbbox()
            self.assertIsNotNone(bbox, f"tile {i} has no opaque pixels")
            # Sample the center of the subject bbox.
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            r, g, b, _ = tile.getpixel((cx, cy))
            # Each channel must be close to expected (with some
            # tolerance for LANCZOS resampling edge smoothing).
            self.assertLess(
                abs(r - expected[0]) + abs(g - expected[1]) + abs(b - expected[2]),
                90,
                f"tile {i}: expected ~{expected}, got ({r},{g},{b})",
            )

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_1x4_horizontal_is_extracted_left_to_right(self, mock_frame):
        """Sheet already in the expected 1×4 horizontal layout. Output
        tiles must be in left-to-right order."""
        mock_frame.return_value = self._sheet_1x4_horizontal()

        generate_sprite_sheet(
            slug="row-order",
            prompt="x",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            actor=self.parent,
        )

        row = SpriteAsset.objects.get(slug="row-order")
        with row.image.open("rb") as fh:
            strip = Image.open(fh)
            strip.load()
        expected_colors = [
            (220, 50, 50),   # first in row → tile 0
            (50, 220, 50),   # second → tile 1
            (50, 50, 220),   # third → tile 2
            (220, 220, 50),  # fourth → tile 3
        ]
        for i, expected in enumerate(expected_colors):
            tile = strip.crop((i * 64, 0, (i + 1) * 64, 64))
            bbox = tile.getbbox()
            self.assertIsNotNone(bbox)
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            r, g, b, _ = tile.getpixel((cx, cy))
            self.assertLess(
                abs(r - expected[0]) + abs(g - expected[1]) + abs(b - expected[2]),
                90,
            )

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_all_tiles_ground_aligned_to_same_baseline(self, mock_frame):
        """The tile 2 vertical-mis-alignment bug from v1.3.0 was caused
        by the old slicer putting 2×2-grid subjects at wrong Y. With
        CC extraction, every tile's subject bottom must land at the
        same baseline — no more teleport during animation."""
        mock_frame.return_value = self._sheet_2x2_grid()

        generate_sprite_sheet(
            slug="baseline-check",
            prompt="x",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            actor=self.parent,
        )

        row = SpriteAsset.objects.get(slug="baseline-check")
        with row.image.open("rb") as fh:
            strip = Image.open(fh)
            strip.load()
        # All 4 tiles' subject bottoms must be within 1px of each other.
        bottoms = []
        for i in range(4):
            tile = strip.crop((i * 64, 0, (i + 1) * 64, 64))
            bbox = tile.getbbox()
            self.assertIsNotNone(bbox)
            bottoms.append(bbox[3])
        self.assertLessEqual(
            max(bottoms) - min(bottoms), 1,
            f"subject bottoms not aligned: {bottoms}",
        )

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_fallback_to_slicing_when_fewer_components_than_frames(self, mock_frame):
        """Edge case: if Gemini somehow produces fewer distinct subjects
        than frames requested (e.g., subjects connect), fall back to
        the horizontal slicer rather than raising. Guarantees the
        pipeline always produces a result."""
        # Single-component sheet (one big red rectangle spanning most of
        # the image — looks like all subjects touched/merged).
        img = Image.new("RGBA", (1024, 256), (0, 0, 0, 0))
        big = Image.new("RGBA", (900, 150), (220, 50, 50, 255))
        img.paste(big, (50, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        mock_frame.return_value = buf.getvalue()

        # Should succeed without raising and produce 4 tiles.
        generate_sprite_sheet(
            slug="fallback-case",
            prompt="x",
            frame_count=4,
            tile_size=64,
            fps=6,
            motion="idle",
            actor=self.parent,
        )
        row = SpriteAsset.objects.get(slug="fallback-case")
        with row.image.open("rb") as fh:
            strip = Image.open(fh)
            strip.load()
        self.assertEqual(strip.size, (256, 64))


@override_settings(GEMINI_API_KEY="test-key")
class OneShotPoseSheetTests(TestCase):
    """v1.2 architecture: a single Gemini call produces all N poses as one
    image, which is then sliced into N equal tiles and each tile autocentered
    with a SHARED scale factor. This removes the iterative per-frame drift
    that v1.1 couldn't eliminate and fixes the per-frame size variance that
    v1.1's per-slice autocenter introduced."""

    def setUp(self):
        self.parent = User.objects.create_user(username="p5", password="pw", role="parent")

    def _sheet_png(self, slice_configs):
        """Build a horizontal sheet where each slice contains a subject rect.

        ``slice_configs`` is a list of ``(rect_w, rect_h, color)`` — one
        per slice. Each slice is 256×256 in the sheet, subject rect
        centered within its slice.
        """
        n = len(slice_configs)
        sheet = Image.new("RGBA", (256 * n, 256), (0, 0, 0, 0))
        for i, (rw, rh, color) in enumerate(slice_configs):
            subject = Image.new("RGBA", (rw, rh), color)
            x = i * 256 + (256 - rw) // 2
            y = (256 - rh) // 2
            sheet.paste(subject, (x, y))
        buf = io.BytesIO()
        sheet.save(buf, format="PNG")
        return buf.getvalue()

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_animated_uses_exactly_one_gemini_call(self, mock_frame):
        """Regardless of frame_count, only one API call should fire —
        that's the whole point of the one-shot architecture."""
        mock_frame.return_value = self._sheet_png([
            (80, 80, (200, 50, 50, 255)),
        ] * 4)

        generate_sprite_sheet(
            slug="one-shot-call",
            prompt="pixel-art red fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )

        self.assertEqual(mock_frame.call_count, 1)
        # The single call must NOT use a reference image (no iterative mode).
        self.assertIsNone(mock_frame.call_args.kwargs.get("reference_png"))

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_one_shot_prompt_lists_all_pose_phases(self, mock_frame):
        """The single call's prompt must describe every frame's pose so
        Gemini can draw the full motion sequence in one composition."""
        mock_frame.return_value = self._sheet_png([(64, 64, (100, 100, 200, 255))] * 4)

        generate_sprite_sheet(
            slug="pose-list",
            prompt="pixel-art wolf",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="walk",
            actor=self.parent,
        )

        prompt = mock_frame.call_args.kwargs["prompt"]
        # Every template phase should appear in the composite prompt.
        from apps.rpg.sprite_generation import WALK_CYCLE_TEMPLATE
        for phase in WALK_CYCLE_TEMPLATE:
            # Use a distinctive substring from each phase.
            key = phase.split(":", 1)[0]  # e.g. "right-contact pose"
            self.assertIn(key, prompt, f"phase '{key}' missing from prompt")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_ground_align_preserves_relative_vertical_position(self, mock_frame):
        """v1.2.5 critical algorithm test. Classic hand-drawn sprite
        cycles preserve body bob by keeping the character's feet on
        a shared ground line and letting the body rise/fall above it
        between frames. v1.2.4's center-align normalized every
        subject's bbox to the tile's vertical center — erasing the
        bob and producing the 'slideshow feel.' Ground-align anchors
        each subject's BOTTOM to a shared baseline near the tile's
        bottom edge; variations in bbox height then show as the
        subject's TOP being at different Y positions across tiles,
        which IS the bob.
        """
        def _sheet_with_varying_heights():
            sheet = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
            # Slice 0: small 40×40 subject, centered in cell.
            subj1 = Image.new("RGBA", (40, 40), (200, 60, 60, 255))
            sheet.paste(subj1, ((256 - 40) // 2, (256 - 40) // 2))
            # Slice 1: tall 80×80 subject, centered in cell.
            subj2 = Image.new("RGBA", (80, 80), (60, 200, 60, 255))
            sheet.paste(subj2, (256 + (256 - 80) // 2, (256 - 80) // 2))
            buf = io.BytesIO()
            sheet.save(buf, format="PNG")
            return buf.getvalue()
        mock_frame.return_value = _sheet_with_varying_heights()

        generate_sprite_sheet(
            slug="ground-align-check",
            prompt="pixel-art subject",
            frame_count=2,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )

        row = SpriteAsset.objects.get(slug="ground-align-check")
        with row.image.open("rb") as fh:
            strip = Image.open(fh)
            strip.load()

        tile0 = strip.crop((0, 0, 64, 64))
        tile1 = strip.crop((64, 0, 128, 64))
        bbox0 = tile0.getbbox()
        bbox1 = tile1.getbbox()
        self.assertIsNotNone(bbox0)
        self.assertIsNotNone(bbox1)
        # Shared baseline: both subjects' BOTTOMS within 1px of each other.
        bottom0 = bbox0[3]
        bottom1 = bbox1[3]
        self.assertLessEqual(
            abs(bottom0 - bbox1[3]), 1,
            f"ground-align violated: bottom0={bottom0}, bottom1={bottom1}",
        )
        # Tops differ: tile 0 (smaller subject after shared scaling)
        # must have its top LOWER in the tile than tile 1 (bigger
        # subject). That's what preserves body-bob across frames.
        top0 = bbox0[1]
        top1 = bbox1[1]
        self.assertGreater(
            top0, top1,
            f"smaller-subject top should be lower in tile (larger Y) than "
            f"bigger-subject top; got top0={top0}, top1={top1}",
        )

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_size_consistency_across_frames_with_variable_subject_sizes(self, mock_frame):
        """The v1.1 regression: different bbox sizes → different per-frame
        scale factors → visible size variance. v1.2 uses a shared scale
        computed from the largest bbox across all slices, so a sprawled
        pose and a tucked pose end up at the same scale in the output."""
        # Slice 1: tiny subject (20×20). Slice 2: large subject (120×120).
        # Slice 3: medium (60×60). Slice 4: tall (40×100).
        mock_frame.return_value = self._sheet_png([
            (20, 20, (255, 0, 0, 255)),
            (120, 120, (0, 255, 0, 255)),
            (60, 60, (0, 0, 255, 255)),
            (40, 100, (255, 255, 0, 255)),
        ])

        generate_sprite_sheet(
            slug="size-check",
            prompt="pixel-art variable",
            frame_count=4,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )

        # Read the saved 4-tile strip and inspect each tile's subject bbox.
        row = SpriteAsset.objects.get(slug="size-check")
        with row.image.open("rb") as fh:
            strip = Image.open(fh)
            strip.load()
        self.assertEqual(strip.size, (256, 64))

        # The LARGEST subject (slice 2, 120×120) was the scale reference.
        # Its bbox in the output should fill ~80% of the 64-tile. Smaller
        # subjects from slices 1/3/4 should be proportionally smaller —
        # so the largest-subject tile still dominates as expected.
        tiles = [strip.crop((i * 64, 0, (i + 1) * 64, 64)) for i in range(4)]
        bbox2 = tiles[1].getbbox()
        self.assertIsNotNone(bbox2)
        max2 = max(bbox2[2] - bbox2[0], bbox2[3] - bbox2[1])
        # Slice 2 was the reference. It should fit the inner 80% window,
        # which for tile_size=64 is 52px — give a couple of px for rounding.
        self.assertGreaterEqual(max2, 48)
        self.assertLessEqual(max2, 56)

        # Slice 1 was 20×20 (one-sixth the size of slice 2's 120). Its
        # tile output should also be about one-sixth the size — NOT scaled
        # up to fill the same 80% (which was v1.1's bug).
        bbox1 = tiles[0].getbbox()
        self.assertIsNotNone(bbox1)
        max1 = max(bbox1[2] - bbox1[0], bbox1[3] - bbox1[1])
        # Expected ~ 52 * (20 / 120) ≈ 9. Give a wide tolerance.
        self.assertLessEqual(max1, 14)
