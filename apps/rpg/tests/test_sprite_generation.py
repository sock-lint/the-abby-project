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
class IterativeSpriteGenerationTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p2", password="pw", role="parent")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_4_frames_stitch_into_horizontal_strip(self, mock_frame):
        mock_frame.side_effect = [_png_bytes((128, 128)) for _ in range(4)]

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

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_each_frame_after_first_passes_previous_as_reference(self, mock_frame):
        mock_frame.side_effect = [_png_bytes((128, 128)) for _ in range(3)]

        generate_sprite_sheet(
            slug="trio",
            prompt="x",
            frame_count=3,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )

        self.assertEqual(mock_frame.call_count, 3)
        calls = mock_frame.call_args_list
        self.assertIsNone(calls[0].kwargs.get("reference_png"))
        self.assertIsNotNone(calls[1].kwargs.get("reference_png"))
        self.assertIsNotNone(calls[2].kwargs.get("reference_png"))


@override_settings(GEMINI_API_KEY="test-key")
class SpriteGenerationErrorSurfaceTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p3", password="pw", role="parent")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_api_failure_mid_iteration_rolls_back(self, mock_frame):
        mock_frame.side_effect = [
            _png_bytes((128, 128)),
            _png_bytes((128, 128)),
            SpriteGenerationError("upstream API down"),
        ]

        with self.assertRaises(SpriteGenerationError):
            generate_sprite_sheet(
                slug="aborted",
                prompt="x",
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

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_default_motion_uses_idle_template(self, mock_frame):
        mock_frame.side_effect = [_png_bytes((128, 128)) for _ in range(4)]

        generate_sprite_sheet(
            slug="default-motion",
            prompt="pixel-art red fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            actor=self.parent,
            # motion not passed — must default to "idle"
        )

        frame_1_prompt = mock_frame.call_args_list[0].kwargs["prompt"]
        self.assertIn("idle", frame_1_prompt.lower())

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_walk_uses_walk_template(self, mock_frame):
        mock_frame.side_effect = [_png_bytes((128, 128)) for _ in range(4)]

        generate_sprite_sheet(
            slug="walk-motion",
            prompt="pixel-art red fox",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="walk",
            actor=self.parent,
        )

        frame_1_prompt = mock_frame.call_args_list[0].kwargs["prompt"]
        self.assertIn("contact", frame_1_prompt.lower())

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_motion_bounce_uses_bounce_template(self, mock_frame):
        mock_frame.side_effect = [_png_bytes((128, 128)) for _ in range(4)]

        generate_sprite_sheet(
            slug="bounce-motion",
            prompt="pixel-art coin",
            frame_count=4,
            tile_size=64,
            fps=8,
            motion="bounce",
            actor=self.parent,
        )

        frame_1_prompt = mock_frame.call_args_list[0].kwargs["prompt"]
        self.assertIn("baseline", frame_1_prompt.lower())

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
class IterativeReferencePassesAutocenteredFrameTests(TestCase):
    """After v1.1, the reference passed to frame N+1 must be the AUTOCENTERED
    frame N — not the raw Gemini output. This is what normalizes the
    reference position so iterative generation doesn't drift."""

    def setUp(self):
        self.parent = User.objects.create_user(username="p5", password="pw", role="parent")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_reference_passed_to_frame_2_is_tile_sized(self, mock_frame):
        # Return a 512×512 image (Gemini's typical output) where the
        # subject is in the top-left corner. Autocentering should crop +
        # center it to 64×64 before passing back as reference.
        def _big_offset_png():
            img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            subject = Image.new("RGBA", (80, 80), (200, 50, 50, 255))
            img.paste(subject, (0, 0))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        mock_frame.side_effect = [_big_offset_png() for _ in range(2)]

        generate_sprite_sheet(
            slug="ref-check",
            prompt="pixel-art fox walking",
            frame_count=2,
            tile_size=64,
            fps=8,
            actor=self.parent,
        )

        # Second call got a reference. Verify it's 64×64 (tile-sized,
        # autocentered) — NOT 512×512 (raw Gemini output).
        ref_bytes = mock_frame.call_args_list[1].kwargs["reference_png"]
        ref_img = Image.open(io.BytesIO(ref_bytes))
        self.assertEqual(ref_img.size, (64, 64))
        # And the subject should be centered now, not top-left.
        bbox = ref_img.getbbox()
        self.assertIsNotNone(bbox)
        left, top, right, bottom = bbox
        self.assertLessEqual(abs(left - (64 - right)), 1)
        self.assertLessEqual(abs(top - (64 - bottom)), 1)
