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
