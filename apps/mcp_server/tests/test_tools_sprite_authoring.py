import base64
import io
from unittest.mock import patch

from PIL import Image
from django.test import TestCase, override_settings
from pydantic import ValidationError

from apps.accounts.models import User
from apps.rpg.models import SpriteAsset

from apps.mcp_server.context import set_current_user, reset_current_user
from apps.mcp_server.errors import MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    RegisterSpriteIn,
    RegisterSpriteBatchIn,
    ListSpritesIn,
    DeleteSpriteIn,
    AnimatedSpriteTileDecl,
    GenerateSpriteSheetIn,
)
from apps.mcp_server.tools.sprite_authoring import (
    register_sprite as tool_register_sprite,
    register_sprite_batch as tool_register_sprite_batch,
    list_sprites as tool_list_sprites,
    delete_sprite as tool_delete_sprite,
    generate_sprite_sheet as tool_generate_sprite_sheet,
)


def _png_b64(size=(32, 32)):
    img = Image.new("RGBA", size, (0, 0, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class SpriteAuthoringToolTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="kid", password="pw", role="child")

    def _as_parent(self):
        return set_current_user(self.parent)

    def _as_child(self):
        return set_current_user(self.child)

    def test_register_sprite_requires_parent(self):
        tok = self._as_child()
        try:
            with self.assertRaises(MCPPermissionDenied):
                tool_register_sprite(RegisterSpriteIn(slug="x", image_b64=_png_b64()))
        finally:
            reset_current_user(tok)

    def test_register_sprite_happy_path(self):
        tok = self._as_parent()
        try:
            result = tool_register_sprite(RegisterSpriteIn(slug="t1", image_b64=_png_b64()))
            self.assertEqual(result["slug"], "t1")
            self.assertTrue(SpriteAsset.objects.filter(slug="t1").exists())
        finally:
            reset_current_user(tok)

    def test_list_sprites(self):
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(slug="t2", image_b64=_png_b64()))
            tool_register_sprite(RegisterSpriteIn(slug="t3", image_b64=_png_b64(), pack="other"))
            result = tool_list_sprites(ListSpritesIn())
            slugs = {s["slug"] for s in result["sprites"]}
            self.assertIn("t2", slugs)
            self.assertIn("t3", slugs)
        finally:
            reset_current_user(tok)

    def test_list_sprites_filter_by_pack(self):
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(slug="t4", image_b64=_png_b64(), pack="a"))
            tool_register_sprite(RegisterSpriteIn(slug="t5", image_b64=_png_b64(), pack="b"))
            result = tool_list_sprites(ListSpritesIn(pack="a"))
            self.assertEqual({s["slug"] for s in result["sprites"]}, {"t4"})
        finally:
            reset_current_user(tok)

    def test_delete_sprite(self):
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(slug="bye", image_b64=_png_b64()))
            result = tool_delete_sprite(DeleteSpriteIn(slug="bye"))
            self.assertEqual(result, {"slug": "bye", "deleted": True})
            self.assertFalse(SpriteAsset.objects.filter(slug="bye").exists())
        finally:
            reset_current_user(tok)

    def test_register_sprite_batch(self):
        tok = self._as_parent()
        try:
            sheet = _png_b64((64, 32))
            result = tool_register_sprite_batch(RegisterSpriteBatchIn(
                sheet_b64=sheet,
                tile_size=32,
                tiles=[
                    AnimatedSpriteTileDecl(slug="b1", col=0, row=0),
                    AnimatedSpriteTileDecl(slug="b2", col=1, row=0),
                ],
            ))
            self.assertEqual(len(result["registered"]), 2)
            self.assertEqual(result["skipped"], [])
        finally:
            reset_current_user(tok)

    def test_all_tools_registered_with_fastmcp(self):
        """Guard against a regression where the sprite_authoring module
        is not imported by server.py — the @tool() decorators only fire
        on import, so a missing import silently drops the tools from the
        MCP surface.
        """
        from apps.mcp_server.server import mcp
        import asyncio
        tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
        self.assertIn("register_sprite", tool_names)
        self.assertIn("register_sprite_batch", tool_names)
        self.assertIn("list_sprites", tool_names)
        self.assertIn("delete_sprite", tool_names)
        self.assertIn("generate_sprite_sheet", tool_names)


def _png_bytes(size=(128, 128)):
    img = Image.new("RGBA", size, (100, 50, 150, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@override_settings(GEMINI_API_KEY="test-key")
class GenerateSpriteSheetToolTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="gen_parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="gen_kid", password="pw", role="child")

    def _as_parent(self):
        return set_current_user(self.parent)

    def _as_child(self):
        return set_current_user(self.child)

    def test_requires_parent(self):
        tok = self._as_child()
        try:
            with self.assertRaises(MCPPermissionDenied):
                tool_generate_sprite_sheet(GenerateSpriteSheetIn(
                    slug="denied",
                    prompt="pixel-art fox",
                ))
        finally:
            reset_current_user(tok)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_parent_happy_path_delegates_to_service(self, mock_frame):
        mock_frame.return_value = _png_bytes((256, 256))
        tok = self._as_parent()
        try:
            result = tool_generate_sprite_sheet(GenerateSpriteSheetIn(
                slug="gen-fox",
                prompt="pixel-art red fox sitting",
                frame_count=1,
                tile_size=64,
                fps=0,
            ))
        finally:
            reset_current_user(tok)

        self.assertEqual(result["slug"], "gen-fox")
        self.assertEqual(result["frame_count"], 1)
        self.assertEqual(result["frame_width_px"], 64)
        self.assertTrue(SpriteAsset.objects.filter(slug="gen-fox").exists())
        # The SpriteAsset was created by the parent (actor=get_current_user()).
        asset = SpriteAsset.objects.get(slug="gen-fox")
        self.assertEqual(asset.created_by, self.parent)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_parent_animated_4_frames(self, mock_frame):
        mock_frame.side_effect = [_png_bytes((128, 128)) for _ in range(4)]
        tok = self._as_parent()
        try:
            result = tool_generate_sprite_sheet(GenerateSpriteSheetIn(
                slug="gen-walk",
                prompt="pixel-art red fox walking side view",
                frame_count=4,
                tile_size=64,
                fps=8,
            ))
        finally:
            reset_current_user(tok)

        self.assertEqual(result["frame_count"], 4)
        self.assertEqual(result["fps"], 8)
        self.assertEqual(result["frame_layout"], "horizontal")

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_service_error_wraps_as_mcp_validation_error(self, mock_frame):
        from apps.rpg.sprite_generation import SpriteGenerationError
        mock_frame.side_effect = SpriteGenerationError("upstream API down")
        tok = self._as_parent()
        try:
            with self.assertRaises(MCPValidationError):
                tool_generate_sprite_sheet(GenerateSpriteSheetIn(
                    slug="fails",
                    prompt="pixel-art fox",
                    frame_count=1,
                    tile_size=64,
                    fps=0,
                ))
        finally:
            reset_current_user(tok)


class GenerateSpriteSheetSchemaTests(TestCase):
    """Schema-level validation — these fail at pydantic construction, before
    the tool layer ever sees them. Guarantees cheap rejection of obviously
    bad inputs without touching Django users or the Gemini SDK.
    """

    def test_prompt_too_short_rejected(self):
        with self.assertRaises(ValidationError):
            GenerateSpriteSheetIn(slug="x", prompt="a")

    def test_frame_count_over_cap_rejected(self):
        with self.assertRaises(ValidationError):
            GenerateSpriteSheetIn(slug="x", prompt="pixel-art fox", frame_count=99)

    def test_tile_size_must_be_32_64_or_128(self):
        with self.assertRaises(ValidationError):
            GenerateSpriteSheetIn(slug="x", prompt="pixel-art fox", tile_size=50)

    def test_static_with_nonzero_fps_rejected(self):
        with self.assertRaises(ValidationError):
            GenerateSpriteSheetIn(
                slug="x", prompt="pixel-art fox", frame_count=1, fps=8,
            )

    def test_animated_with_zero_fps_rejected(self):
        with self.assertRaises(ValidationError):
            GenerateSpriteSheetIn(
                slug="x", prompt="pixel-art fox", frame_count=4, tile_size=64, fps=0,
            )

    def test_valid_static_accepted(self):
        m = GenerateSpriteSheetIn(slug="ok", prompt="pixel-art fox")
        self.assertEqual(m.frame_count, 1)
        self.assertEqual(m.fps, 0)
        self.assertEqual(m.tile_size, 64)
        self.assertEqual(m.pack, "ai-generated")

    def test_valid_animated_accepted(self):
        m = GenerateSpriteSheetIn(
            slug="ok",
            prompt="pixel-art fox",
            frame_count=4,
            tile_size=32,
            fps=8,
            style_hint="gameboy palette",
        )
        self.assertEqual(m.frame_count, 4)
        self.assertEqual(m.fps, 8)
        self.assertEqual(m.style_hint, "gameboy palette")
