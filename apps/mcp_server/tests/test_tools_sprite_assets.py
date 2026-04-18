"""Tests for the register_sprite_assets MCP tool.

Covers:
- Happy-path register + slice of sheet tiles and loose files.
- Path containment rejects assets outside the pack's allowed roots.
- Parent-only gating.
- Rejects unknown sheet refs, out-of-bounds tiles, and missing sources
  BEFORE mutating the on-disk manifest.
- Idempotency: re-registering the same slug leaves the manifest clean
  and only re-slices when ``force=True``.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from PIL import Image
from pydantic import ValidationError as PydanticValidationError

from apps.accounts.models import User
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import (
    RegisterSpriteAssetsIn,
    SheetDecl,
    SpriteLooseDecl,
    SpriteTileDecl,
)
from apps.mcp_server.tools import sprite_assets as sa
from apps.rpg.content.sprites import load_manifest


_VALIDATION_ERRORS = (MCPValidationError, PydanticValidationError)


def _make_sheet(path: Path, cols: int, rows: int, tile: int) -> None:
    img = Image.new("RGBA", (cols * tile, rows * tile), (0, 0, 0, 0))
    pixels = img.load()
    for row in range(rows):
        for col in range(cols):
            r = (col * 37) % 256
            g = (row * 53) % 256
            for y in range(row * tile, (row + 1) * tile):
                for x in range(col * tile, (col + 1) * tile):
                    pixels[x, y] = (r, g, 128, 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _make_solid(path: Path, size: int) -> None:
    img = Image.new("RGBA", (size, size), (255, 50, 50, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


class _SpritesMixin(TestCase):
    """Redirect BASE_DIR to a tmp dir so each test owns its asset roots."""

    def setUp(self) -> None:
        super().setUp()
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp_sprites_test_"))
        self._override = override_settings(BASE_DIR=str(self.tmp))
        self._override.enable()

    def tearDown(self) -> None:
        self._override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()


class HappyPathTests(_SpritesMixin):
    def test_register_and_slice_multi_source_pack(self) -> None:
        # Sheet under the pack's allowed sheet root.
        _make_sheet(
            self.tmp / "reward-icons" / "demo" / "sheet.png",
            cols=4, rows=4, tile=32,
        )
        # Loose file under the pack's sprites dir.
        loose_rel = "content/rpg/packs/demo/sprites/star.png"
        _make_solid(self.tmp / loose_rel, size=48)

        with override_user(self.parent):
            result = sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="demo",
                sheets=[SheetDecl(
                    id="demo-sheet",
                    file="reward-icons/demo/sheet.png",
                    tile_size=32,
                )],
                tiles=[
                    SpriteTileDecl(slug="tile-a", sheet="demo-sheet", col=0, row=0),
                    SpriteTileDecl(slug="tile-b", sheet="demo-sheet", col=3, row=3),
                ],
                loose=[SpriteLooseDecl(slug="star", file=loose_rel)],
            ))

        self.assertEqual(result["pack"], "demo")
        self.assertEqual(result["sliced"], 2)
        self.assertEqual(result["copied"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(
            set(result["sprites_registered"]), {"tile-a", "tile-b", "star"},
        )

        # Sliced/copied files exist.
        out_dir = self.tmp / "frontend" / "src" / "assets" / "rpg-sprites"
        for slug in ("tile-a", "tile-b", "star"):
            self.assertTrue((out_dir / f"{slug}.png").exists())

        # Manifest round-trips through the shared loader.
        manifest = load_manifest(self.tmp / "scripts" / "sprite_manifest.yaml")
        self.assertIn("demo-sheet", manifest.sheets)
        self.assertEqual(set(manifest.sprites), {"tile-a", "tile-b", "star"})

    def test_idempotent_register_skips_sliced_outputs(self) -> None:
        _make_sheet(
            self.tmp / "reward-icons" / "demo" / "sheet.png",
            cols=2, rows=2, tile=16,
        )
        payload = RegisterSpriteAssetsIn(
            pack="demo",
            sheets=[SheetDecl(
                id="s", file="reward-icons/demo/sheet.png", tile_size=16,
            )],
            tiles=[SpriteTileDecl(slug="x", sheet="s", col=0, row=0)],
        )
        with override_user(self.parent):
            sa.register_sprite_assets(payload)
            # Second call without force: the `only` list still targets the
            # slug, but slice_all sees an existing file → counts as skipped.
            second = sa.register_sprite_assets(payload)
        self.assertEqual(second["sliced"], 0)
        self.assertEqual(second["skipped"], 1)

    def test_force_reslice_rewrites_existing(self) -> None:
        sheet_path = self.tmp / "reward-icons" / "demo" / "sheet.png"
        _make_sheet(sheet_path, cols=2, rows=2, tile=16)
        payload = RegisterSpriteAssetsIn(
            pack="demo",
            sheets=[SheetDecl(
                id="s", file="reward-icons/demo/sheet.png", tile_size=16,
            )],
            tiles=[SpriteTileDecl(slug="x", sheet="s", col=0, row=0)],
        )
        with override_user(self.parent):
            sa.register_sprite_assets(payload)
            payload_force = payload.model_copy(update={"force": True})
            result = sa.register_sprite_assets(payload_force)
        self.assertEqual(result["sliced"], 1)
        self.assertEqual(result["skipped"], 0)


class SafetyRailTests(_SpritesMixin):
    def test_child_cannot_register(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="demo",
                sheets=[SheetDecl(
                    id="s", file="reward-icons/demo/a.png", tile_size=32,
                )],
            ))

    def test_sheet_outside_allowed_root_rejected(self) -> None:
        # Sheet file sitting at the repo root is outside the pack roots.
        _make_sheet(self.tmp / "rogue.png", cols=2, rows=2, tile=16)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="demo",
                sheets=[SheetDecl(
                    id="s", file="rogue.png", tile_size=16,
                )],
                tiles=[SpriteTileDecl(slug="x", sheet="s", col=0, row=0)],
            ))

    def test_loose_outside_pack_sprites_rejected(self) -> None:
        # Loose files may only live under the pack's own sprites/ dir.
        _make_solid(self.tmp / "reward-icons" / "demo" / "loose.png", size=16)
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="demo",
                loose=[SpriteLooseDecl(
                    slug="bad", file="reward-icons/demo/loose.png",
                )],
            ))

    def test_out_of_bounds_tile_rejected_before_write(self) -> None:
        manifest_path = self.tmp / "scripts" / "sprite_manifest.yaml"
        self.assertFalse(manifest_path.exists())
        _make_sheet(
            self.tmp / "reward-icons" / "demo" / "sheet.png",
            cols=2, rows=2, tile=16,
        )
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="demo",
                sheets=[SheetDecl(
                    id="s", file="reward-icons/demo/sheet.png", tile_size=16,
                )],
                tiles=[SpriteTileDecl(slug="x", sheet="s", col=5, row=5)],
            ))
        # Pre-flight failure means the manifest was never written.
        self.assertFalse(manifest_path.exists())

    def test_missing_loose_source_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="demo",
                loose=[SpriteLooseDecl(
                    slug="x",
                    file="content/rpg/packs/demo/sprites/missing.png",
                )],
            ))

    def test_tile_referencing_unknown_sheet_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="demo",
                tiles=[SpriteTileDecl(
                    slug="x", sheet="not-registered", col=0, row=0,
                )],
            ))

    def test_empty_payload_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(pack="demo"))

    def test_bad_pack_name_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(_VALIDATION_ERRORS):
            sa.register_sprite_assets(RegisterSpriteAssetsIn(
                pack="Demo/../evil",
                sheets=[SheetDecl(
                    id="s", file="reward-icons/demo/a.png", tile_size=16,
                )],
            ))
