import base64
import io
from unittest.mock import patch

from PIL import Image
from django.test import TestCase, override_settings
from pydantic import ValidationError

from apps.accounts.models import User
from apps.rpg.models import SpriteAsset

from config.tests.factories import make_family

from apps.mcp_server.context import set_current_user, reset_current_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    RegisterSpriteIn,
    RegisterSpriteBatchIn,
    ListSpritesIn,
    DeleteSpriteIn,
    AnimatedSpriteTileDecl,
    GenerateSpriteSheetIn,
    GetSpriteIn,
    UpdateSpriteMetadataIn,
)
from apps.mcp_server.tools.sprite_authoring import (
    register_sprite as tool_register_sprite,
    register_sprite_batch as tool_register_sprite_batch,
    list_sprites as tool_list_sprites,
    delete_sprite as tool_delete_sprite,
    generate_sprite_sheet as tool_generate_sprite_sheet,
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
        tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
        self.assertIn("register_sprite", tool_names)
        self.assertIn("register_sprite_batch", tool_names)
        self.assertIn("list_sprites", tool_names)
        self.assertIn("delete_sprite", tool_names)
        self.assertIn("generate_sprite_sheet", tool_names)
        self.assertIn("update_sprite_metadata", tool_names)
        self.assertIn("get_sprite", tool_names)
        self.assertIn("get_sprite_prompting_playbook", tool_names)


class GetSpriteToolTests(TestCase):
    """Read-shape parity for the new chat-side critique loop. ``list_sprites``
    stays lean; ``get_sprite`` returns the full authoring shape so a chat
    agent can read what was sent to Gemini and compare against the rendered
    image at ``url``.
    """

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
            # register_sprite doesn't write authoring inputs (those come from
            # generate_sprite_sheet) — manually stamp them so we can verify
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
        even though they can't ``generate_sprite_sheet``. Sprites are
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


def _png_bytes(size=(128, 128)):
    img = Image.new("RGBA", size, (100, 50, 150, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@override_settings(GEMINI_API_KEY="test-key")
class GenerateSpriteSheetToolTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="gen_parent", password="pw", role="parent", is_staff=True)
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

    def test_motion_defaults_to_idle(self):
        m = GenerateSpriteSheetIn(slug="ok", prompt="pixel-art fox")
        self.assertEqual(m.motion, "idle")

    def test_motion_accepts_walk_and_bounce(self):
        for motion in ("walk", "bounce", "idle"):
            m = GenerateSpriteSheetIn(slug="ok", prompt="pixel-art fox", motion=motion)
            self.assertEqual(m.motion, motion)

    def test_motion_rejects_unknown_value(self):
        with self.assertRaises(ValidationError):
            GenerateSpriteSheetIn(slug="x", prompt="pixel-art fox", motion="sprint")

    def test_reference_image_url_defaults_to_none(self):
        m = GenerateSpriteSheetIn(slug="ok", prompt="pixel-art fox")
        self.assertIsNone(m.reference_image_url)

    def test_reference_image_url_accepts_https_url(self):
        m = GenerateSpriteSheetIn(
            slug="ok",
            prompt="pixel-art fox",
            reference_image_url="https://s3.neato.digital/abby-sprites/rpg-sprites/turtle-abc.png",
        )
        self.assertEqual(
            m.reference_image_url,
            "https://s3.neato.digital/abby-sprites/rpg-sprites/turtle-abc.png",
        )

    def test_return_debug_raw_defaults_false(self):
        m = GenerateSpriteSheetIn(slug="ok", prompt="pixel-art fox")
        self.assertFalse(m.return_debug_raw)

    def test_return_debug_raw_accepts_true(self):
        m = GenerateSpriteSheetIn(
            slug="ok", prompt="pixel-art fox", return_debug_raw=True,
        )
        self.assertTrue(m.return_debug_raw)
