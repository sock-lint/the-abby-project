# Chat-to-production sprite authoring

## Context

Today's sprite system is a **build-time pipeline**:

- Author drops sheet PNGs under `reward-icons/<pack>/`, or loose-file PNGs under `content/rpg/packs/<pack>/sprites/`.
- [`scripts/slice_rpg_sprites.py`](../../../scripts/slice_rpg_sprites.py) (or the MCP tool `register_sprite_assets`) reads [`scripts/sprite_manifest.yaml`](../../../scripts/sprite_manifest.yaml), slices tiles, writes output PNGs to [`frontend/src/assets/rpg-sprites/<slug>.png`](../../../frontend/src/assets/rpg-sprites/).
- Vite's `import.meta.glob({ eager: true })` in [`frontend/src/assets/rpg-sprites/index.js`](../../../frontend/src/assets/rpg-sprites/index.js) bakes 72 PNGs into the production bundle at image-build time.
- [`RpgSprite.jsx`](../../../frontend/src/components/rpg/RpgSprite.jsx) resolves `sprite_key: <slug>` references from content YAML (referenced by `ItemDefinition`, `QuestDefinition`, `PetSpecies`) to bundled URLs synchronously via `getSpriteUrl(slug)`.

The LLM-facing MCP tool `register_sprite_assets` writes into this source tree, which means it only works against a local dev checkout. Running it against the production MCP endpoint at `https://abby.bos.lol/mcp` hits `/app/content/rpg/packs/…: Permission denied` because the running container's source tree is read-only and Vite has already bundled whatever PNGs existed at image-build time. The smoke test sweep at [`scripts/smoke_mcp.py`](../../../scripts/smoke_mcp.py) skips the tool for exactly this reason.

**Goal:** let the LLM (running in any chat client with MCP access to prod) register sprites — static *or* animated — and have them render in the production UI on the next browser refresh. No PR, no CI, no deploy cycle.

The long-term goal is simple looping animations (pet idle flutter, flame flicker, coin spin). Phase 1 includes them so the data model and render path don't have to be retrofitted later.

## Scope

**In scope for Phase 1:**

- Runtime sprite registration via MCP (both single-sprite and bulk-sheet flows).
- Static sprites and horizontally-tiled animation strips (`frame_count > 1, fps > 0, layout = "horizontal"`).
- Ceph-backed image storage + DB-backed manifest replacing the YAML file.
- Data migration importing the 72 existing sprites.
- Full frontend swap from Vite-glob bundle to API-driven catalog.
- Animation rendering via CSS `steps()` background-position cycling.

**Not in scope:**

- Sheet source persistence (sheets are transient server-side inputs — re-authoring requires re-upload).
- Vertical/2D-grid animation layouts (Phase 2 if ever needed; `frame_layout` column is there).
- Animation preview tools (the LLM registers → user refreshes → sees result live).
- Variable-speed / pause-on-hover / multi-state animations (canvas-based; not needed for idle loops).
- Offline/bundle fallback for sprites (Django being down means the whole app is down).
- Replacing any of the existing Django models that *reference* sprites via `sprite_key` — those continue to work as opaque string references.

## Data model

One new model replaces [`scripts/sprite_manifest.yaml`](../../../scripts/sprite_manifest.yaml):

```python
# apps/rpg/models.py (new model, new migration)

class SpriteAsset(TimestampedModel):
    SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"

    class FrameLayout(TextChoices):
        HORIZONTAL = "horizontal", "Horizontal strip"
        VERTICAL   = "vertical",   "Vertical strip"

    slug             = CharField(max_length=64, unique=True,
                                 validators=[RegexValidator(SLUG_PATTERN)])
    image            = ImageField(upload_to="rpg-sprites/",
                                  storage=sprite_storage())   # see config/settings.py
    pack             = CharField(max_length=40, db_index=True, default="user-authored")
    frame_count      = PositiveSmallIntegerField(default=1)
    fps              = PositiveSmallIntegerField(default=0)
    frame_width_px   = PositiveSmallIntegerField()
    frame_height_px  = PositiveSmallIntegerField()
    frame_layout     = CharField(max_length=12, choices=FrameLayout.choices,
                                 default=FrameLayout.HORIZONTAL)
    created_by       = ForeignKey(User, on_delete=SET_NULL, null=True, blank=True,
                                  related_name="sprites_authored")

    class Meta:
        indexes = [Index(fields=["pack", "slug"])]

    def clean(self):
        if self.frame_count < 1:
            raise ValidationError("frame_count must be >= 1")
        if self.frame_count == 1 and self.fps != 0:
            raise ValidationError("static sprite (frame_count=1) must have fps=0")
        if self.frame_count > 1 and self.fps < 1:
            raise ValidationError("animated sprite (frame_count>1) requires fps >= 1")
```

**Interpretation:**

- `frame_count == 1, fps == 0` → **static sprite**. Single-frame PNG. Dimensions = `frame_width_px × frame_height_px`.
- `frame_count > 1, fps >= 1` → **animated sprite**. Horizontal strip by default: PNG dimensions = `(frame_count * frame_width_px) × frame_height_px`. Animation duration = `frame_count / fps` seconds.
- `pack = "core"` for the 72 imported legacy sprites; `pack = "user-authored"` for chat-registered sprites by default; arbitrary pack slugs allowed for future organization.

**File key on Ceph:** `rpg-sprites/<slug>-<content-sha256[:8]>.png`. Content-hash suffix gives:
- Stable URL per content → browsers cache forever (`max-age=31536000, immutable`).
- New bytes → new hash → new URL → automatic cache-bust. No manual purge.

## Storage — dedicated bucket

Ceph RGW's per-bucket CORS + ACL model makes a separate bucket the cleanest split.

**New bucket `abby-sprites`** (one-time, manual via Ceph admin):

- **ACL:** public-read on objects (sprites are not sensitive; the whole point is long-lived cacheable URLs).
- **CORS:** `AllowedOrigins: ["https://abby.bos.lol"]`, `AllowedMethods: ["GET", "HEAD"]`, `AllowedHeaders: ["*"]`, `MaxAgeSeconds: 3600`.
- **Upload defaults:** every `PutObject` sends `Cache-Control: public, max-age=31536000, immutable` and `ACL: public-read`.

**Django wiring** ([`config/settings.py`](../../../config/settings.py)): add a second `STORAGES` entry:

```python
STORAGES = {
    "default":    {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {...existing...}},
    "staticfiles": {...},
    "sprites": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("SPRITE_S3_BUCKET", default="abby-sprites"),
            "endpoint_url": env("SPRITE_S3_ENDPOINT", default=env("AWS_S3_ENDPOINT_URL")),
            "access_key": env("AWS_ACCESS_KEY_ID"),
            "secret_key": env("AWS_SECRET_ACCESS_KEY"),
            "querystring_auth": False,           # << public URLs, no presigning
            "default_acl": "public-read",
            "object_parameters": {
                "CacheControl": "public, max-age=31536000, immutable",
            },
            "custom_domain": env("SPRITE_S3_CUSTOM_DOMAIN", default=None),
        },
    },
}

def sprite_storage():
    from django.core.files.storage import storages
    return storages["sprites"]
```

New env vars (`.env.example` + prod Coolify settings):
- `SPRITE_S3_BUCKET=abby-sprites`
- `SPRITE_S3_ENDPOINT=https://s3.neato.digital` (defaults to existing `AWS_S3_ENDPOINT_URL`)
- `SPRITE_S3_CUSTOM_DOMAIN=sprites.neato.digital` (optional — if operator fronts the bucket with a custom domain for prettier URLs)

**Tests** keep `STORAGES["default"]` pinned to `FileSystemStorage` per the existing `if "test" in sys.argv` block; `STORAGES["sprites"]` gets the same override, pointed at a tmp dir. `SpriteAsset.image.url` in tests resolves to a local file URL; no Ceph traffic.

**Deletes** follow the existing pattern from the [storage-deletes gotcha](../../../CLAUDE.md): any `SpriteAsset.delete()` call or `.image` reassignment invokes `image.delete(save=False)` first so the Ceph blob goes before the DB row. `delete_sprite` MCP tool uses this ordering.

## MCP tool surface

The old [`register_sprite_assets`](../../../apps/mcp_server/tools/sprite_assets.py) is deleted. Four focused tools replace it, all parent-only.

### `register_sprite` — one sprite, one call

Handles the "I have a single PNG, make it a sprite" flow. Accepts static single-frame OR animated strip images.

```python
class RegisterSpriteIn(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    image_b64: Optional[str] = None           # exactly one of image_b64 / image_url
    image_url: Optional[str] = None
    pack: str = Field(default="user-authored", max_length=40)
    frame_count: int = Field(default=1, ge=1, le=64)
    fps: int = Field(default=0, ge=0, le=30)
    frame_layout: Literal["horizontal", "vertical"] = "horizontal"
    overwrite: bool = False

# Returns:
# {slug, url, pack, frame_count, fps, frame_width_px, frame_height_px, frame_layout}
```

**Server workflow** (in `apps/sprite_authoring/services.py`):

1. Validate exactly one of `image_b64` / `image_url`. Decode base64 or HTTP-GET the URL (size cap 10 MB, content-type must be `image/png` or `image/webp`).
2. Open with Pillow. Reject if not PNG/WebP, if dimensions are >4096 on any axis, or if bytes are malformed.
3. For `frame_count > 1`: validate that `img.width % frame_count == 0` (horizontal) or `img.height % frame_count == 0` (vertical). Compute per-frame dimensions.
4. Compute `sha256(bytes)[:8]`.
5. If slug exists and `overwrite=False`, raise `MCPValidationError`. If `overwrite=True`, the old `SpriteAsset.image.delete(save=False)` fires before the new upload so the old Ceph blob is cleaned up.
6. Build `ContentFile(bytes, name=f"{slug}-{hash}.png")`, assign to `SpriteAsset.image` → the S3 backend uploads.
7. Upsert the DB row with dimensions, frame_count, fps, pack, created_by.
8. Return the structured dict above.

### `register_sprite_batch` — sheet + many named tiles

The shikashi bulk-authoring use case, adapted for runtime.

```python
class SpriteTileDecl(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    col: int = Field(ge=0, le=1024)
    row: int = Field(ge=0, le=1024)
    frame_count: int = Field(default=1, ge=1, le=64)  # animation extends rightward from (col, row)
    fps: int = Field(default=0, ge=0, le=30)
    pack: str = Field(default="user-authored", max_length=40)

class RegisterSpriteBatchIn(_Base):
    sheet_b64: Optional[str] = None
    sheet_url: Optional[str] = None
    tile_size: int = Field(ge=8, le=256)
    tiles: list[SpriteTileDecl] = Field(min_length=1, max_length=200)
    overwrite: bool = False

# Returns:
# {registered: [{slug, url, frame_count, fps, ...}, ...],
#  skipped:    [{slug, reason}, ...]}
```

**Server workflow:**

1. Fetch/decode sheet (same validation as `register_sprite`, size cap 20 MB).
2. Open with Pillow once, hold in memory.
3. For each tile decl:
   - Crop `(col * tile_size, row * tile_size)` → `((col + frame_count) * tile_size, (row + 1) * tile_size)`. Validate crop box stays within sheet bounds.
   - Encode the cropped region as PNG bytes.
   - Run the same upload + upsert logic as `register_sprite`.
   - On per-tile errors (slug collision without overwrite, out-of-bounds crop): add to `skipped`, don't fail the whole batch.
4. Source sheet is **not persisted**. Re-authoring a tile means re-uploading the sheet. This is intentional — persisting sheets doubles the storage footprint for marginal LLM-convenience gain.

### `list_sprites` — read-only enumeration

```python
class ListSpritesIn(_Base):
    pack: Optional[str] = None
    limit: int = Field(default=200, ge=1, le=500)

# Returns:
# {sprites: [{slug, url, pack, frame_count, fps, frame_width_px, frame_height_px, frame_layout}, ...]}
```

Lets the LLM check what's already registered before authoring (avoid name collisions).

### `delete_sprite`

```python
class DeleteSpriteIn(_Base):
    slug: str

# Returns:
# {slug, deleted: true}
```

Deletes DB row + Ceph blob (blob first, following the storage-deletes invariant). Content YAML or model rows that still reference the slug via `sprite_key` are not touched — they'll emoji-fallback in the UI, which is the existing contract when a slug is unknown. The LLM is responsible for not leaving dangling references; `list_sprites` + targeted grep is the way to check.

## HTTP API — sprite catalog

One new read-only endpoint for the frontend.

### `GET /api/sprites/catalog/`

**Authentication:** none. The sprite URLs are public-read on Ceph; no child-specific data is exposed here.

**Response:**

```json
{
  "sprites": {
    "dragon":      {"url": "https://sprites.neato.digital/rpg-sprites/dragon-a3f7b1.png",
                    "frames": 1, "fps": 0, "w": 32, "h": 32, "layout": "horizontal"},
    "pet-flutter": {"url": "https://sprites.neato.digital/rpg-sprites/pet-flutter-8c2d91.png",
                    "frames": 4, "fps": 6,  "w": 32, "h": 32, "layout": "horizontal"}
  },
  "etag": "sha256-shortened"
}
```

`etag` is the SHA256 of the sorted list of `(slug, image_key)` pairs, truncated to 16 chars. Included in the JSON body AND as the HTTP `ETag` header so the client can send `If-None-Match` for `304 Not Modified` responses.

**Caching:** `Cache-Control: public, max-age=60, stale-while-revalidate=600`. Short max-age because new sprites need to be visible quickly after the LLM authors them; `stale-while-revalidate` keeps UX snappy.

**Size budget:** 200 sprites × ~180 bytes JSON each ≈ 36 KB. Gzipped, ~10 KB. Fine for a once-per-session fetch.

## Frontend — catalog provider + renderer

**Delete:** [`frontend/src/assets/rpg-sprites/index.js`](../../../frontend/src/assets/rpg-sprites/index.js) and all 72 PNGs in that directory.

**New:** [`frontend/src/providers/SpriteCatalogProvider.jsx`](../../../frontend/src/providers/SpriteCatalogProvider.jsx):

- Wraps the app root (mounted in [`App.jsx`](../../../frontend/src/App.jsx) inside the existing `<AuthProvider>`).
- On mount: `fetch("/api/sprites/catalog/", { headers: { "If-None-Match": localStorage.getItem("spriteCatalogEtag") }})`.
- Caches the response in `localStorage` under `spriteCatalog` + `spriteCatalogEtag`. Fresh mounts use cached data immediately; the network revalidation updates in the background.
- Exposes a `useSpriteCatalog()` hook returning `{getSpriteUrl, getSpriteMeta}`:
  - `getSpriteUrl(slug)` → `string | null` (same shape as today's function — existing call sites don't need to change).
  - `getSpriteMeta(slug)` → `{url, frames, fps, w, h, layout} | null` (new, for [`RpgSprite.jsx`](../../../frontend/src/components/rpg/RpgSprite.jsx) animation branch).
- Emits an `<style id="sprite-keyframes">` tag containing `@keyframes sprite-cycle-N` rules for each distinct `frame_count` value in the catalog (so any animation length is covered without runtime style recomputation).

**[`RpgSprite.jsx`](../../../frontend/src/components/rpg/RpgSprite.jsx) update:** one new branch for animated sprites.

```jsx
export default function RpgSprite({ spriteKey, icon, size = 32, className = "", alt = "" }) {
  const { getSpriteMeta } = useSpriteCatalog();
  const meta = getSpriteMeta(spriteKey);

  if (meta && meta.frames === 1) {
    return <img src={meta.url} alt={alt || spriteKey || "sprite"}
                width={size} height={size}
                style={{ imageRendering: "pixelated" }} className={className} />;
  }
  if (meta && meta.frames > 1) {
    return (
      <span
        role="img"
        aria-label={alt}
        className={`inline-block ${className}`}
        style={{
          width: size, height: size,
          backgroundImage: `url(${meta.url})`,
          backgroundSize: `${meta.frames * size}px ${size}px`,
          imageRendering: "pixelated",
          animation: `sprite-cycle-${meta.frames} ${meta.frames / meta.fps}s steps(${meta.frames}) infinite`,
        }}
      />
    );
  }
  // Emoji fallback (unchanged from today)
  ...
}
```

`prefers-reduced-motion` respected by the keyframes themselves:

```css
@media (prefers-reduced-motion: reduce) {
  [class*="sprite-cycle"] { animation: none !important; background-position: 0 0 !important; }
}
```

**Call sites** — 14 files currently import `getSpriteUrl`. They stay working through the hook's shape-compatible `getSpriteUrl`. Migration risk is low: null-return is already handled everywhere (emoji fallback).

## Migration — import the 72 existing sprites

One data migration in `apps/rpg/migrations/`:

```python
# XXXX_import_legacy_sprites.py

def import_legacy_sprites(apps, schema_editor):
    SpriteAsset = apps.get_model("rpg", "SpriteAsset")
    from pathlib import Path
    from hashlib import sha256
    from django.core.files.base import ContentFile
    from apps.rpg.content.sprites import load_manifest
    from PIL import Image

    repo_root = Path(settings.BASE_DIR).resolve()
    manifest = load_manifest(repo_root / "scripts" / "sprite_manifest.yaml")

    for slug, entry in manifest.sprites.items():
        if SpriteAsset.objects.filter(slug=slug).exists():
            continue  # idempotent
        if isinstance(entry, SheetTile):
            sheet = manifest.sheets[entry.sheet_id]
            img = Image.open(repo_root / sheet.file)
            ts = sheet.tile_size
            crop = img.crop((entry.col*ts, entry.row*ts, (entry.col+1)*ts, (entry.row+1)*ts))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            png_bytes = buf.getvalue()
        else:  # LooseFile
            png_bytes = (repo_root / entry.file).read_bytes()

        digest = sha256(png_bytes).hexdigest()[:8]
        dims = Image.open(io.BytesIO(png_bytes)).size

        asset = SpriteAsset(
            slug=slug, pack="core",
            frame_count=1, fps=0,
            frame_width_px=dims[0], frame_height_px=dims[1],
            frame_layout="horizontal",
        )
        asset.image.save(f"{slug}-{digest}.png", ContentFile(png_bytes), save=False)
        asset.save()


def remove_legacy_sprites(apps, schema_editor):
    SpriteAsset = apps.get_model("rpg", "SpriteAsset")
    for asset in SpriteAsset.objects.filter(pack="core"):
        asset.image.delete(save=False)  # Ceph blob gone first
        asset.delete()


class Migration(migrations.Migration):
    dependencies = [("rpg", "<prev>"), ("rpg", "XXXX_sprite_asset")]
    operations = [migrations.RunPython(import_legacy_sprites, remove_legacy_sprites)]
```

Reverse migration is **not** `noop` — restoring to the previous state means deleting 72 Ceph objects too, and the reverse here does that cleanly.

**Rollback safety:** if the frontend deploy fails and we need to revert, leaving these rows in the DB is harmless — the old frontend bundle still has its own local PNGs and ignores the API. Ceph costs are negligible (< 200 KB of PNGs).

## Rollout plan

Three deploys, held apart for safety.

**Deploy 1 — backend + migration:**

- Add `SpriteAsset` model + migration + data-import migration.
- Add four new MCP tools, `/api/sprites/catalog/` endpoint.
- Ship `register_sprite_assets` + `scripts/slice_rpg_sprites.py` unchanged (still functional for source-tree authoring).
- Verify: migration ran, 72 rows in DB, Ceph bucket has 72 PNGs, `/api/sprites/catalog/` returns them.

**Deploy 2 — frontend cutover:**

- Ship `SpriteCatalogProvider`, update `RpgSprite.jsx`.
- Delete `frontend/src/assets/rpg-sprites/index.js` + all 72 PNGs.
- Verify: every page that renders an RPG icon still shows the right sprite. Check animation rendering (no existing animated sprites, so this is a pending integration test — register one via MCP and verify it animates).

**Deploy 3 — cleanup (a week later, once stable):**

- Delete `apps/mcp_server/tools/sprite_assets.py`, `apps/rpg/content/sprites.py` (or the unused bits), `scripts/sprite_manifest.yaml`, `scripts/slice_rpg_sprites.py`, `reward-icons/` directory, `content/rpg/packs/*/sprites/` directories.
- Note in commit message: legacy source tree preserved in git history for re-hydration if ever needed.

## Testing

**Backend** (`apps/sprite_authoring/tests/`):

- `test_register_sprite_static.py`: base64 input, URL input, invalid MIME, oversize PNG, slug collision with/without overwrite, non-parent rejected (403).
- `test_register_sprite_animated.py`: dimensions validation for frame_count (wraps around when `img.width % frame_count != 0`), fps required for animated, partial failures in batch.
- `test_register_sprite_batch.py`: multi-tile slice success, out-of-bounds col/row reported as skipped (not batch failure), sheet URL fetch timeout.
- `test_delete_sprite.py`: Ceph blob is deleted before DB row (mock storage, assert call order).
- `test_catalog_endpoint.py`: ETag round-trip, unauthenticated access, response shape.
- `test_legacy_migration.py`: point at a fixture manifest, confirm 72 rows + Ceph uploads + idempotent re-run.

**Frontend** (`frontend/src/`):

- `providers/SpriteCatalogProvider.test.jsx`: mounts, fetches, exposes hook, handles 304, localStorage round-trip.
- `components/rpg/RpgSprite.test.jsx`: static render path, animated render path (check computed `animation` style), emoji fallback, `prefers-reduced-motion`.

**End-to-end smoke test** ([`scripts/smoke_mcp.py`](../../../scripts/smoke_mcp.py)):

- Replace the `register_sprite_assets` skip with real coverage of the four new tools: `register_sprite` round-trip (create+delete with a 1×1 red pixel), `register_sprite_batch` with a 64×32 2-tile sheet, `list_sprites`, `delete_sprite`.
- Add a `--verify-frontend` flag: fetches `GET /api/sprites/catalog/`, asserts the just-registered slug is present, then deletes it.

## Open questions → closed

| Question | Decision |
|----------|----------|
| Byte transport | Base64 **and** URL, tool decides based on which is populated. |
| Animation render tech | PNG strip + CSS `steps()` animation. |
| Storage backend | Dedicated Ceph bucket `abby-sprites`, public-read, no presigning. |
| Manifest location | DB model `SpriteAsset`, one row per sprite. |
| Frontend loading | `GET /api/sprites/catalog/` at app mount, ETag revalidation. |
| Sheet persistence | No. Sheets are transient server-side inputs. |
| Legacy sprites | All 72 migrated to `pack="core"`; Vite bundle deleted. |
| Backward compat for `sprite_key` references | None needed — slugs still resolve, just through DB now. |
| Delete semantics | Blob-first, then DB row. Dangling `sprite_key` references emoji-fallback (existing contract). |
