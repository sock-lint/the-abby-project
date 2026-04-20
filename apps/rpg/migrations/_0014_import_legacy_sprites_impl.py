"""Forward/reverse functions for 0014_import_legacy_sprites.

Lives in its own module (not inline in the migration file) so tests can
import and invoke it directly — migrations run at import time as
RunPython wrappers and are awkward to test end-to-end otherwise.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image


def import_legacy_sprites(apps, schema_editor):
    """Import every sprite from scripts/sprite_manifest.yaml into the DB."""
    from apps.rpg.content.sprites import load_manifest, SheetTile, LooseFile

    SpriteAsset = apps.get_model("rpg", "SpriteAsset")
    repo_root = Path(settings.BASE_DIR).resolve()
    manifest_path = repo_root / "scripts" / "sprite_manifest.yaml"

    if not manifest_path.exists():
        # Fresh deploy where the manifest was already removed — nothing to import
        return

    manifest = load_manifest(manifest_path)

    for slug, entry in manifest.sprites.items():
        if SpriteAsset.objects.filter(slug=slug).exists():
            continue  # idempotent

        if isinstance(entry, SheetTile):
            sheet = manifest.sheets[entry.sheet_id]
            sheet_img = Image.open(repo_root / sheet.file)
            ts = sheet.tile_size
            crop = sheet_img.crop(
                (entry.col * ts, entry.row * ts,
                 (entry.col + 1) * ts, (entry.row + 1) * ts),
            )
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            w, h = ts, ts
        elif isinstance(entry, LooseFile):
            png_bytes = (repo_root / entry.file).read_bytes()
            img = Image.open(io.BytesIO(png_bytes))
            w, h = img.size
        else:
            continue  # unknown source type — skip

        digest = hashlib.sha256(png_bytes).hexdigest()[:8]
        asset = SpriteAsset(
            slug=slug,
            pack="core",
            frame_count=1,
            fps=0,
            frame_width_px=w,
            frame_height_px=h,
            frame_layout="horizontal",
        )
        asset.image.save(f"{slug}-{digest}.png", ContentFile(png_bytes), save=False)
        asset.save()


def remove_legacy_sprites(apps, schema_editor):
    """Reverse: delete all pack='core' sprites from DB and from storage."""
    SpriteAsset = apps.get_model("rpg", "SpriteAsset")
    for asset in SpriteAsset.objects.filter(pack="core"):
        asset.image.delete(save=False)  # blob first
        asset.delete()
