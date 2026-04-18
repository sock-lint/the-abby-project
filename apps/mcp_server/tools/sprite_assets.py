"""MCP tool for registering sprite artwork used as ``sprite_key`` values
in RPG content YAML.

Bridges the filesystem-level slicing engine in
``apps.rpg.content.sprites`` with the MCP surface so an LLM can drive the
full "drop in a folder of artwork → new items/pets" flow without leaving
the conversation.

Safety model mirrors the existing ``content_packs.py`` tools:
- Parent-only via ``require_parent``.
- Every referenced path must resolve inside either
  ``reward-icons/<pack>/`` (for sheets) or
  ``content/rpg/packs/<pack>/sprites/`` (for loose files). Anything
  outside those roots is rejected before the manifest is touched.
- The manifest write is staged in-memory; if slicing fails the on-disk
  manifest is never modified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

from apps.rpg.content.sprites import (
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

from ..context import require_parent
from ..errors import MCPValidationError, safe_tool
from ..schemas import RegisterSpriteAssetsIn
from ..server import tool


def _validate_pack_name(pack: str) -> str:
    """Re-use the same pack-name validator as the YAML tools so names stay
    consistent across the MCP surface.

    Imported lazily to avoid a circular-import loop: ``content_packs``
    imports ``tool`` from ``server``, which loads all tool modules —
    including this one — before ``content_packs`` has finished defining
    its top-level names.
    """
    from .content_packs import _validate_pack_name as _impl
    return _impl(pack)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _manifest_path() -> Path:
    return _repo_root() / "scripts" / "sprite_manifest.yaml"


def _sprite_output_dir() -> Path:
    return _repo_root() / "frontend" / "src" / "assets" / "rpg-sprites"


def _allowed_sheet_roots(pack: str) -> list[Path]:
    """Sheet PNGs may live either under ``reward-icons/<pack>/`` or the
    pack's own ``sprites/`` dir. Returning both keeps the surface flexible
    for packs that ship everything inline."""
    root = _repo_root()
    return [
        (root / "reward-icons" / pack).resolve(),
        (root / "content" / "rpg" / "packs" / pack / "sprites").resolve(),
    ]


def _allowed_loose_roots(pack: str) -> list[Path]:
    """Loose PNGs must live under the pack's own ``sprites/`` dir — this
    is where the author drops hand-authored artwork. We intentionally do
    NOT accept ``reward-icons/`` for loose files so sheet and loose-file
    sources stay visually distinct on disk."""
    root = _repo_root()
    return [
        (root / "content" / "rpg" / "packs" / pack / "sprites").resolve(),
    ]


def _validate_inside(path: str, allowed_roots: list[Path], *, label: str) -> Path:
    """Resolve ``path`` (repo-relative) and ensure it lands inside one of
    ``allowed_roots``. Returns the resolved absolute path."""
    if not path:
        raise MCPValidationError(f"{label}: path is required.")
    # Reject absolute paths outright — every on-disk reference in the
    # project is repo-relative.
    candidate = (_repo_root() / path).resolve()
    for allowed in allowed_roots:
        try:
            candidate.relative_to(allowed)
            return candidate
        except ValueError:
            continue
    raise MCPValidationError(
        f"{label}: {path!r} must resolve inside one of "
        f"{[str(r.relative_to(_repo_root())) for r in allowed_roots]}.",
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def register_sprite_assets(params: RegisterSpriteAssetsIn) -> dict[str, Any]:
    """Register spritesheets and sprites for a content pack and slice artwork.

    Workflow:
      1. Validate every referenced sheet/loose-file path is inside the
         pack's allowed roots.
      2. Load the shared manifest (creating an empty one if missing).
      3. Merge in the new sheets + sprite entries (upsert by id/slug).
      4. Validate every referenced file exists and every tile coord is
         in bounds — fail BEFORE touching the on-disk manifest.
      5. Slice tiles / copy loose PNGs into
         ``frontend/src/assets/rpg-sprites/<slug>.png``.
      6. Write the merged manifest back to disk.

    Returns structured stats plus the list of slugs that were registered.
    The ``sprite_key`` values the LLM drafts in the pack YAML should match
    one of those slugs.
    """
    require_parent()
    pack = _validate_pack_name(params.pack)

    if not (params.sheets or params.tiles or params.loose):
        raise MCPValidationError(
            "At least one of sheets, tiles, or loose must be non-empty.",
        )

    # Containment checks up-front.
    sheet_roots = _allowed_sheet_roots(pack)
    loose_roots = _allowed_loose_roots(pack)
    for sheet_decl in params.sheets:
        _validate_inside(
            sheet_decl.file, sheet_roots,
            label=f"sheets[{sheet_decl.id!r}]",
        )
    for loose_decl in params.loose:
        _validate_inside(
            loose_decl.file, loose_roots,
            label=f"loose[{loose_decl.slug!r}]",
        )

    # Load or start a manifest, keeping the on-disk shape intact.
    manifest_path = _manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        try:
            manifest = load_manifest(manifest_path)
        except ManifestError as exc:
            raise MCPValidationError(
                f"sprite manifest at {manifest_path} is malformed: {exc}",
            )
    else:
        from apps.rpg.content.sprites import Manifest
        manifest = Manifest(_multi_sheet=True)

    # Merge sheets first so tile sprites can reference them.
    for sheet_decl in params.sheets:
        register_sheet(
            manifest,
            id=sheet_decl.id,
            file=sheet_decl.file,
            tile_size=sheet_decl.tile_size,
        )

    # Merge sprites.
    new_slugs: list[str] = []
    for tile_decl in params.tiles:
        if tile_decl.sheet not in manifest.sheets:
            raise MCPValidationError(
                f"tile {tile_decl.slug!r}: sheet id {tile_decl.sheet!r} is "
                f"not registered (include it in 'sheets' or ensure it "
                f"already exists in the manifest).",
            )
        register_asset(
            manifest,
            slug=tile_decl.slug,
            source=SheetTile(
                sheet_id=tile_decl.sheet, col=tile_decl.col, row=tile_decl.row,
            ),
        )
        new_slugs.append(tile_decl.slug)
    for loose_decl in params.loose:
        register_asset(
            manifest,
            slug=loose_decl.slug,
            source=LooseFile(file=loose_decl.file),
        )
        new_slugs.append(loose_decl.slug)

    # Pre-flight: every referenced file must exist, every tile in bounds.
    repo_root = _repo_root()
    src_errors = validate_sources(manifest, repo_root)
    if src_errors:
        raise MCPValidationError(
            "sprite manifest references missing files: "
            + "; ".join(src_errors),
        )
    bound_errors = validate_tile_bounds(manifest, repo_root)
    if bound_errors:
        raise MCPValidationError(
            "sprite manifest has out-of-bounds tiles: "
            + "; ".join(bound_errors),
        )

    # Slice only the newly registered slugs — we trust already-committed
    # tiles to have been sliced on their original registration run. This
    # keeps the call fast even once the manifest grows large.
    try:
        stats = slice_all(
            manifest,
            repo_root,
            _sprite_output_dir(),
            force=params.force,
            only=new_slugs,
        )
    except ManifestError as exc:
        raise MCPValidationError(str(exc))

    # Finally, write the manifest back. Atomic rename keeps a crash from
    # leaving a half-written file.
    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    try:
        dump_manifest(manifest, tmp_path)
        tmp_path.replace(manifest_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return {
        "pack": pack,
        "manifest_path": str(manifest_path.relative_to(repo_root)),
        "sheets_registered": [s.id for s in params.sheets],
        "sprites_registered": new_slugs,
        "sliced": stats.sliced,
        "copied": stats.copied,
        "skipped": stats.skipped,
    }
