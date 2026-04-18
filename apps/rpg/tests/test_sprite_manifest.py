"""Tests for the shared sprite slicing engine.

Exercises:
- Legacy single-sheet manifest still parses, slices, and round-trips.
- New multi-sheet + loose-file manifest parses and slices correctly.
- Tile-bound and missing-source validation fire before any slice.
- register_asset / register_sheet upsert in-memory and promote the
  dumped YAML to the new schema when a second sheet appears.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase
from PIL import Image

from apps.rpg.content.sprites import (
    DEFAULT_SHEET_ID,
    LooseFile,
    ManifestError,
    Sheet,
    SheetTile,
    dump_manifest,
    load_manifest,
    register_asset,
    register_sheet,
    slice_all,
    validate_sources,
    validate_tile_bounds,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _make_sheet(path: Path, cols: int, rows: int, tile: int) -> None:
    """Build a colourful grid PNG so each tile is visually distinct."""
    img = Image.new("RGBA", (cols * tile, rows * tile), (0, 0, 0, 0))
    pixels = img.load()
    for row in range(rows):
        for col in range(cols):
            r = (col * 37) % 256
            g = (row * 53) % 256
            b = ((col + row) * 23) % 256
            for y in range(row * tile, (row + 1) * tile):
                for x in range(col * tile, (col + 1) * tile):
                    pixels[x, y] = (r, g, b, 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _make_solid(path: Path, size: int, colour: tuple[int, int, int, int]) -> None:
    img = Image.new("RGBA", (size, size), colour)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


class LoadManifestTests(SimpleTestCase):
    def test_legacy_schema_parses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "m.yaml"
            _write(manifest_path, (
                "sheet: pack/sheet.png\n"
                "tile_size: 32\n"
                "sprites:\n"
                "  wolf: {col: 0, row: 0}\n"
                "  apple: {col: 3, row: 5}\n"
            ))
            manifest = load_manifest(manifest_path)
        self.assertIn(DEFAULT_SHEET_ID, manifest.sheets)
        self.assertEqual(
            manifest.sheets[DEFAULT_SHEET_ID].file, "reward-icons/pack/sheet.png",
        )
        self.assertEqual(manifest.sheets[DEFAULT_SHEET_ID].tile_size, 32)
        self.assertEqual(
            manifest.sprites["wolf"], SheetTile(DEFAULT_SHEET_ID, 0, 0),
        )

    def test_new_schema_with_loose_and_tile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "m.yaml"
            _write(manifest_path, (
                "sheets:\n"
                "  - id: shikashi\n"
                "    file: reward-icons/pack/a.png\n"
                "    tile_size: 32\n"
                "  - id: pets-2026\n"
                "    file: reward-icons/abby/pets.png\n"
                "    tile_size: 64\n"
                "sprites:\n"
                "  wolf: {sheet: pets-2026, col: 0, row: 0}\n"
                "  tropical-fish: {sheet: shikashi, col: 6, row: 16}\n"
                "  custom: {file: content/rpg/packs/demo/sprites/custom.png}\n"
            ))
            manifest = load_manifest(manifest_path)
        self.assertEqual(len(manifest.sheets), 2)
        self.assertEqual(manifest.sheets["pets-2026"].tile_size, 64)
        self.assertEqual(
            manifest.sprites["wolf"], SheetTile("pets-2026", 0, 0),
        )
        self.assertEqual(
            manifest.sprites["custom"],
            LooseFile(file="content/rpg/packs/demo/sprites/custom.png"),
        )

    def test_mixed_schema_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "m.yaml"
            _write(manifest_path, (
                "sheet: pack/sheet.png\n"
                "tile_size: 32\n"
                "sheets:\n"
                "  - id: a\n"
                "    file: reward-icons/a.png\n"
                "    tile_size: 32\n"
                "sprites: {}\n"
            ))
            with self.assertRaises(ManifestError):
                load_manifest(manifest_path)

    def test_tile_missing_sheet_rejected_in_new_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "m.yaml"
            _write(manifest_path, (
                "sheets:\n"
                "  - id: a\n"
                "    file: reward-icons/a.png\n"
                "    tile_size: 32\n"
                "sprites:\n"
                "  wolf: {col: 0, row: 0}\n"   # no sheet ref
            ))
            with self.assertRaises(ManifestError):
                load_manifest(manifest_path)

    def test_loose_and_sheet_keys_cannot_mix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "m.yaml"
            _write(manifest_path, (
                "sheets:\n"
                "  - id: a\n"
                "    file: reward-icons/a.png\n"
                "    tile_size: 32\n"
                "sprites:\n"
                "  bad: {sheet: a, col: 0, row: 0, file: some.png}\n"
            ))
            with self.assertRaises(ManifestError):
                load_manifest(manifest_path)


class ValidateAndSliceTests(SimpleTestCase):
    def test_validate_and_slice_sheet_tiles_and_loose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet_rel = "reward-icons/demo/a.png"
            loose_rel = "content/rpg/packs/demo/sprites/star.png"
            _make_sheet(root / sheet_rel, cols=4, rows=4, tile=32)
            _make_solid(root / loose_rel, size=48, colour=(255, 0, 0, 255))

            manifest_path = root / "m.yaml"
            _write(manifest_path, (
                "sheets:\n"
                "  - id: demo\n"
                "    file: reward-icons/demo/a.png\n"
                "    tile_size: 32\n"
                "sprites:\n"
                "  tile-a: {sheet: demo, col: 0, row: 0}\n"
                "  tile-b: {sheet: demo, col: 3, row: 3}\n"
                f"  star: {{file: {loose_rel}}}\n"
            ))
            manifest = load_manifest(manifest_path)
            self.assertEqual(validate_sources(manifest, root), [])
            self.assertEqual(validate_tile_bounds(manifest, root), [])

            out_dir = root / "out"
            stats = slice_all(manifest, root, out_dir)
            self.assertEqual(stats.sliced, 2)
            self.assertEqual(stats.copied, 1)
            self.assertEqual(stats.skipped, 0)
            for slug in ("tile-a", "tile-b", "star"):
                self.assertTrue((out_dir / f"{slug}.png").exists())

            # Loose file preserves source bytes.
            self.assertEqual(
                (out_dir / "star.png").read_bytes(),
                (root / loose_rel).read_bytes(),
            )

            # Re-run without force skips; with force re-writes.
            stats2 = slice_all(manifest, root, out_dir)
            self.assertEqual(stats2.skipped, 3)
            stats3 = slice_all(manifest, root, out_dir, force=True)
            self.assertEqual(stats3.sliced, 2)
            self.assertEqual(stats3.copied, 1)

    def test_tile_out_of_bounds_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_sheet(root / "reward-icons/demo/a.png", cols=2, rows=2, tile=32)
            manifest_path = root / "m.yaml"
            _write(manifest_path, (
                "sheets:\n"
                "  - id: demo\n"
                "    file: reward-icons/demo/a.png\n"
                "    tile_size: 32\n"
                "sprites:\n"
                "  bad: {sheet: demo, col: 5, row: 0}\n"
            ))
            manifest = load_manifest(manifest_path)
            errors = validate_tile_bounds(manifest, root)
            self.assertTrue(any("bad" in e for e in errors))

    def test_missing_source_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "m.yaml"
            _write(manifest_path, (
                "sheets:\n"
                "  - id: demo\n"
                "    file: reward-icons/demo/a.png\n"
                "    tile_size: 32\n"
                "sprites:\n"
                "  bad-tile: {sheet: demo, col: 0, row: 0}\n"
                "  bad-loose: {file: content/rpg/packs/demo/sprites/nope.png}\n"
            ))
            manifest = load_manifest(manifest_path)
            errors = validate_sources(manifest, root)
            self.assertEqual(len(errors), 2)


class RegisterAndDumpTests(SimpleTestCase):
    def test_register_sheet_promotes_to_multi_sheet_on_second_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "m.yaml"
            _write(manifest_path, (
                "sheet: pack/a.png\n"
                "tile_size: 32\n"
                "sprites:\n"
                "  alpha: {col: 0, row: 0}\n"
            ))
            manifest = load_manifest(manifest_path)
            # Adding a second (non-default) sheet upgrades the schema.
            register_sheet(
                manifest, id="beta", file="reward-icons/beta.png", tile_size=64,
            )
            register_asset(
                manifest, slug="beta-0", source=SheetTile("beta", 0, 0),
            )
            out_path = root / "out.yaml"
            dump_manifest(manifest, out_path)
            text = out_path.read_text(encoding="utf-8")
            self.assertIn("sheets:", text)
            self.assertIn("beta", text)
            # Re-parsing round-trips cleanly.
            reparsed = load_manifest(out_path)
            self.assertIn("beta", reparsed.sheets)
            self.assertIn(DEFAULT_SHEET_ID, reparsed.sheets)

    def test_register_asset_replaces_existing_slug(self) -> None:
        from apps.rpg.content.sprites import Manifest
        m = Manifest(_multi_sheet=True)
        m.sheets["a"] = Sheet(id="a", file="reward-icons/a.png", tile_size=32)
        register_asset(m, slug="x", source=SheetTile("a", 0, 0))
        register_asset(m, slug="x", source=SheetTile("a", 1, 1))  # replace
        self.assertEqual(m.sprites["x"], SheetTile("a", 1, 1))

    def test_register_asset_unknown_sheet_rejected(self) -> None:
        from apps.rpg.content.sprites import Manifest
        m = Manifest(_multi_sheet=True)
        with self.assertRaises(ManifestError):
            register_asset(m, slug="x", source=SheetTile("missing", 0, 0))

    def test_dump_preserves_legacy_schema_when_no_second_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "m.yaml"
            _write(manifest_path, (
                "sheet: pack/a.png\n"
                "tile_size: 32\n"
                "sprites:\n"
                "  alpha: {col: 0, row: 0}\n"
            ))
            manifest = load_manifest(manifest_path)
            out_path = root / "out.yaml"
            dump_manifest(manifest, out_path)
            text = out_path.read_text(encoding="utf-8")
            self.assertIn("sheet:", text)
            # No "sheets:" list key — stays legacy.
            self.assertNotIn("sheets:", text)
