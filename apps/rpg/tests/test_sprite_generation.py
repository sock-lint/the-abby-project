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

        # Each ban keyword must appear in BOTH prompts.
        for banned in ("ground", "shadow", "dust", "motion line"):
            self.assertIn(banned, animated_prompt, f"animated prompt missing ban on '{banned}'")
            self.assertIn(banned, static_prompt, f"static prompt missing ban on '{banned}'")

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
