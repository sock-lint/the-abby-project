"""MCP tools for authoring and loading RPG content packs.

A "content pack" is a directory under ``content/rpg/packs/<pack-name>/``
containing any subset of YAML files that ``apps.rpg.content.loader`` knows
how to read (items.yaml, drops.yaml, quests.yaml, badges.yaml,
pet_species.yaml, potion_types.yaml, skill_tree.yaml, rewards.yaml).

The LLM workflow:

1. ``list_rpg_catalog()`` — see what slugs/names already exist so the pack's
   YAML can reference core content (e.g., a quest reward referencing a
   pre-existing item slug).
2. ``write_pack_file(pack, filename, yaml_content)`` — draft YAML files.
3. ``validate_content_pack(pack)`` — dry-run the loader to surface errors.
4. ``load_content_pack(pack)`` — commit; rows are upserted and the pack's
   ``.manifest.json`` records ``last_loaded_at``.

Safety rails:
- Every write is parent-only.
- Pack names must match ``^[a-z0-9][a-z0-9-]*$`` — no dots, no underscores
  at the start, no path separators. Reserved names (``initial``) are blocked.
- Writes outside ``content/rpg/packs/`` are rejected via resolved-path
  containment checks; path traversal (``..`` components) is refused before
  resolution.
- YAML payloads are parsed before write to catch syntax errors early.
- File size is capped at 200 KB.

Loading is done by calling ``ContentPack(path, namespace=f"{pack}-").load()``
directly — no subprocess shell-out — so structured counts and dry-run
rollback semantics come through cleanly.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings

from ..context import require_parent
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    DeleteContentPackIn,
    DeletePackFileIn,
    DraftPackEntriesIn,
    GetContentPackIn,
    ListContentPacksIn,
    ListRpgCatalogIn,
    LoadContentPackIn,
    PrunePackContentIn,
    ReadPackFileIn,
    ValidateContentPackIn,
    WritePackFileIn,
)
from ..server import tool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_PACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_RESERVED_PACK_NAMES = {"initial", "packs"}
_ALLOWED_FILENAMES = {
    "items.yaml",
    "drops.yaml",
    "quests.yaml",
    "badges.yaml",
    "pet_species.yaml",
    "potion_types.yaml",
    "skill_tree.yaml",
    "rewards.yaml",
}
_MAX_YAML_BYTES = 200_000
_MANIFEST_FILENAME = ".manifest.json"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _packs_root() -> Path:
    """Absolute path to ``content/rpg/packs/`` under BASE_DIR."""
    root = Path(settings.BASE_DIR) / "content" / "rpg" / "packs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_pack_name(pack: str) -> str:
    """Validate ``pack`` is safe for filesystem use and not reserved."""
    if not _PACK_NAME_RE.match(pack):
        raise MCPValidationError(
            f"Invalid pack name {pack!r}: must match ^[a-z0-9][a-z0-9-]*$ "
            f"(lowercase, digits, hyphens; 1-40 chars).",
        )
    if pack in _RESERVED_PACK_NAMES:
        raise MCPValidationError(
            f"Pack name {pack!r} is reserved. Choose a different name.",
        )
    return pack


def _resolve_pack_path(pack: str) -> Path:
    """Return the resolved, containment-checked path for a pack directory."""
    _validate_pack_name(pack)
    root = _packs_root().resolve()
    candidate = (root / pack).resolve()
    # Defence in depth — the regex already blocks traversal, but verify.
    try:
        candidate.relative_to(root)
    except ValueError:
        raise MCPValidationError(
            f"Pack path escapes the packs root: {candidate}",
        )
    return candidate


def _resolve_pack_file(pack: str, filename: str) -> Path:
    if filename not in _ALLOWED_FILENAMES:
        raise MCPValidationError(
            f"filename {filename!r} is not an allowed pack file. "
            f"Allowed: {sorted(_ALLOWED_FILENAMES)}",
        )
    return _resolve_pack_path(pack) / filename


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _read_manifest(pack_dir: Path) -> dict[str, Any]:
    path = pack_dir / _MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_manifest(pack_dir: Path, data: dict[str, Any]) -> None:
    path = pack_dir / _MANIFEST_FILENAME
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _pack_summary(pack_dir: Path) -> dict[str, Any]:
    """Return a dict describing a pack directory's current state."""
    files_present = sorted(
        p.name for p in pack_dir.iterdir()
        if p.is_file() and p.name in _ALLOWED_FILENAMES
    )
    manifest = _read_manifest(pack_dir)
    return {
        "name": pack_dir.name,
        "namespace_prefix": f"{pack_dir.name}-",
        "files_present": files_present,
        "last_loaded_at": manifest.get("last_loaded_at"),
        "last_load_stats": manifest.get("last_load_stats"),
    }


# ---------------------------------------------------------------------------
# Tools — pack discovery / file CRUD
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def list_content_packs(params: ListContentPacksIn) -> dict[str, Any]:
    """List all RPG content packs under ``content/rpg/packs/``.

    Returns each pack's name, namespace prefix (used at load time to avoid
    slug collisions with ``content/rpg/initial/``), which YAML files are
    currently present, and when (if ever) it was last loaded.
    """
    require_parent()
    root = _packs_root()
    packs = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        packs.append(_pack_summary(child))
    return {"packs": packs, "count": len(packs)}


@tool()
@safe_tool
def get_content_pack(params: GetContentPackIn) -> dict[str, Any]:
    """Return a single pack's summary — files present + last-load metadata."""
    require_parent()
    pack_dir = _resolve_pack_path(params.pack)
    if not pack_dir.exists():
        raise MCPNotFoundError(f"Content pack {params.pack!r} does not exist.")
    return _pack_summary(pack_dir)


@tool()
@safe_tool
def read_pack_file(params: ReadPackFileIn) -> dict[str, Any]:
    """Read the raw YAML content of a file inside a pack.

    Useful for incremental edits — read, modify in memory, write back.
    """
    require_parent()
    path = _resolve_pack_file(params.pack, params.filename)
    if not path.exists():
        raise MCPNotFoundError(
            f"{params.pack}/{params.filename} does not exist yet.",
        )
    return {
        "pack": params.pack,
        "filename": params.filename,
        "yaml_content": path.read_text(encoding="utf-8"),
    }


@tool()
@safe_tool
def write_pack_file(params: WritePackFileIn) -> dict[str, Any]:
    """Write YAML content to ``<pack>/<filename>.yaml``.

    Creates the pack directory if it doesn't exist yet. Validates:
      - pack name matches ``^[a-z0-9][a-z0-9-]*$`` and is not reserved
      - filename is one of the allowed pack files
      - content parses as YAML with a top-level mapping
      - content is under 200 KB

    Does NOT trigger a load — call ``load_content_pack`` when ready.
    """
    require_parent()
    if len(params.yaml_content.encode("utf-8")) > _MAX_YAML_BYTES:
        raise MCPValidationError(
            f"yaml_content exceeds 200 KB (actual: "
            f"{len(params.yaml_content.encode('utf-8'))} bytes).",
        )
    try:
        parsed = yaml.safe_load(params.yaml_content)
    except yaml.YAMLError as exc:
        raise MCPValidationError(f"Invalid YAML: {exc}")
    if parsed is not None and not isinstance(parsed, dict):
        raise MCPValidationError(
            "YAML top level must be a mapping (e.g. 'items:', 'drops:'). "
            f"Got {type(parsed).__name__}.",
        )

    path = _resolve_pack_file(params.pack, params.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(params.yaml_content, encoding="utf-8")
    return {
        "pack": params.pack,
        "filename": params.filename,
        "bytes_written": len(params.yaml_content.encode("utf-8")),
    }


# Mapping from a pack filename to ``(top_level_key, natural_key_field)``.
# The loader reads each file's rows from its top-level key (e.g.
# ``items.yaml`` → ``items:``) and upserts on the listed natural key. The
# draft-entries tool uses the same mapping so merges here stay consistent
# with what ``load_content_pack`` will later do.
_PACK_FILE_SCHEMA: dict[str, tuple[str, str]] = {
    "items.yaml": ("items", "slug"),
    "pet_species.yaml": ("species", "slug"),
    "potion_types.yaml": ("potions", "slug"),
    "badges.yaml": ("badges", "name"),
    "quests.yaml": ("quests", "name"),
    "rewards.yaml": ("rewards", "name"),
}


@tool()
@safe_tool
def draft_pack_entries(params: DraftPackEntriesIn) -> dict[str, Any]:
    """Merge a batch of YAML entries into a pack file.

    Parses the existing file (creating it if absent), combines the new
    rows with the old ones, dedupes by natural key (``slug`` for items /
    pet_species / potion_types, ``name`` for badges / quests / rewards)
    with last-write-wins semantics — matching the loader's upsert — and
    writes the merged YAML back through the same safety rails as
    ``write_pack_file`` (size cap, path containment, reserved-name check).

    ``mode="append"`` (default) merges into any existing rows; ``"replace"``
    discards the current file contents and writes only ``entries``.

    Does NOT trigger a load. Call ``validate_content_pack`` then
    ``load_content_pack`` to commit the rows to the database.
    """
    require_parent()
    schema = _PACK_FILE_SCHEMA.get(params.filename)
    if schema is None:
        raise MCPValidationError(
            f"filename {params.filename!r} is not draftable. "
            f"Supported: {sorted(_PACK_FILE_SCHEMA)}",
        )
    top_key, natural_key = schema

    # Validate entries shape up-front so a bad row doesn't silently pass
    # through to the loader later.
    for i, entry in enumerate(params.entries):
        if not isinstance(entry, dict):
            raise MCPValidationError(
                f"entries[{i}] must be a mapping, got {type(entry).__name__}.",
            )
        if natural_key not in entry or not entry[natural_key]:
            raise MCPValidationError(
                f"entries[{i}] is missing required field "
                f"{natural_key!r} (the natural key for "
                f"{params.filename}).",
            )

    path = _resolve_pack_file(params.pack, params.filename)

    existing: list[dict] = []
    if params.mode == "append" and path.exists():
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise MCPValidationError(
                f"{params.pack}/{params.filename} is malformed YAML: {exc}",
            )
        if parsed and not isinstance(parsed, dict):
            raise MCPValidationError(
                f"{params.pack}/{params.filename} top level must be a mapping.",
            )
        raw_existing = (parsed or {}).get(top_key) or []
        if not isinstance(raw_existing, list):
            raise MCPValidationError(
                f"{params.pack}/{params.filename}: {top_key!r} must be a list "
                f"(got {type(raw_existing).__name__}).",
            )
        existing = [e for e in raw_existing if isinstance(e, dict)]

    # Last-write-wins dedup by natural key. Preserve order: existing rows
    # first (with their key unchanged), new/updated rows added or replacing
    # in place.
    by_key: dict[Any, dict] = {}
    order: list[Any] = []
    for entry in existing:
        key = entry.get(natural_key)
        if key is None:
            # Skip rows without a natural key — the loader would reject
            # them anyway, and they'd create ambiguous merges here.
            continue
        if key not in by_key:
            order.append(key)
        by_key[key] = entry
    for entry in params.entries:
        key = entry[natural_key]
        if key not in by_key:
            order.append(key)
        by_key[key] = entry

    merged = [by_key[k] for k in order]
    doc = {top_key: merged}
    yaml_content = yaml.safe_dump(
        doc,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )

    if len(yaml_content.encode("utf-8")) > _MAX_YAML_BYTES:
        raise MCPValidationError(
            f"Merged {params.filename} exceeds 200 KB "
            f"({len(yaml_content.encode('utf-8'))} bytes). Split the pack "
            f"or reduce entry count.",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_content, encoding="utf-8")
    return {
        "pack": params.pack,
        "filename": params.filename,
        "mode": params.mode,
        "entry_count": len(merged),
        "entries_added_or_updated": len(params.entries),
        "bytes_written": len(yaml_content.encode("utf-8")),
    }


@tool()
@safe_tool
def delete_pack_file(params: DeletePackFileIn) -> dict[str, Any]:
    """Delete one YAML file from a pack.

    Does not remove already-loaded rows from the database; the loader has
    no prune step. Use this to stop shipping a section from a pack on
    subsequent loads.
    """
    require_parent()
    path = _resolve_pack_file(params.pack, params.filename)
    if not path.exists():
        raise MCPNotFoundError(
            f"{params.pack}/{params.filename} does not exist.",
        )
    path.unlink()
    return {
        "pack": params.pack,
        "filename": params.filename,
        "deleted": True,
    }


@tool()
@safe_tool
def delete_content_pack(params: DeleteContentPackIn) -> dict[str, Any]:
    """Delete an entire pack directory.

    Requires ``confirm=True``. Does NOT un-load rows already upserted to
    the database — those stay. Delete the pack from the filesystem only
    when you're sure future loads should not include its YAML.
    """
    require_parent()
    if not params.confirm:
        raise MCPValidationError(
            "delete_content_pack requires confirm=True for safety.",
        )
    pack_dir = _resolve_pack_path(params.pack)
    if not pack_dir.exists():
        raise MCPNotFoundError(f"Pack {params.pack!r} does not exist.")

    # Remove files inside, then the directory itself. Only delete known
    # pack files + manifest — refuse if there are unexpected files.
    allowed = _ALLOWED_FILENAMES | {_MANIFEST_FILENAME}
    unexpected = [
        p.name for p in pack_dir.iterdir() if p.name not in allowed
    ]
    if unexpected:
        raise MCPValidationError(
            f"Refusing to delete pack {params.pack!r}: contains unexpected "
            f"files {unexpected}. Remove them manually first.",
        )
    for p in pack_dir.iterdir():
        p.unlink()
    pack_dir.rmdir()
    return {"pack": params.pack, "deleted": True}


# ---------------------------------------------------------------------------
# Tools — validate / load
# ---------------------------------------------------------------------------


def _invoke_loader(pack: str, dry_run: bool) -> dict[str, Any]:
    """Call the loader directly and normalize the result into a dict."""
    from apps.rpg.content.loader import ContentPack, ContentPackError

    pack_dir = _resolve_pack_path(pack)
    if not pack_dir.exists():
        raise MCPNotFoundError(f"Pack {pack!r} does not exist.")
    # Skip packs with no YAML at all — loader tolerates it, but the user
    # probably made a mistake and we can flag it early.
    if not any(
        (pack_dir / name).exists() for name in _ALLOWED_FILENAMES
    ):
        raise MCPValidationError(
            f"Pack {pack!r} contains no recognizable YAML files yet.",
        )
    try:
        result = ContentPack(pack_dir, namespace=f"{pack}-").load(
            stdout=None, dry_run=dry_run,
        )
    except ContentPackError as exc:
        raise MCPValidationError(str(exc))
    return {
        "pack": pack,
        "dry_run": dry_run,
        "created": dict(result.created),
        "updated": dict(result.updated),
        "skipped": dict(result.skipped),
    }


@tool()
@safe_tool
def validate_content_pack(params: ValidateContentPackIn) -> dict[str, Any]:
    """Dry-run load a pack. Returns what WOULD be created/updated.

    Uses the loader's savepoint rollback so nothing persists. Any
    malformed YAML or reference to a missing item/badge/species surfaces
    as ``MCPValidationError``.
    """
    require_parent()
    return _invoke_loader(params.pack, dry_run=True)


@tool()
@safe_tool
def load_content_pack(params: LoadContentPackIn) -> dict[str, Any]:
    """Load a content pack into the database.

    Upserts every row defined in the pack's YAML files using the namespace
    ``<pack>-`` so slugs can't collide with ``content/rpg/initial/``.
    Re-loads are idempotent. On success, updates the pack's manifest with
    ``last_loaded_at`` and a copy of the load stats.

    Pass ``dry_run=true`` to get the same result as ``validate_content_pack``
    in one call. Use that for "what would this do?" before committing.
    """
    require_parent()
    result = _invoke_loader(params.pack, dry_run=params.dry_run)
    if not params.dry_run:
        pack_dir = _resolve_pack_path(params.pack)
        manifest = _read_manifest(pack_dir)
        manifest["last_loaded_at"] = datetime.now(timezone.utc).isoformat()
        manifest["last_load_stats"] = {
            "created": result["created"],
            "updated": result["updated"],
            "skipped": result["skipped"],
        }
        _write_manifest(pack_dir, manifest)
    return result


@tool()
@safe_tool
def prune_pack_content(params: PrunePackContentIn) -> dict[str, Any]:
    """Delete pack-scoped DropTable + Reward rows before a re-load.

    ``load_content_pack`` is upsert-only — removing a drop rule or shop
    reward from a pack's YAML and re-loading does NOT delete the stale
    row. Call this first to wipe the pack's drop + reward surface so the
    next load re-materializes exactly what the current YAML declares.

    Matches rows by ``ItemDefinition.slug.startswith("<pack>-")`` — so it
    only touches rows owned by this pack, never core content or other packs.

    Does NOT prune: ItemDefinitions (would cascade to UserInventory),
    QuestDefinitions/RewardItems (owned by quests and re-upserted), or
    Badges (name-keyed, not slug-keyed — edit via admin if needed).

    Parent-only. Pass ``dry_run=true`` to get counts without deleting.
    Returns ``{"pack": ..., "dry_run": bool, "drops_deleted": int, "rewards_deleted": int}``.
    """
    require_parent()
    # Validate pack name format via the same check used for writes, but
    # don't require the pack dir to exist — operator may be pruning a
    # pack whose YAML was already deleted.
    _validate_pack_name(params.pack)

    from apps.rpg.management.commands.prune_pack_content import prune_pack

    counts = prune_pack(params.pack, dry_run=params.dry_run)
    return {
        "pack": params.pack,
        "dry_run": params.dry_run,
        "drops_deleted": counts["drops"],
        "rewards_deleted": counts["rewards"],
    }


# ---------------------------------------------------------------------------
# Tools — RPG catalog (read-only lookup)
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def list_rpg_catalog(params: ListRpgCatalogIn) -> dict[str, Any]:
    """Aggregate read of the live RPG catalog.

    Returns all the slugs/names the LLM needs to reference when authoring
    a new pack: items (by type), pet species, potion types, drop-table
    entries (grouped by trigger), quest definitions, and badges.

    Parent-only. ``item_type`` and ``trigger_type`` filter the items and
    drop-table sections respectively.
    """
    require_parent()
    from apps.achievements.models import Badge
    from apps.pets.models import PetSpecies, PotionType
    from apps.quests.models import QuestDefinition, QuestRewardItem
    from apps.rpg.models import DropTable, ItemDefinition

    limit = params.limit_per_section

    items_qs = ItemDefinition.objects.all()
    if params.item_type:
        items_qs = items_qs.filter(item_type=params.item_type)
    items = [
        {
            "slug": it.slug,
            "name": it.name,
            "item_type": it.item_type,
            "rarity": it.rarity,
            "icon": it.icon,
            "coin_value": it.coin_value,
            "pet_species_slug": it.pet_species.slug if it.pet_species_id else None,
            "potion_type_slug": it.potion_type.slug if it.potion_type_id else None,
            "food_species_slug": it.food_species.slug if it.food_species_id else None,
        }
        for it in items_qs[:limit]
    ]

    species = [
        {
            "slug": s.slug,
            "name": s.name,
            "icon": s.icon,
            "food_preference": s.food_preference,
            "available_potion_slugs": sorted(
                p.slug for p in s.available_potions.all()
            ),
        }
        for s in PetSpecies.objects.prefetch_related("available_potions").all()[:limit]
    ]

    potions = [
        {
            "slug": p.slug,
            "name": p.name,
            "color_hex": p.color_hex,
            "rarity": p.rarity,
        }
        for p in PotionType.objects.all()[:limit]
    ]

    drops_qs = DropTable.objects.select_related("item").all()
    if params.trigger_type:
        drops_qs = drops_qs.filter(trigger_type=params.trigger_type)
    drops_by_trigger: dict[str, list[dict[str, Any]]] = {}
    for d in drops_qs[:limit]:
        drops_by_trigger.setdefault(d.trigger_type, []).append({
            "item_slug": d.item.slug,
            "item_name": d.item.name,
            "weight": d.weight,
            "min_level": d.min_level,
        })

    quests_qs = QuestDefinition.objects.prefetch_related(
        "reward_items__item",
    ).all()[:limit]
    quests = [
        {
            "name": q.name,
            "quest_type": q.quest_type,
            "target_value": q.target_value,
            "duration_days": q.duration_days,
            "coin_reward": q.coin_reward,
            "xp_reward": q.xp_reward,
            "is_repeatable": q.is_repeatable,
            "reward_items": [
                {
                    "item_slug": r.item.slug,
                    "quantity": r.quantity,
                }
                for r in q.reward_items.all()
            ],
        }
        for q in quests_qs
    ]

    badges = [
        {
            "name": b.name,
            "rarity": b.rarity,
            "criteria_type": b.criteria_type,
            "xp_bonus": b.xp_bonus,
        }
        for b in Badge.objects.all()[:limit]
    ]

    return {
        "items": items,
        "pet_species": species,
        "potion_types": potions,
        "drops_by_trigger": drops_by_trigger,
        "quests": quests,
        "badges": badges,
        "counts": {
            "items": len(items),
            "pet_species": len(species),
            "potion_types": len(potions),
            "quests": len(quests),
            "badges": len(badges),
        },
    }
