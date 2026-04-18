"""Slice RPG sprites declared in ``scripts/sprite_manifest.yaml``.

Thin CLI wrapper around ``apps.rpg.content.sprites.slice_all``. Supports
both sheet-tile sprites and loose PNGs, and multiple sheets with
different tile sizes.

Usage:
    python scripts/slice_rpg_sprites.py            # skip existing files
    python scripts/slice_rpg_sprites.py --force    # overwrite
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script without installing the project — add the repo
# root to sys.path so ``apps.rpg.content.sprites`` imports cleanly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.rpg.content.sprites import (  # noqa: E402  (path setup above)
    ManifestError,
    load_manifest,
    slice_all,
    validate_sources,
    validate_tile_bounds,
)


MANIFEST_PATH = REPO_ROOT / "scripts" / "sprite_manifest.yaml"
OUTPUT_DIR = REPO_ROOT / "frontend" / "src" / "assets" / "rpg-sprites"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing sprite files instead of skipping them.",
    )
    args = parser.parse_args()

    try:
        manifest = load_manifest(MANIFEST_PATH)
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors = validate_sources(manifest, REPO_ROOT)
    if errors:
        for line in errors:
            print(f"ERROR: {line}", file=sys.stderr)
        return 1

    errors = validate_tile_bounds(manifest, REPO_ROOT)
    if errors:
        for line in errors:
            print(f"ERROR: {line}", file=sys.stderr)
        return 1

    try:
        stats = slice_all(manifest, REPO_ROOT, OUTPUT_DIR, force=args.force)
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Sliced {stats.sliced}, copied {stats.copied}, skipped "
        f"{stats.skipped} (use --force to overwrite).",
    )
    print(f"Output: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
