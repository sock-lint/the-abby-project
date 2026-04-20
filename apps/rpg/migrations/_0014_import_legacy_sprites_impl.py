"""Forward/reverse functions for 0014_import_legacy_sprites.

Lives in its own module (not inline in the migration file) so tests can
import and invoke it directly — migrations run at import time as
RunPython wrappers and are awkward to test end-to-end otherwise.

Sources the pre-sliced PNG derivatives committed at
``content/rpg/legacy_sprites/``. Slug = filename stem. Does NOT read
``scripts/sprite_manifest.yaml`` or the source sheets — those sheets
are in .gitignore (licensed, not redistributable) and therefore not
in the Docker image.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image


def _legacy_sprite_dir() -> Path:
    return Path(settings.BASE_DIR).resolve() / "content" / "rpg" / "legacy_sprites"


def import_legacy_sprites(apps, schema_editor):
    """Import every PNG in content/rpg/legacy_sprites/ as a SpriteAsset row."""
    SpriteAsset = apps.get_model("rpg", "SpriteAsset")
    sprite_dir = _legacy_sprite_dir()

    if not sprite_dir.exists():
        # Fresh deploy where the legacy directory was already removed —
        # nothing to import (Phase 3 cleanup will be this path).
        return

    for png_path in sorted(sprite_dir.glob("*.png")):
        slug = png_path.stem

        if SpriteAsset.objects.filter(slug=slug).exists():
            continue  # idempotent

        png_bytes = png_path.read_bytes()
        img = Image.open(io.BytesIO(png_bytes))
        w, h = img.size

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
