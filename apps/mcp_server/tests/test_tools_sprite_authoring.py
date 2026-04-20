import base64
import io
from PIL import Image
from django.test import TestCase
from apps.accounts.models import User
from apps.rpg.models import SpriteAsset

from apps.mcp_server.context import set_current_user, reset_current_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.mcp_server.schemas import (
    RegisterSpriteIn,
    RegisterSpriteBatchIn,
    ListSpritesIn,
    DeleteSpriteIn,
    AnimatedSpriteTileDecl,
)
from apps.mcp_server.tools.sprite_authoring import (
    register_sprite as tool_register_sprite,
    register_sprite_batch as tool_register_sprite_batch,
    list_sprites as tool_list_sprites,
    delete_sprite as tool_delete_sprite,
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
