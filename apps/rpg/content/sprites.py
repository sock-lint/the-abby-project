"""Shared slicing engine for RPG sprite assets.

The ``scripts/slice_rpg_sprites.py`` CLI and the ``register_sprite_assets``
MCP tool both route through this module so there is one implementation of
manifest parsing + slicing.

Two source kinds are supported:

* **Sheet tile** — a tile at ``(col, row)`` on a named spritesheet with a
  uniform ``tile_size``. Sliced via PIL ``Image.crop``.
* **Loose file** — a standalone PNG. Copied byte-for-byte to the output
  directory; useful for assets that aren't laid out on a regular grid.

The manifest YAML accepts both a legacy single-sheet shape (the initial
Shikashi manifest) and a multi-sheet / loose-file shape. See
``load_manifest`` for the parser.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Union

import yaml


DEFAULT_SHEET_ID = "__default__"
LEGACY_SHEET_DIR = "reward-icons"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sheet:
    """A spritesheet with a uniform tile size."""
    id: str
    file: str        # repo-relative path
    tile_size: int


@dataclass(frozen=True)
class SheetTile:
    """Sprite source: one tile on a named sheet."""
    sheet_id: str
    col: int
    row: int


@dataclass(frozen=True)
class LooseFile:
    """Sprite source: a standalone PNG file."""
    file: str        # repo-relative path


Source = Union[SheetTile, LooseFile]


@dataclass
class Manifest:
    sheets: dict[str, Sheet] = field(default_factory=dict)
    sprites: dict[str, Source] = field(default_factory=dict)
    # Preserves the source schema shape so ``dump_manifest`` can round-trip
    # a legacy file without silently upgrading it. ``False`` means legacy.
    _multi_sheet: bool = False


@dataclass
class SliceStats:
    sliced: int = 0
    skipped: int = 0
    copied: int = 0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> Manifest:
    """Parse a sprite manifest YAML file.

    Accepts either the legacy single-sheet shape::

        sheet: "pack2/#1 - Transparent Icons.png"  # relative to reward-icons/
        tile_size: 32
        sprites:
          wolf: {col: 0, row: 0}

    or the new multi-sheet + loose-file shape::

        sheets:
          - id: shikashi
            file: "reward-icons/pack2/#1 - Transparent Icons.png"
            tile_size: 32
          - id: abby-pets
            file: "reward-icons/abby/pets.png"
            tile_size: 64
        sprites:
          wolf:        {sheet: abby-pets, col: 0, row: 0}
          custom-icon: {file: "content/rpg/packs/my-pack/sprites/custom.png"}

    Both forms land in the same in-memory ``Manifest``. Paths on sheets and
    loose files are always repo-relative in the unified form — the legacy
    ``sheet:`` path is prefixed with ``reward-icons/`` so downstream code
    only deals with one convention.
    """
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ManifestError(
            f"{path}: top-level must be a mapping, got {type(raw).__name__}.",
        )

    sprites_raw = raw.get("sprites") or {}
    if not isinstance(sprites_raw, dict):
        raise ManifestError(f"{path}: 'sprites' must be a mapping.")

    # Decide which shape we're reading. If ``sheets:`` (list) is present we
    # use the new schema; if ``sheet:`` (scalar) is present we're in legacy
    # mode. Having both is a configuration error.
    has_new = "sheets" in raw
    has_legacy = "sheet" in raw or "tile_size" in raw
    if has_new and has_legacy:
        raise ManifestError(
            f"{path}: cannot mix legacy ('sheet', 'tile_size') and new "
            f"('sheets:') keys in the same manifest.",
        )

    manifest = Manifest()

    if has_new:
        manifest._multi_sheet = True
        sheets_raw = raw.get("sheets") or []
        if not isinstance(sheets_raw, list):
            raise ManifestError(f"{path}: 'sheets' must be a list.")
        for i, entry in enumerate(sheets_raw):
            if not isinstance(entry, dict):
                raise ManifestError(
                    f"{path}: sheets[{i}] must be a mapping.",
                )
            sheet_id = str(entry.get("id", "")).strip()
            sheet_file = str(entry.get("file", "")).strip()
            try:
                tile_size = int(entry.get("tile_size"))
            except (TypeError, ValueError):
                raise ManifestError(
                    f"{path}: sheets[{i}].tile_size must be a positive int.",
                )
            if not sheet_id or not sheet_file or tile_size <= 0:
                raise ManifestError(
                    f"{path}: sheets[{i}] needs non-empty id/file and "
                    f"tile_size > 0.",
                )
            if sheet_id in manifest.sheets:
                raise ManifestError(
                    f"{path}: duplicate sheet id {sheet_id!r}.",
                )
            manifest.sheets[sheet_id] = Sheet(
                id=sheet_id, file=sheet_file, tile_size=tile_size,
            )
    elif has_legacy:
        sheet_file = str(raw.get("sheet", "")).strip()
        try:
            tile_size = int(raw.get("tile_size"))
        except (TypeError, ValueError):
            raise ManifestError(f"{path}: legacy 'tile_size' missing or invalid.")
        if not sheet_file or tile_size <= 0:
            raise ManifestError(
                f"{path}: legacy manifest needs 'sheet' + 'tile_size' > 0.",
            )
        # Legacy sheet paths are relative to reward-icons/; normalize.
        resolved_file = f"{LEGACY_SHEET_DIR}/{sheet_file}"
        manifest.sheets[DEFAULT_SHEET_ID] = Sheet(
            id=DEFAULT_SHEET_ID, file=resolved_file, tile_size=tile_size,
        )
    # else: sprite-only manifest with no sheets → only loose files allowed.

    for slug, entry in sprites_raw.items():
        if not isinstance(entry, dict):
            raise ManifestError(
                f"{path}: sprite {slug!r} must be a mapping.",
            )
        if "file" in entry:
            file_str = str(entry["file"]).strip()
            if not file_str:
                raise ManifestError(
                    f"{path}: sprite {slug!r} has empty 'file'.",
                )
            if "col" in entry or "row" in entry or "sheet" in entry:
                raise ManifestError(
                    f"{path}: sprite {slug!r} mixes 'file' with sheet-tile "
                    f"keys ('col'/'row'/'sheet').",
                )
            manifest.sprites[slug] = LooseFile(file=file_str)
            continue

        # Sheet-tile entry.
        if "col" not in entry or "row" not in entry:
            raise ManifestError(
                f"{path}: sprite {slug!r} needs 'col' + 'row' (or 'file').",
            )
        try:
            col = int(entry["col"])
            row = int(entry["row"])
        except (TypeError, ValueError):
            raise ManifestError(
                f"{path}: sprite {slug!r} has non-integer col/row.",
            )
        if col < 0 or row < 0:
            raise ManifestError(
                f"{path}: sprite {slug!r} has negative col/row.",
            )
        if has_new:
            sheet_id = str(entry.get("sheet", "")).strip()
            if not sheet_id:
                raise ManifestError(
                    f"{path}: sprite {slug!r} must name a 'sheet' when using "
                    f"the multi-sheet schema.",
                )
            if sheet_id not in manifest.sheets:
                raise ManifestError(
                    f"{path}: sprite {slug!r} references unknown sheet "
                    f"{sheet_id!r}.",
                )
        else:
            sheet_id = DEFAULT_SHEET_ID
            if DEFAULT_SHEET_ID not in manifest.sheets:
                raise ManifestError(
                    f"{path}: sprite {slug!r} uses col/row but no default "
                    f"sheet is defined.",
                )
        manifest.sprites[slug] = SheetTile(
            sheet_id=sheet_id, col=col, row=row,
        )

    return manifest


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def dump_manifest(manifest: Manifest, path: Path) -> None:
    """Write ``manifest`` back to YAML.

    Preserves the source schema (legacy vs. new) so a round-trip of an
    unchanged manifest does not rewrite its top-level shape. Sprite
    ordering is preserved (python dicts are insertion-ordered).
    """
    if manifest._multi_sheet or len(manifest.sheets) != 1 or (
        DEFAULT_SHEET_ID not in manifest.sheets
    ):
        # New schema: emit ``sheets:`` + per-sprite ``sheet`` refs.
        sheets_out = [
            {"id": s.id, "file": s.file, "tile_size": s.tile_size}
            for s in manifest.sheets.values()
        ]
        sprites_out: dict[str, dict] = {}
        for slug, source in manifest.sprites.items():
            if isinstance(source, SheetTile):
                sprites_out[slug] = {
                    "sheet": source.sheet_id,
                    "col": source.col,
                    "row": source.row,
                }
            else:
                sprites_out[slug] = {"file": source.file}
        out = {"sheets": sheets_out, "sprites": sprites_out}
    else:
        # Legacy schema: one synthetic default sheet, no loose files allowed.
        default_sheet = manifest.sheets[DEFAULT_SHEET_ID]
        legacy_sheet = default_sheet.file
        if legacy_sheet.startswith(f"{LEGACY_SHEET_DIR}/"):
            legacy_sheet = legacy_sheet[len(LEGACY_SHEET_DIR) + 1:]
        sprites_out = {}
        for slug, source in manifest.sprites.items():
            if not isinstance(source, SheetTile):
                # Loose file in a legacy manifest → upgrade silently to the
                # new schema so round-tripping doesn't lose data.
                return dump_manifest(
                    _promote_to_multi_sheet(manifest), path,
                )
            sprites_out[slug] = {"col": source.col, "row": source.row}
        out = {
            "sheet": legacy_sheet,
            "tile_size": default_sheet.tile_size,
            "sprites": sprites_out,
        }

    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            out,
            fh,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )


def _promote_to_multi_sheet(manifest: Manifest) -> Manifest:
    """Return a copy of ``manifest`` in the new-schema form."""
    new = Manifest(
        sheets=dict(manifest.sheets),
        sprites=dict(manifest.sprites),
        _multi_sheet=True,
    )
    return new


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def register_asset(
    manifest: Manifest,
    *,
    slug: str,
    source: Source,
    replace: bool = True,
) -> None:
    """Add or update a sprite entry in-memory.

    When ``replace`` is False, an existing slug raises ``ManifestError``.
    When True (default), the new source silently overwrites the old one —
    matching the upsert semantics of the YAML content loader.
    """
    if not slug or not isinstance(slug, str):
        raise ManifestError("register_asset: slug must be a non-empty string.")
    if slug in manifest.sprites and not replace:
        raise ManifestError(
            f"register_asset: sprite {slug!r} already registered.",
        )
    if isinstance(source, SheetTile):
        if source.sheet_id not in manifest.sheets:
            raise ManifestError(
                f"register_asset: sprite {slug!r} references unknown sheet "
                f"{source.sheet_id!r}.",
            )
        if source.col < 0 or source.row < 0:
            raise ManifestError(
                f"register_asset: sprite {slug!r} has negative col/row.",
            )
    manifest.sprites[slug] = source


def register_sheet(
    manifest: Manifest,
    *,
    id: str,
    file: str,
    tile_size: int,
    replace: bool = True,
) -> None:
    """Add or update a sheet entry in-memory."""
    if not id or not file:
        raise ManifestError("register_sheet: id and file are required.")
    if tile_size <= 0:
        raise ManifestError("register_sheet: tile_size must be > 0.")
    if id in manifest.sheets and not replace:
        raise ManifestError(f"register_sheet: sheet {id!r} already exists.")
    manifest.sheets[id] = Sheet(id=id, file=file, tile_size=tile_size)
    # Registering any second sheet flips the manifest into multi-sheet mode
    # so dump_manifest emits the new schema.
    if len(manifest.sheets) > 1 or id != DEFAULT_SHEET_ID:
        manifest._multi_sheet = True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_sources(manifest: Manifest, repo_root: Path) -> list[str]:
    """Check that every referenced sheet and loose file actually exists.

    Returns a list of error messages (empty == valid). Callers decide
    whether to raise — the MCP tool raises ``MCPValidationError``, the
    CLI prints the list and exits non-zero.
    """
    errors: list[str] = []
    for sheet in manifest.sheets.values():
        full = (repo_root / sheet.file).resolve()
        if not full.exists():
            errors.append(f"sheet {sheet.id!r}: file not found: {sheet.file}")
    for slug, source in manifest.sprites.items():
        if isinstance(source, LooseFile):
            full = (repo_root / source.file).resolve()
            if not full.exists():
                errors.append(
                    f"sprite {slug!r}: loose file not found: {source.file}",
                )
    return errors


def validate_tile_bounds(manifest: Manifest, repo_root: Path) -> list[str]:
    """Check that every sheet-tile coord lands inside its sheet's image.

    Opens each referenced sheet once with PIL to read dimensions. Returns
    a list of error messages; empty list means every tile is in bounds.
    """
    from PIL import Image  # local import so non-slicing callers don't pay

    errors: list[str] = []
    dims_cache: dict[str, tuple[int, int]] = {}
    for slug, source in manifest.sprites.items():
        if not isinstance(source, SheetTile):
            continue
        sheet = manifest.sheets.get(source.sheet_id)
        if sheet is None:
            errors.append(
                f"sprite {slug!r}: references unknown sheet "
                f"{source.sheet_id!r}",
            )
            continue
        if sheet.file not in dims_cache:
            full = (repo_root / sheet.file).resolve()
            if not full.exists():
                # validate_sources already catches this; skip.
                continue
            with Image.open(full) as img:
                dims_cache[sheet.file] = (img.width, img.height)
        width, height = dims_cache[sheet.file]
        x1 = source.col * sheet.tile_size + sheet.tile_size
        y1 = source.row * sheet.tile_size + sheet.tile_size
        if x1 > width or y1 > height:
            errors.append(
                f"sprite {slug!r}: tile ({source.col}, {source.row}) at "
                f"size {sheet.tile_size} exceeds sheet "
                f"{sheet.file} dims {width}×{height}.",
            )
    return errors


# ---------------------------------------------------------------------------
# Slicing
# ---------------------------------------------------------------------------


def slice_all(
    manifest: Manifest,
    repo_root: Path,
    output_dir: Path,
    *,
    force: bool = False,
    only: Optional[Iterable[str]] = None,
) -> SliceStats:
    """Materialize every sprite in the manifest into ``output_dir``.

    Sheet tiles are cropped with PIL; loose files are copied byte-for-byte.
    Existing output files are skipped unless ``force=True`` (matches the
    legacy CLI behaviour).

    ``only`` limits the operation to a subset of slugs — used by the MCP
    tool when only a handful of new sprites were just registered, so we
    don't re-slice the whole catalog on every call.
    """
    from PIL import Image  # local import keeps test fixtures cheap

    output_dir.mkdir(parents=True, exist_ok=True)
    stats = SliceStats()

    selected: Iterable[str]
    if only is None:
        selected = list(manifest.sprites.keys())
    else:
        selected = list(only)
        for slug in selected:
            if slug not in manifest.sprites:
                raise ManifestError(
                    f"slice_all: slug {slug!r} not registered in manifest.",
                )

    # Cache open sheets so we don't re-open on every tile.
    sheet_images: dict[str, "Image.Image"] = {}
    try:
        for slug in selected:
            out_path = output_dir / f"{slug}.png"
            if out_path.exists() and not force:
                stats.skipped += 1
                continue
            source = manifest.sprites[slug]
            if isinstance(source, LooseFile):
                src_full = (repo_root / source.file).resolve()
                if not src_full.exists():
                    raise ManifestError(
                        f"slice_all: sprite {slug!r} loose file missing: "
                        f"{source.file}",
                    )
                shutil.copyfile(src_full, out_path)
                stats.copied += 1
                continue
            # SheetTile
            sheet = manifest.sheets[source.sheet_id]
            if sheet.file not in sheet_images:
                sheet_full = (repo_root / sheet.file).resolve()
                if not sheet_full.exists():
                    raise ManifestError(
                        f"slice_all: sheet {sheet.id!r} file missing: "
                        f"{sheet.file}",
                    )
                sheet_images[sheet.file] = Image.open(sheet_full)
            sheet_img = sheet_images[sheet.file]
            x = source.col * sheet.tile_size
            y = source.row * sheet.tile_size
            tile = sheet_img.crop(
                (x, y, x + sheet.tile_size, y + sheet.tile_size),
            )
            tile.save(out_path)
            stats.sliced += 1
    finally:
        for img in sheet_images.values():
            img.close()

    return stats


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ManifestError(Exception):
    """Raised when the manifest is malformed or references something missing."""
