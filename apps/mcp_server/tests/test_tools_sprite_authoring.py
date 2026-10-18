import base64
import io

from PIL import Image
from django.test import TestCase
from pydantic import ValidationError

from apps.accounts.models import User
from apps.rpg.models import SpriteAsset

from config.tests.factories import make_family

from apps.mcp_server.context import (
    set_current_user, reset_current_user, set_current_scopes, reset_current_scopes,
)
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    RegisterSpriteIn,
    RegisterSpriteBatchIn,
    ListSpritesIn,
    DeleteSpriteIn,
    AnimatedSpriteTileDecl,
    GetSpriteIn,
    UpdateSpriteMetadataIn,
)
from apps.mcp_server.tools.sprite_authoring import (
    register_sprite as tool_register_sprite,
    register_sprite_batch as tool_register_sprite_batch,
    list_sprites as tool_list_sprites,
    delete_sprite as tool_delete_sprite,
    get_sprite as tool_get_sprite,
    update_sprite_metadata as tool_update_sprite_metadata,
)


def _png_b64(size=(32, 32)):
    img = Image.new("RGBA", size, (0, 0, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class SpriteAuthoringToolTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent", is_staff=True)
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
        from apps.mcp_server.tool_policy import MCP_SCOPES
        scopes_token = set_current_scopes(MCP_SCOPES)
        try:
            tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
        finally:
            reset_current_scopes(scopes_token)
        self.assertIn("register_sprite", tool_names)
        self.assertIn("register_sprite_batch", tool_names)
        self.assertIn("list_sprites", tool_names)
        self.assertIn("delete_sprite", tool_names)
        self.assertIn("update_sprite_metadata", tool_names)
        self.assertIn("get_sprite", tool_names)
        for retired_tool in (
            "generate_sprite_sheet", "reroll_sprite", "propose_sprite_reroll",
            "get_sprite_prompting_playbook",
        ):
            self.assertNotIn(retired_tool, tool_names)



class GetSpriteToolTests(TestCase):
    """Prepared sprites and historical authoring metadata remain readable."""

    def setUp(self):
        # Two distinct families so test_regular_parent_can_read genuinely
        # exercises the cross-family read path. Without explicit families,
        # User.save()'s defense-in-depth lands every user in the same
        # auto-attached default-family and the test would pass even if
        # get_sprite were accidentally family-scoped.
        fam_a = make_family(
            "get-sprite-family-a",
            parents=[{"username": "get_parent", "is_staff": True}],
            children=[{"username": "get_kid"}],
        )
        fam_b = make_family(
            "get-sprite-family-b",
            parents=[{"username": "get_regular_parent"}],
        )
        self.parent = fam_a.parents[0]
        self.child = fam_a.children[0]
        self.regular_parent = fam_b.parents[0]

    def _as(self, user):
        return set_current_user(user)

    def test_returns_full_authoring_shape(self):
        tok = self._as(self.parent)
        try:
            tool_register_sprite(RegisterSpriteIn(slug="full-shape", image_b64=_png_b64()))
            # Keep historical authoring inputs readable after generation retires.
            # Manually stamp them so we can verify
            # the tool surfaces them.
            SpriteAsset.objects.filter(slug="full-shape").update(
                prompt="refined prompt",
                original_intent="a thing the parent wanted",
                motion="idle",
                style_hint="moss tint",
                tile_size=64,
                reference_image_url="https://example.com/ref.png",
            )
            result = tool_get_sprite(GetSpriteIn(slug="full-shape"))
        finally:
            reset_current_user(tok)

        self.assertEqual(result["slug"], "full-shape")
        self.assertEqual(result["prompt"], "refined prompt")
        self.assertEqual(result["original_intent"], "a thing the parent wanted")
        self.assertEqual(result["motion"], "idle")
        self.assertEqual(result["style_hint"], "moss tint")
        self.assertEqual(result["tile_size"], 64)
        self.assertEqual(result["reference_image_url"], "https://example.com/ref.png")
        # Plus the read-shape that ``list_sprites`` already returns.
        self.assertIn("url", result)
        self.assertIn("frame_count", result)
        self.assertIn("frame_width_px", result)
        self.assertIn("frame_height_px", result)

    def test_unknown_slug_raises_not_found(self):
        tok = self._as(self.parent)
        try:
            with self.assertRaises(MCPNotFoundError):
                tool_get_sprite(GetSpriteIn(slug="never-registered"))
        finally:
            reset_current_user(tok)

    def test_requires_parent(self):
        """Read-only — gated on require_parent (any parent in any family).
        Children must be denied."""
        tok = self._as(self.parent)
        try:
            tool_register_sprite(RegisterSpriteIn(slug="parent-only", image_b64=_png_b64()))
        finally:
            reset_current_user(tok)
        tok = self._as(self.child)
        try:
            with self.assertRaises(MCPPermissionDenied):
                tool_get_sprite(GetSpriteIn(slug="parent-only"))
        finally:
            reset_current_user(tok)

    def test_regular_parent_can_read(self):
        """Read access is wider than write AND wider than family — a
        non-staff parent in a different family can call ``get_sprite``
        through the ordinary catalog read surface. Sprites are
        global content; every parent in every family can read them."""
        tok = self._as(self.parent)
        try:
            tool_register_sprite(RegisterSpriteIn(slug="readable", image_b64=_png_b64()))
        finally:
            reset_current_user(tok)
        tok = self._as(self.regular_parent)
        try:
            result = tool_get_sprite(GetSpriteIn(slug="readable"))
            self.assertEqual(result["slug"], "readable")
        finally:
            reset_current_user(tok)

    def test_include_image_default_false_returns_dict(self):
        """Lean default: no image bytes, just the authoring dict. Existing
        callers (catalog dumps, prompt-rewriting loops) pay nothing for
        the new behavior."""
        tok = self._as(self.parent)
        try:
            tool_register_sprite(RegisterSpriteIn(slug="lean", image_b64=_png_b64()))
            result = tool_get_sprite(GetSpriteIn(slug="lean"))
            self.assertIsInstance(result, dict)
            self.assertEqual(result["slug"], "lean")
        finally:
            reset_current_user(tok)

    def test_include_image_true_returns_dict_plus_imagecontent(self):
        """include_image=True returns ``[dict, ImageContent]``. FastMCP
        serializes the dict as a text JSON content block and passes the
        ImageContent through, so the chat agent sees both metadata and
        rendered pixels without going through the public Ceph URL.
        """
        from mcp.types import ImageContent
        tok = self._as(self.parent)
        try:
            tool_register_sprite(RegisterSpriteIn(slug="inline", image_b64=_png_b64()))
            result = tool_get_sprite(GetSpriteIn(slug="inline", include_image=True))
        finally:
            reset_current_user(tok)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        payload, image_block = result
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["slug"], "inline")
        self.assertIsInstance(image_block, ImageContent)
        self.assertEqual(image_block.type, "image")
        self.assertEqual(image_block.mimeType, "image/png")
        # data is base64-encoded PNG bytes — decode and verify the magic.
        decoded = base64.b64decode(image_block.data)
        self.assertEqual(decoded[:8], b"\x89PNG\r\n\x1a\n")

    def test_include_image_oversize_raises_validation_error(self):
        """The raw-decoded-size cap refuses sprites whose pixel budget
        would dominate the LLM context window. A 400×400 single frame
        (640 KB raw) is well over the 200 KB cap."""
        tok = self._as(self.parent)
        try:
            tool_register_sprite(RegisterSpriteIn(slug="too-big", image_b64=_png_b64((400, 400))))
            with self.assertRaises(MCPValidationError):
                tool_get_sprite(GetSpriteIn(slug="too-big", include_image=True))
            # Without the flag the dict path still works — only the inline
            # path is gated, callers can still read metadata + url.
            result = tool_get_sprite(GetSpriteIn(slug="too-big"))
            self.assertEqual(result["slug"], "too-big")
        finally:
            reset_current_user(tok)


class UpdateSpriteMetadataToolTests(TestCase):
    """v1.2.8: metadata-only edits on an existing sprite without
    regenerating the image. Covers fps tuning (the first use case —
    fix animation speed on already-good sprites) and pack reassignment
    (useful for curation passes)."""

    def setUp(self):
        self.parent = User.objects.create_user(username="meta_parent", password="pw", role="parent", is_staff=True)
        self.child = User.objects.create_user(username="meta_kid", password="pw", role="child")

    def _as_parent(self):
        return set_current_user(self.parent)

    def _as_child(self):
        return set_current_user(self.child)

    def _register_animated(self, slug="anim", fps=8, frame_count=4, pack="test"):
        """Build a small animated sheet and register it so we have a
        target to update. Uses a width divisible by frame_count so
        register_sprite infers per-frame dimensions correctly."""
        png_b64 = _png_b64((frame_count * 32, 32))
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(
                slug=slug,
                image_b64=png_b64,
                pack=pack,
                frame_count=frame_count,
                fps=fps,
                frame_layout="horizontal",
            ))
        finally:
            reset_current_user(tok)

    def test_requires_parent(self):
        self._register_animated(slug="guarded")
        tok = self._as_child()
        try:
            with self.assertRaises(MCPPermissionDenied):
                tool_update_sprite_metadata(UpdateSpriteMetadataIn(slug="guarded", fps=4))
        finally:
            reset_current_user(tok)

    def test_update_fps_changes_row_without_touching_image(self):
        self._register_animated(slug="fps-test", fps=8)
        original = SpriteAsset.objects.get(slug="fps-test")
        original_image_name = original.image.name

        tok = self._as_parent()
        try:
            result = tool_update_sprite_metadata(UpdateSpriteMetadataIn(slug="fps-test", fps=4))
        finally:
            reset_current_user(tok)

        self.assertEqual(result["slug"], "fps-test")
        self.assertEqual(result["fps"], 4)
        updated = SpriteAsset.objects.get(slug="fps-test")
        self.assertEqual(updated.fps, 4)
        # Image blob untouched — same image.name, same content hash.
        self.assertEqual(updated.image.name, original_image_name)

    def test_update_pack_changes_row(self):
        self._register_animated(slug="pack-test", pack="before")
        tok = self._as_parent()
        try:
            result = tool_update_sprite_metadata(UpdateSpriteMetadataIn(slug="pack-test", pack="after"))
        finally:
            reset_current_user(tok)
        self.assertEqual(result["pack"], "after")
        self.assertEqual(SpriteAsset.objects.get(slug="pack-test").pack, "after")

    def test_update_both_fields_in_one_call(self):
        self._register_animated(slug="both-test", fps=8, pack="before")
        tok = self._as_parent()
        try:
            tool_update_sprite_metadata(UpdateSpriteMetadataIn(
                slug="both-test", fps=6, pack="after",
            ))
        finally:
            reset_current_user(tok)
        row = SpriteAsset.objects.get(slug="both-test")
        self.assertEqual(row.fps, 6)
        self.assertEqual(row.pack, "after")

    def test_unknown_slug_raises_mcp_validation_error(self):
        tok = self._as_parent()
        try:
            with self.assertRaises(MCPValidationError):
                tool_update_sprite_metadata(UpdateSpriteMetadataIn(slug="does-not-exist", fps=4))
        finally:
            reset_current_user(tok)

    def test_no_updates_is_rejected_at_schema_layer(self):
        """Both fields None = no-op. Rejected by pydantic so the tool
        never runs with an ambiguous intent."""
        with self.assertRaises(ValidationError):
            UpdateSpriteMetadataIn(slug="any")

    def test_updating_static_sprite_to_nonzero_fps_rejected(self):
        """SpriteAsset.clean() forbids fps>0 on a static sprite
        (frame_count=1). The tool must surface that as
        MCPValidationError, not let the DB silently end up invalid."""
        # Register a static sprite.
        png_b64 = _png_b64((32, 32))
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(
                slug="static-test", image_b64=png_b64,
                frame_count=1, fps=0, frame_layout="horizontal",
            ))
            with self.assertRaises(MCPValidationError):
                tool_update_sprite_metadata(UpdateSpriteMetadataIn(slug="static-test", fps=8))
        finally:
            reset_current_user(tok)
        # Ensure the DB row was NOT mutated despite the attempted update.
        self.assertEqual(SpriteAsset.objects.get(slug="static-test").fps, 0)

    def test_fps_out_of_range_rejected_by_schema(self):
        with self.assertRaises(ValidationError):
            UpdateSpriteMetadataIn(slug="x", fps=99)
        with self.assertRaises(ValidationError):
            UpdateSpriteMetadataIn(slug="x", fps=-1)
