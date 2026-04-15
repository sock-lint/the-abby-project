"""Slice individual 32x32 RPG sprites from a Shikashi spritesheet.

Reads scripts/sprite_manifest.yaml (slug → {col, row}) and writes
frontend/src/assets/rpg-sprites/<slug>.png for each entry.

Usage:
    python scripts/slice_rpg_sprites.py            # skip existing files
    python scripts/slice_rpg_sprites.py --force    # overwrite

The manifest lists only the sprites we actually use in content YAML;
unused tiles are not sliced.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "scripts" / "sprite_manifest.yaml"
SHEET_DIR = REPO_ROOT / "reward-icons"
OUTPUT_DIR = REPO_ROOT / "frontend" / "src" / "assets" / "rpg-sprites"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing sprite files instead of skipping them.",
    )
    args = parser.parse_args()

    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)

    sheet_path = SHEET_DIR / manifest["sheet"]
    tile_size = int(manifest["tile_size"])
    sprites = manifest["sprites"]

    if not sheet_path.exists():
        print(f"ERROR: spritesheet not found: {sheet_path}", file=sys.stderr)
        return 1

    sheet = Image.open(sheet_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sliced = 0
    skipped = 0
    for slug, coord in sprites.items():
        out_path = OUTPUT_DIR / f"{slug}.png"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        col = int(coord["col"])
        row = int(coord["row"])
        x = col * tile_size
        y = row * tile_size
        tile = sheet.crop((x, y, x + tile_size, y + tile_size))
        tile.save(out_path)
        sliced += 1

    print(f"Sliced {sliced}, skipped {skipped} (use --force to overwrite).")
    print(f"Output: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
