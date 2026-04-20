# Chat-to-Production Sprite Authoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the MCP-connected LLM register static or animated sprites directly against production and have them render in the UI on next browser refresh — replacing the build-time Vite-glob bundle with a DB + Ceph runtime system.

**Architecture:** New `SpriteAsset` Django model (replacing `scripts/sprite_manifest.yaml`) + dedicated public-read Ceph bucket `abby-sprites` + four new MCP tools + one new GET catalog API endpoint + a React `SpriteCatalogProvider` that fetches the catalog once at mount. Animation via PNG strips rendered with CSS `steps()` background-position cycling.

**Tech Stack:** Django 5.1 + DRF, django-storages S3Storage → Ceph RGW, Pillow (image slicing), FastMCP, Pydantic v2 (tool schemas), React 19 + React Context, Vitest 4 + MSW 2 (frontend tests).

**Spec:** [docs/superpowers/specs/2026-04-20-chat-to-prod-sprite-authoring-design.md](../specs/2026-04-20-chat-to-prod-sprite-authoring-design.md)

---

## Phase 0: Ceph bucket (manual, one-time, operator only)

**Files:** none (manual step on Ceph admin before backend deploy).

- [ ] **Step 1: Create bucket `abby-sprites` on Ceph RGW**

```bash
aws --endpoint-url https://s3.neato.digital s3api create-bucket --bucket abby-sprites
```

- [ ] **Step 2: Apply public-read ACL to the bucket**

```bash
aws --endpoint-url https://s3.neato.digital s3api put-bucket-acl \
    --bucket abby-sprites --acl public-read
```

- [ ] **Step 3: Apply CORS to the bucket**

Write `/tmp/sprite-cors.json`:

```json
{
  "CORSRules": [{
    "AllowedOrigins": ["https://abby.bos.lol"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }]
}
```

Apply:

```bash
aws --endpoint-url https://s3.neato.digital s3api put-bucket-cors \
    --bucket abby-sprites --cors-configuration file:///tmp/sprite-cors.json
```

- [ ] **Step 4: Verify bucket is reachable anonymously**

```bash
curl -I https://s3.neato.digital/abby-sprites/  # expect 200 or 403 (listing disabled), NOT 404
```

- [ ] **Step 5: Add env vars to production Coolify service**

```
SPRITE_S3_BUCKET=abby-sprites
SPRITE_S3_ENDPOINT=https://s3.neato.digital
SPRITE_S3_CUSTOM_DOMAIN=            # leave blank initially; fill if/when fronted by CDN
```

---

## Phase 1: Backend data model + storage wiring

### Task 1: Add the `SpriteAsset` model + schema migration

**Files:**
- Modify: `apps/rpg/models.py` (append model)
- Create: `apps/rpg/migrations/0012_sprite_asset.py` (auto-generated)
- Create: `apps/rpg/tests/test_sprite_asset_model.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_sprite_asset_model.py`:

```python
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.accounts.models import User
from apps.rpg.models import SpriteAsset


class SpriteAssetModelTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")

    def test_static_sprite_defaults(self):
        asset = SpriteAsset.objects.create(
            slug="dragon",
            pack="test",
            frame_width_px=32,
            frame_height_px=32,
            created_by=self.parent,
        )
        self.assertEqual(asset.frame_count, 1)
        self.assertEqual(asset.fps, 0)
        self.assertEqual(asset.frame_layout, "horizontal")

    def test_slug_uniqueness(self):
        SpriteAsset.objects.create(slug="unique", pack="t", frame_width_px=8, frame_height_px=8)
        with self.assertRaises(Exception):
            SpriteAsset.objects.create(slug="unique", pack="t", frame_width_px=8, frame_height_px=8)

    def test_slug_lowercase_hyphens_only(self):
        asset = SpriteAsset(slug="Invalid Slug", pack="t", frame_width_px=8, frame_height_px=8)
        with self.assertRaises(ValidationError):
            asset.full_clean()

    def test_static_sprite_rejects_nonzero_fps(self):
        asset = SpriteAsset(slug="bad", pack="t", frame_width_px=8, frame_height_px=8, fps=6)
        with self.assertRaises(ValidationError):
            asset.full_clean()

    def test_animated_sprite_requires_fps(self):
        asset = SpriteAsset(slug="bad2", pack="t", frame_width_px=8, frame_height_px=8,
                            frame_count=4, fps=0)
        with self.assertRaises(ValidationError):
            asset.full_clean()

    def test_animated_sprite_happy_path(self):
        asset = SpriteAsset(slug="flame", pack="t", frame_width_px=16, frame_height_px=16,
                            frame_count=4, fps=6, frame_layout="horizontal")
        asset.full_clean()  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_asset_model -v 2`

Expected: FAIL with `ImportError: cannot import name 'SpriteAsset' from 'apps.rpg.models'`.

- [ ] **Step 3: Add the model to `apps/rpg/models.py`**

Append to `apps/rpg/models.py`:

```python
from django.core.validators import RegexValidator

class SpriteAsset(TimestampedModel):
    """Runtime-authored sprite (static or animated strip) stored on Ceph.

    Replaces the build-time scripts/sprite_manifest.yaml + Vite bundle flow.
    One row per registered sprite; the ``image`` FieldFile points at a
    public-read Ceph object under the ``abby-sprites`` bucket. Content YAML
    and model rows reference sprites by ``slug`` via ``sprite_key`` fields
    (unchanged — just resolved through DB now).
    """

    SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"

    class FrameLayout(models.TextChoices):
        HORIZONTAL = "horizontal", "Horizontal strip"
        VERTICAL = "vertical", "Vertical strip"

    slug = models.CharField(
        max_length=64,
        unique=True,
        validators=[RegexValidator(SLUG_PATTERN, "Slug must be lowercase a-z0-9 and hyphens.")],
    )
    image = models.ImageField(upload_to="rpg-sprites/", storage=None)
    pack = models.CharField(max_length=40, db_index=True, default="user-authored")
    frame_count = models.PositiveSmallIntegerField(default=1)
    fps = models.PositiveSmallIntegerField(default=0)
    frame_width_px = models.PositiveSmallIntegerField()
    frame_height_px = models.PositiveSmallIntegerField()
    frame_layout = models.CharField(
        max_length=12,
        choices=FrameLayout.choices,
        default=FrameLayout.HORIZONTAL,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sprites_authored",
    )

    class Meta:
        indexes = [models.Index(fields=["pack", "slug"])]

    def clean(self):
        super().clean()
        if self.frame_count < 1:
            raise ValidationError({"frame_count": "frame_count must be >= 1"})
        if self.frame_count == 1 and self.fps != 0:
            raise ValidationError({"fps": "static sprite (frame_count=1) must have fps=0"})
        if self.frame_count > 1 and self.fps < 1:
            raise ValidationError({"fps": "animated sprite (frame_count>1) requires fps >= 1"})

    def __str__(self):
        tag = "animated" if self.frame_count > 1 else "static"
        return f"{self.slug} ({tag}, {self.pack})"
```

Note: `storage=None` is a temporary placeholder — Task 2 wires it to `sprite_storage()`.

- [ ] **Step 4: Generate and apply migration**

```bash
docker compose exec django python manage.py makemigrations rpg --name sprite_asset
docker compose exec django python manage.py migrate rpg
```

Expected: creates `0012_sprite_asset.py` with `CreateModel` operation.

- [ ] **Step 5: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_asset_model -v 2`

Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/rpg/models.py apps/rpg/migrations/0012_sprite_asset.py apps/rpg/tests/test_sprite_asset_model.py
git commit -m "feat: add SpriteAsset model for runtime sprite authoring"
```

---

### Task 2: Wire `STORAGES["sprites"]` + `sprite_storage()` helper

**Files:**
- Modify: `config/settings.py:245-289`
- Modify: `.env.example`
- Modify: `apps/rpg/models.py` (update `SpriteAsset.image` storage)
- Create: `apps/rpg/storage.py`
- Create: `apps/rpg/tests/test_sprite_storage.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_sprite_storage.py`:

```python
from django.test import TestCase, override_settings
from apps.rpg.storage import sprite_storage


class SpriteStorageHelperTests(TestCase):
    def test_returns_a_storage_instance(self):
        storage = sprite_storage()
        # All Django storages expose .save / .url / .delete. Any one is fine
        # as a smoke check that we got a storage-like object, not None.
        self.assertTrue(hasattr(storage, "save"))
        self.assertTrue(hasattr(storage, "url"))
        self.assertTrue(hasattr(storage, "delete"))

    def test_default_is_filesystem_in_tests(self):
        from django.core.files.storage import FileSystemStorage
        # The test-mode block in settings.py keeps sprite_storage pinned to
        # FileSystem so SimpleUploadedFile tests don't reach for Ceph.
        self.assertIsInstance(sprite_storage(), FileSystemStorage)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_storage -v 2`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.rpg.storage'`.

- [ ] **Step 3: Create `apps/rpg/storage.py`**

Create `apps/rpg/storage.py`:

```python
"""Storage accessor for the sprite bucket.

Kept in its own module so model files stay clean, and so the S3 backend
can be swapped for FileSystemStorage in tests via override_settings
without touching model definitions.
"""
from django.core.files.storage import storages


def sprite_storage():
    """Return the storage backend dedicated to the sprite bucket.

    Resolves to ``STORAGES["sprites"]`` via Django's storage registry.
    Use this in ImageField's ``storage=`` argument so the field picks up
    the current dict at runtime — not at import time — which makes
    ``override_settings(STORAGES={...})`` work in tests.
    """
    return storages["sprites"]
```

- [ ] **Step 4: Update `config/settings.py` to define `STORAGES["sprites"]`**

In `config/settings.py`, replace the `STORAGES = {…}` block at line 245 with:

```python
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    # Sprites: dedicated public-read bucket on Ceph with long-lived Cache-Control
    # headers so browsers cache aggressively and no presigning is needed.
    # Defaults to FileSystemStorage in dev/test; flips to S3 when USE_S3_STORAGE=true.
    "sprites": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
```

Then in the `if USE_S3_STORAGE:` block (currently ends at line 289 with `STORAGES["default"] = {…}`), add sprite-specific S3 wiring. Replace that `if USE_S3_STORAGE:` block with:

```python
if USE_S3_STORAGE:
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL", "")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_ADDRESSING_STYLE = "path"
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = int(os.environ.get("AWS_QUERYSTRING_EXPIRE", "3600"))
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None

    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}

    # Sprite bucket — public-read, immutable cache, no presigning.
    STORAGES["sprites"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.environ.get("SPRITE_S3_BUCKET", "abby-sprites"),
            "endpoint_url": os.environ.get(
                "SPRITE_S3_ENDPOINT", AWS_S3_ENDPOINT_URL,
            ),
            "access_key": AWS_ACCESS_KEY_ID,
            "secret_key": AWS_SECRET_ACCESS_KEY,
            "region_name": AWS_S3_REGION_NAME,
            "addressing_style": "path",
            "signature_version": "s3v4",
            "querystring_auth": False,   # public URLs, no presigning
            "default_acl": "public-read",
            "file_overwrite": True,       # content-hashed filenames → collisions mean identical bytes
            "object_parameters": {
                "CacheControl": "public, max-age=31536000, immutable",
            },
            "custom_domain": os.environ.get("SPRITE_S3_CUSTOM_DOMAIN") or None,
        },
    }
```

At the bottom of `settings.py` (just before/inside the `if "test" in sys.argv` block if present, otherwise right at the end), ensure `STORAGES["sprites"]` stays on FileSystemStorage for tests:

```python
if "test" in sys.argv:
    STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    STORAGES["sprites"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
```

- [ ] **Step 5: Update the `SpriteAsset.image` field to use `sprite_storage()`**

In `apps/rpg/models.py`, replace:

```python
    image = models.ImageField(upload_to="rpg-sprites/", storage=None)
```

with:

```python
    from apps.rpg.storage import sprite_storage
    image = models.ImageField(upload_to="rpg-sprites/", storage=sprite_storage)
```

Django accepts a callable for `storage=`, which defers resolution to runtime.

- [ ] **Step 6: Add env var entries to `.env.example`**

Append to `.env.example`:

```
# --- Sprite storage (Phase 1 of chat-to-prod sprite authoring) ------------
# Dedicated public-read bucket for runtime-authored sprites. Defaults below
# match the Coolify production service; leave blank locally to use
# FileSystemStorage.
SPRITE_S3_BUCKET=abby-sprites
SPRITE_S3_ENDPOINT=https://s3.neato.digital
SPRITE_S3_CUSTOM_DOMAIN=
```

- [ ] **Step 7: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_storage apps.rpg.tests.test_sprite_asset_model -v 2`

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add config/settings.py .env.example apps/rpg/storage.py apps/rpg/models.py apps/rpg/tests/test_sprite_storage.py
git commit -m "feat: wire STORAGES['sprites'] backend for sprite bucket"
```

---

### Task 3: `register_sprite` service — static happy path

**Files:**
- Create: `apps/rpg/sprite_authoring.py`
- Create: `apps/rpg/tests/test_sprite_authoring.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_sprite_authoring.py`:

```python
import base64
import io
from PIL import Image
from django.test import TestCase
from apps.accounts.models import User
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import register_sprite


def _png_bytes(size=(32, 32), color=(255, 0, 0, 255)):
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class RegisterSpriteStaticTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")

    def test_registers_static_png_from_base64(self):
        png = _png_bytes((32, 32))
        b64 = base64.b64encode(png).decode()

        result = register_sprite(
            slug="dragon",
            image_b64=b64,
            pack="test-pack",
            frame_count=1,
            fps=0,
            frame_layout="horizontal",
            actor=self.parent,
        )

        self.assertEqual(result["slug"], "dragon")
        self.assertEqual(result["frame_count"], 1)
        self.assertEqual(result["fps"], 0)
        self.assertEqual(result["frame_width_px"], 32)
        self.assertEqual(result["frame_height_px"], 32)
        self.assertEqual(result["pack"], "test-pack")
        self.assertTrue(result["url"])  # non-empty URL string

        row = SpriteAsset.objects.get(slug="dragon")
        self.assertEqual(row.created_by, self.parent)
        self.assertEqual(row.frame_width_px, 32)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteStaticTests -v 2`

Expected: FAIL — `ModuleNotFoundError: No module named 'apps.rpg.sprite_authoring'`.

- [ ] **Step 3: Create `apps/rpg/sprite_authoring.py` with minimal impl**

Create `apps/rpg/sprite_authoring.py`:

```python
"""Service layer for runtime sprite authoring.

Orchestrates: decode/download PNG bytes → validate with Pillow → compute
content hash → upload to the sprite bucket (via SpriteAsset.image) →
upsert the DB row. Callable from both the MCP tool layer and from the
data-migration that imports legacy sprites.

The service intentionally does NOT check permissions — callers (MCP tools,
API views, migrations) enforce their own auth. This mirrors the
project's other service modules (e.g., apps/rpg/services.py).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
from typing import Any, Optional

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from apps.accounts.models import User
from apps.rpg.models import SpriteAsset


MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB cap for single-sprite uploads
MAX_DIMENSION_PX = 4096


class SpriteAuthoringError(Exception):
    """Raised on any user-visible validation failure in the service layer.

    Callers translate this to their surface's error type — MCP tools wrap
    it in MCPValidationError, API views return 400.
    """


def _decode_b64(b64: str) -> bytes:
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SpriteAuthoringError(f"image_b64 is not valid base64: {exc}")


def _validate_png(png_bytes: bytes) -> tuple[int, int]:
    if len(png_bytes) > MAX_IMAGE_BYTES:
        raise SpriteAuthoringError(
            f"image exceeds {MAX_IMAGE_BYTES} bytes "
            f"({len(png_bytes)} received).",
        )
    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.verify()  # raises on corrupt images
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteAuthoringError(f"not a valid PNG/WebP image: {exc}")
    # Pillow verify() closes the image; reopen for dimensions.
    img = Image.open(io.BytesIO(png_bytes))
    if img.format not in ("PNG", "WEBP"):
        raise SpriteAuthoringError(f"format {img.format!r} not supported; use PNG or WebP")
    if img.width > MAX_DIMENSION_PX or img.height > MAX_DIMENSION_PX:
        raise SpriteAuthoringError(
            f"image dimensions {img.width}x{img.height} exceed "
            f"{MAX_DIMENSION_PX}px limit.",
        )
    return img.width, img.height


def register_sprite(
    *,
    slug: str,
    image_b64: Optional[str] = None,
    image_url: Optional[str] = None,  # URL path implemented in later task
    pack: str = "user-authored",
    frame_count: int = 1,
    fps: int = 0,
    frame_layout: str = "horizontal",
    overwrite: bool = False,
    actor: Optional[User] = None,
) -> dict[str, Any]:
    """Register a single sprite (static or animation strip) from bytes.

    Exactly one of ``image_b64`` / ``image_url`` must be provided.
    Returns a structured dict matching the MCP tool's contract.
    """
    if bool(image_b64) == bool(image_url):
        raise SpriteAuthoringError(
            "exactly one of image_b64 or image_url must be provided.",
        )

    if image_b64:
        png_bytes = _decode_b64(image_b64)
    else:
        # URL input is implemented in Task 6; fail loudly here for now.
        raise SpriteAuthoringError("image_url not yet implemented")

    total_w, total_h = _validate_png(png_bytes)

    # Compute per-frame dimensions for animation strips.
    if frame_count == 1:
        frame_w, frame_h = total_w, total_h
    elif frame_layout == "horizontal":
        if total_w % frame_count != 0:
            raise SpriteAuthoringError(
                f"animated strip width {total_w}px is not divisible by "
                f"frame_count={frame_count}.",
            )
        frame_w, frame_h = total_w // frame_count, total_h
    else:  # vertical
        if total_h % frame_count != 0:
            raise SpriteAuthoringError(
                f"animated strip height {total_h}px is not divisible by "
                f"frame_count={frame_count}.",
            )
        frame_w, frame_h = total_w, total_h // frame_count

    digest = hashlib.sha256(png_bytes).hexdigest()[:8]
    filename = f"{slug}-{digest}.png"

    existing = SpriteAsset.objects.filter(slug=slug).first()
    if existing and not overwrite:
        raise SpriteAuthoringError(
            f"sprite {slug!r} already exists; pass overwrite=True to replace.",
        )
    if existing:
        existing.image.delete(save=False)  # Ceph blob first, per storage-deletes invariant

    asset = existing or SpriteAsset(slug=slug)
    asset.pack = pack
    asset.frame_count = frame_count
    asset.fps = fps
    asset.frame_width_px = frame_w
    asset.frame_height_px = frame_h
    asset.frame_layout = frame_layout
    asset.created_by = actor
    asset.full_clean()  # triggers SpriteAsset.clean() → validates frame/fps combo
    asset.image.save(filename, ContentFile(png_bytes), save=False)
    asset.save()

    return {
        "slug": asset.slug,
        "url": asset.image.url,
        "pack": asset.pack,
        "frame_count": asset.frame_count,
        "fps": asset.fps,
        "frame_width_px": asset.frame_width_px,
        "frame_height_px": asset.frame_height_px,
        "frame_layout": asset.frame_layout,
    }
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteStaticTests -v 2`

Expected: 1 test PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/sprite_authoring.py apps/rpg/tests/test_sprite_authoring.py
git commit -m "feat: register_sprite service — static base64 happy path"
```

---

### Task 4: `register_sprite` validations

**Files:**
- Modify: `apps/rpg/tests/test_sprite_authoring.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `apps/rpg/tests/test_sprite_authoring.py`:

```python
class RegisterSpriteValidationTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")

    def test_rejects_both_b64_and_url(self):
        with self.assertRaises(SpriteAuthoringError):
            register_sprite(
                slug="x", image_b64="aa", image_url="http://e/a.png",
                actor=self.parent,
            )

    def test_rejects_neither_b64_nor_url(self):
        with self.assertRaises(SpriteAuthoringError):
            register_sprite(slug="x", actor=self.parent)

    def test_rejects_malformed_base64(self):
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="x", image_b64="not-base64!!!", actor=self.parent)
        self.assertIn("base64", str(ctx.exception))

    def test_rejects_non_png_bytes(self):
        import base64
        garbage_b64 = base64.b64encode(b"hello world not a png").decode()
        with self.assertRaises(SpriteAuthoringError):
            register_sprite(slug="x", image_b64=garbage_b64, actor=self.parent)

    def test_rejects_animated_strip_width_mismatch(self):
        import base64
        # 30×16 image with frame_count=4 → 30/4 is not an integer
        png = _png_bytes((30, 16))
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(
                slug="x", image_b64=base64.b64encode(png).decode(),
                frame_count=4, fps=6, frame_layout="horizontal",
                actor=self.parent,
            )
        self.assertIn("divisible", str(ctx.exception))

    def test_slug_collision_without_overwrite(self):
        import base64
        b64 = base64.b64encode(_png_bytes()).decode()
        register_sprite(slug="taken", image_b64=b64, actor=self.parent)
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="taken", image_b64=b64, actor=self.parent)
        self.assertIn("already exists", str(ctx.exception))

    def test_slug_collision_with_overwrite_succeeds(self):
        import base64
        b64_a = base64.b64encode(_png_bytes((16, 16))).decode()
        b64_b = base64.b64encode(_png_bytes((32, 32))).decode()
        register_sprite(slug="replaceable", image_b64=b64_a, actor=self.parent)
        result = register_sprite(
            slug="replaceable", image_b64=b64_b, overwrite=True,
            actor=self.parent,
        )
        self.assertEqual(result["frame_width_px"], 32)
        self.assertEqual(SpriteAsset.objects.filter(slug="replaceable").count(), 1)
```

- [ ] **Step 2: Run tests to verify some fail**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteValidationTests -v 2`

Expected: All PASS (validations were written in Task 3's service already). If any fail, review the service in Task 3 — this task's purpose is to pin down that those validation branches are exercised.

- [ ] **Step 3: Commit**

```bash
git add apps/rpg/tests/test_sprite_authoring.py
git commit -m "test: register_sprite validation coverage"
```

---

### Task 5: `register_sprite` animated strip happy path

**Files:**
- Modify: `apps/rpg/tests/test_sprite_authoring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_sprite_authoring.py`:

```python
class RegisterSpriteAnimatedTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p2", password="pw", role="parent")

    def test_horizontal_strip_4_frames(self):
        import base64
        # 128x32 = 4 frames of 32x32
        png = _png_bytes((128, 32))
        result = register_sprite(
            slug="flame", image_b64=base64.b64encode(png).decode(),
            frame_count=4, fps=6, frame_layout="horizontal",
            actor=self.parent,
        )
        self.assertEqual(result["frame_count"], 4)
        self.assertEqual(result["fps"], 6)
        self.assertEqual(result["frame_width_px"], 32)
        self.assertEqual(result["frame_height_px"], 32)

    def test_vertical_strip_3_frames(self):
        import base64
        png = _png_bytes((16, 48))  # 3 frames of 16x16
        result = register_sprite(
            slug="coin", image_b64=base64.b64encode(png).decode(),
            frame_count=3, fps=8, frame_layout="vertical",
            actor=self.parent,
        )
        self.assertEqual(result["frame_width_px"], 16)
        self.assertEqual(result["frame_height_px"], 16)
        self.assertEqual(result["frame_layout"], "vertical")
```

- [ ] **Step 2: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteAnimatedTests -v 2`

Expected: 2 tests PASS (animated branch was implemented in Task 3's service).

- [ ] **Step 3: Commit**

```bash
git add apps/rpg/tests/test_sprite_authoring.py
git commit -m "test: register_sprite animation strip coverage"
```

---

### Task 6: `register_sprite` URL input path

**Files:**
- Modify: `apps/rpg/sprite_authoring.py` (replace `raise SpriteAuthoringError("image_url not yet implemented")`)
- Modify: `apps/rpg/tests/test_sprite_authoring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_sprite_authoring.py`:

```python
from unittest.mock import patch

class RegisterSpriteFromUrlTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p3", password="pw", role="parent")

    @patch("apps.rpg.sprite_authoring.requests.get")
    def test_fetches_url_and_registers(self, mock_get):
        png_bytes = _png_bytes((32, 32))
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = png_bytes
        mock_get.return_value.headers = {"Content-Type": "image/png"}
        mock_get.return_value.raise_for_status = lambda: None

        result = register_sprite(
            slug="fetched", image_url="https://example.com/a.png",
            actor=self.parent,
        )
        self.assertEqual(result["slug"], "fetched")
        mock_get.assert_called_once_with("https://example.com/a.png", timeout=15)

    @patch("apps.rpg.sprite_authoring.requests.get")
    def test_rejects_non_image_mime(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<html>"
        mock_get.return_value.headers = {"Content-Type": "text/html"}
        mock_get.return_value.raise_for_status = lambda: None
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="x", image_url="http://e/x", actor=self.parent)
        self.assertIn("Content-Type", str(ctx.exception))

    @patch("apps.rpg.sprite_authoring.requests.get")
    def test_rejects_http_error(self, mock_get):
        import requests
        mock_get.return_value.status_code = 404
        mock_get.return_value.raise_for_status = (
            lambda: (_ for _ in ()).throw(requests.HTTPError("404"))
        )
        with self.assertRaises(SpriteAuthoringError):
            register_sprite(slug="x", image_url="http://e/missing", actor=self.parent)
```

- [ ] **Step 2: Run, verify new tests fail**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteFromUrlTests -v 2`

Expected: 3 tests FAIL with `SpriteAuthoringError: image_url not yet implemented` or similar.

- [ ] **Step 3: Implement URL fetch in `apps/rpg/sprite_authoring.py`**

At the top of `apps/rpg/sprite_authoring.py`, add:

```python
import requests
```

Replace:

```python
    if image_b64:
        png_bytes = _decode_b64(image_b64)
    else:
        # URL input is implemented in Task 6; fail loudly here for now.
        raise SpriteAuthoringError("image_url not yet implemented")
```

with:

```python
    if image_b64:
        png_bytes = _decode_b64(image_b64)
    else:
        png_bytes = _fetch_url(image_url)
```

Add helper function (above `register_sprite`):

```python
def _fetch_url(url: str) -> bytes:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise SpriteAuthoringError(f"failed to fetch image: {exc}")
    ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if ctype not in ("image/png", "image/webp"):
        raise SpriteAuthoringError(
            f"Content-Type {ctype!r} not accepted; must be image/png or image/webp",
        )
    if len(resp.content) > MAX_IMAGE_BYTES:
        raise SpriteAuthoringError(
            f"fetched image exceeds {MAX_IMAGE_BYTES} bytes",
        )
    return resp.content
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteFromUrlTests -v 2`

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/sprite_authoring.py apps/rpg/tests/test_sprite_authoring.py
git commit -m "feat: register_sprite accepts image_url in addition to base64"
```

---

### Task 7: `register_sprite_batch` service

**Files:**
- Modify: `apps/rpg/sprite_authoring.py` (append `register_sprite_batch`)
- Modify: `apps/rpg/tests/test_sprite_authoring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_sprite_authoring.py`:

```python
class RegisterSpriteBatchTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p4", password="pw", role="parent")

    def test_slices_sheet_into_multiple_tiles(self):
        import base64
        # 64x32 sheet, tile_size=32 → 2 columns × 1 row
        sheet = _png_bytes((64, 32), color=(0, 255, 0, 255))
        result = register_sprite_batch(
            sheet_b64=base64.b64encode(sheet).decode(),
            tile_size=32,
            tiles=[
                {"slug": "tile-a", "col": 0, "row": 0},
                {"slug": "tile-b", "col": 1, "row": 0},
            ],
            actor=self.parent,
        )
        self.assertEqual(len(result["registered"]), 2)
        self.assertEqual(result["skipped"], [])
        self.assertEqual(SpriteAsset.objects.filter(slug__startswith="tile-").count(), 2)

    def test_registers_animated_tile(self):
        import base64
        # 128x32 sheet, tile_size=32 → 4 columns × 1 row
        sheet = _png_bytes((128, 32))
        result = register_sprite_batch(
            sheet_b64=base64.b64encode(sheet).decode(),
            tile_size=32,
            tiles=[{
                "slug": "flame-anim", "col": 0, "row": 0,
                "frame_count": 4, "fps": 6,
            }],
            actor=self.parent,
        )
        self.assertEqual(result["registered"][0]["frame_count"], 4)
        self.assertEqual(result["registered"][0]["frame_width_px"], 32)
```

Import at top of test file:

```python
from apps.rpg.sprite_authoring import register_sprite, register_sprite_batch, SpriteAuthoringError
```

- [ ] **Step 2: Run, verify fail**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteBatchTests -v 2`

Expected: FAIL — `ImportError: cannot import 'register_sprite_batch'`.

- [ ] **Step 3: Implement `register_sprite_batch`**

Append to `apps/rpg/sprite_authoring.py`:

```python
MAX_SHEET_BYTES = 20 * 1024 * 1024  # sheets can be up to 20 MB


def register_sprite_batch(
    *,
    sheet_b64: Optional[str] = None,
    sheet_url: Optional[str] = None,
    tile_size: int,
    tiles: list[dict[str, Any]],
    overwrite: bool = False,
    actor: Optional[User] = None,
) -> dict[str, Any]:
    """Slice a spritesheet into many named tile sprites in one call.

    Each tile dict accepts: ``slug`` (required), ``col`` (required),
    ``row`` (required), ``frame_count`` (default 1 — animation frames
    extend rightward from col), ``fps`` (default 0), ``pack`` (default
    "user-authored"). Per-tile failures are collected in the ``skipped``
    list rather than aborting the whole batch.
    """
    if bool(sheet_b64) == bool(sheet_url):
        raise SpriteAuthoringError("exactly one of sheet_b64 or sheet_url must be provided.")

    if sheet_b64:
        sheet_bytes = _decode_b64(sheet_b64)
    else:
        sheet_bytes = _fetch_url(sheet_url)

    if len(sheet_bytes) > MAX_SHEET_BYTES:
        raise SpriteAuthoringError(f"sheet exceeds {MAX_SHEET_BYTES} bytes")

    try:
        sheet_img = Image.open(io.BytesIO(sheet_bytes))
        sheet_img.load()  # force decode to catch corruption
    except (UnidentifiedImageError, OSError) as exc:
        raise SpriteAuthoringError(f"sheet is not a valid image: {exc}")

    if sheet_img.format not in ("PNG", "WEBP"):
        raise SpriteAuthoringError(f"sheet format {sheet_img.format!r} not supported")

    cols_max = sheet_img.width // tile_size
    rows_max = sheet_img.height // tile_size

    registered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for tile in tiles:
        slug = tile["slug"]
        col = tile["col"]
        row = tile["row"]
        fc = tile.get("frame_count", 1)
        fps = tile.get("fps", 0)
        pack = tile.get("pack", "user-authored")

        # Bounds check: tile extends `fc` columns to the right from (col, row)
        if col < 0 or row < 0 or row >= rows_max or col + fc > cols_max:
            skipped.append({
                "slug": slug,
                "reason": f"tile out of bounds (col={col}, row={row}, fc={fc}; sheet is {cols_max}x{rows_max} tiles)",
            })
            continue

        # Crop the tile region and re-encode as standalone PNG
        left = col * tile_size
        top = row * tile_size
        right = (col + fc) * tile_size
        bottom = (row + 1) * tile_size
        crop = sheet_img.crop((left, top, right, bottom))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        tile_bytes = buf.getvalue()
        tile_b64 = base64.b64encode(tile_bytes).decode()

        try:
            result = register_sprite(
                slug=slug,
                image_b64=tile_b64,
                pack=pack,
                frame_count=fc,
                fps=fps,
                frame_layout="horizontal",
                overwrite=overwrite,
                actor=actor,
            )
            registered.append(result)
        except SpriteAuthoringError as exc:
            skipped.append({"slug": slug, "reason": str(exc)})

    return {"registered": registered, "skipped": skipped}
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteBatchTests -v 2`

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/sprite_authoring.py apps/rpg/tests/test_sprite_authoring.py
git commit -m "feat: register_sprite_batch for sheet-to-many-tiles authoring"
```

---

### Task 8: `register_sprite_batch` partial failures (out-of-bounds, slug collision)

**Files:**
- Modify: `apps/rpg/tests/test_sprite_authoring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_sprite_authoring.py`:

```python
class RegisterSpriteBatchPartialFailureTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p5", password="pw", role="parent")

    def test_out_of_bounds_tile_skipped_others_registered(self):
        import base64
        sheet = _png_bytes((64, 32))  # 2x1 tiles at tile_size=32
        result = register_sprite_batch(
            sheet_b64=base64.b64encode(sheet).decode(),
            tile_size=32,
            tiles=[
                {"slug": "good", "col": 0, "row": 0},
                {"slug": "bad", "col": 5, "row": 0},  # out of bounds
            ],
            actor=self.parent,
        )
        self.assertEqual(len(result["registered"]), 1)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["slug"], "bad")
        self.assertIn("out of bounds", result["skipped"][0]["reason"])

    def test_slug_collision_reported_in_skipped(self):
        import base64
        # Pre-seed a sprite with slug "taken"
        seed = base64.b64encode(_png_bytes((16, 16))).decode()
        register_sprite(slug="taken", image_b64=seed, actor=self.parent)

        sheet = _png_bytes((64, 32))
        result = register_sprite_batch(
            sheet_b64=base64.b64encode(sheet).decode(),
            tile_size=32,
            tiles=[{"slug": "taken", "col": 0, "row": 0}],
            actor=self.parent,
        )
        self.assertEqual(result["registered"], [])
        self.assertEqual(len(result["skipped"]), 1)
        self.assertIn("already exists", result["skipped"][0]["reason"])
```

- [ ] **Step 2: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.RegisterSpriteBatchPartialFailureTests -v 2`

Expected: 2 PASS (partial-failure handling is already in Task 7's service).

- [ ] **Step 3: Commit**

```bash
git add apps/rpg/tests/test_sprite_authoring.py
git commit -m "test: register_sprite_batch partial-failure coverage"
```

---

### Task 9: `delete_sprite` service (blob-first)

**Files:**
- Modify: `apps/rpg/sprite_authoring.py`
- Modify: `apps/rpg/tests/test_sprite_authoring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_sprite_authoring.py`:

```python
class DeleteSpriteTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p6", password="pw", role="parent")

    def test_delete_removes_row_and_blob(self):
        import base64
        b64 = base64.b64encode(_png_bytes()).decode()
        register_sprite(slug="gone", image_b64=b64, actor=self.parent)
        self.assertEqual(SpriteAsset.objects.filter(slug="gone").count(), 1)

        delete_sprite(slug="gone")

        self.assertEqual(SpriteAsset.objects.filter(slug="gone").count(), 0)

    def test_delete_unknown_slug_raises(self):
        with self.assertRaises(SpriteAuthoringError):
            delete_sprite(slug="never-existed")

    def test_delete_calls_blob_before_row(self):
        import base64
        from unittest.mock import patch
        b64 = base64.b64encode(_png_bytes()).decode()
        register_sprite(slug="order", image_b64=b64, actor=self.parent)
        asset = SpriteAsset.objects.get(slug="order")

        call_order: list[str] = []
        orig_blob = asset.image.delete
        orig_row = asset.delete

        def record_blob(*a, **kw):
            call_order.append("blob")
            return orig_blob(*a, **kw)

        def record_row(*a, **kw):
            call_order.append("row")
            return orig_row(*a, **kw)

        with patch.object(SpriteAsset.objects, "get", return_value=asset):
            with patch.object(asset.image, "delete", side_effect=record_blob):
                with patch.object(asset, "delete", side_effect=record_row):
                    delete_sprite(slug="order")

        self.assertEqual(call_order, ["blob", "row"])
```

Import:

```python
from apps.rpg.sprite_authoring import delete_sprite
```

- [ ] **Step 2: Run, verify fail**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.DeleteSpriteTests -v 2`

Expected: FAIL — `ImportError: cannot import 'delete_sprite'`.

- [ ] **Step 3: Implement `delete_sprite`**

Append to `apps/rpg/sprite_authoring.py`:

```python
def delete_sprite(*, slug: str) -> dict[str, Any]:
    """Remove a sprite's DB row AND its Ceph blob.

    Blob deletion runs first (per the project's storage-deletes
    invariant): if Ceph rejects the delete, the DB row stays and we
    don't end up with a live blob + missing row.
    """
    try:
        asset = SpriteAsset.objects.get(slug=slug)
    except SpriteAsset.DoesNotExist:
        raise SpriteAuthoringError(f"sprite {slug!r} not found")

    asset.image.delete(save=False)  # blob first
    asset.delete()
    return {"slug": slug, "deleted": True}
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.DeleteSpriteTests -v 2`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/sprite_authoring.py apps/rpg/tests/test_sprite_authoring.py
git commit -m "feat: delete_sprite service (blob-first, matches storage-deletes invariant)"
```

---

### Task 10: `get_catalog` service + catalog ETag computation

**Files:**
- Modify: `apps/rpg/sprite_authoring.py`
- Modify: `apps/rpg/tests/test_sprite_authoring.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/rpg/tests/test_sprite_authoring.py`:

```python
class GetCatalogTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p7", password="pw", role="parent")
        import base64
        b64 = base64.b64encode(_png_bytes((32, 32))).decode()
        b64_anim = base64.b64encode(_png_bytes((128, 32))).decode()
        register_sprite(slug="static-a", image_b64=b64, actor=self.parent)
        register_sprite(slug="anim-b", image_b64=b64_anim,
                        frame_count=4, fps=6, actor=self.parent)

    def test_catalog_shape(self):
        result = get_catalog()
        self.assertIn("sprites", result)
        self.assertIn("etag", result)
        self.assertIsInstance(result["etag"], str)
        self.assertEqual(len(result["etag"]), 16)  # sha256[:16]

        sprites = result["sprites"]
        self.assertIn("static-a", sprites)
        self.assertIn("anim-b", sprites)

        self.assertEqual(sprites["static-a"]["frames"], 1)
        self.assertEqual(sprites["static-a"]["fps"], 0)
        self.assertEqual(sprites["static-a"]["w"], 32)
        self.assertEqual(sprites["static-a"]["layout"], "horizontal")
        self.assertTrue(sprites["static-a"]["url"])

        self.assertEqual(sprites["anim-b"]["frames"], 4)
        self.assertEqual(sprites["anim-b"]["fps"], 6)

    def test_catalog_etag_changes_on_write(self):
        first = get_catalog()["etag"]
        import base64
        register_sprite(
            slug="new-one",
            image_b64=base64.b64encode(_png_bytes()).decode(),
            actor=self.parent,
        )
        second = get_catalog()["etag"]
        self.assertNotEqual(first, second)

    def test_catalog_etag_stable_without_changes(self):
        a = get_catalog()["etag"]
        b = get_catalog()["etag"]
        self.assertEqual(a, b)
```

Import:

```python
from apps.rpg.sprite_authoring import get_catalog
```

- [ ] **Step 2: Run, verify fail**

Expected: `ImportError: cannot import 'get_catalog'`.

- [ ] **Step 3: Implement `get_catalog`**

Append to `apps/rpg/sprite_authoring.py`:

```python
def get_catalog() -> dict[str, Any]:
    """Return the full slug → metadata map for the frontend catalog API.

    Response shape matches the ``GET /api/sprites/catalog/`` contract.
    The ``etag`` is a stable hash of (slug, image-key) pairs so a client
    can send If-None-Match on subsequent fetches.
    """
    assets = SpriteAsset.objects.order_by("slug").only(
        "slug", "image", "frame_count", "fps",
        "frame_width_px", "frame_height_px", "frame_layout",
    )
    sprites: dict[str, dict[str, Any]] = {}
    etag_parts: list[str] = []
    for a in assets:
        sprites[a.slug] = {
            "url": a.image.url,
            "frames": a.frame_count,
            "fps": a.fps,
            "w": a.frame_width_px,
            "h": a.frame_height_px,
            "layout": a.frame_layout,
        }
        etag_parts.append(f"{a.slug}:{a.image.name}")
    etag = hashlib.sha256("|".join(etag_parts).encode()).hexdigest()[:16]
    return {"sprites": sprites, "etag": etag}
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_authoring.GetCatalogTests -v 2`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/rpg/sprite_authoring.py apps/rpg/tests/test_sprite_authoring.py
git commit -m "feat: get_catalog service with etag for catalog API"
```

---

### Task 11: MCP tool Pydantic schemas

**Files:**
- Modify: `apps/mcp_server/schemas.py` (append new schemas)

- [ ] **Step 1: Append schemas to `apps/mcp_server/schemas.py`**

At the end of `apps/mcp_server/schemas.py`, append:

```python
# ---------------------------------------------------------------------------
# Sprite authoring (chat-to-prod runtime sprites)
# ---------------------------------------------------------------------------

FrameLayout = Literal["horizontal", "vertical"]
SPRITE_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class RegisterSpriteIn(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=SPRITE_SLUG_PATTERN)
    image_b64: Optional[str] = Field(
        default=None,
        description="Base64-encoded PNG or WebP bytes. Exactly one of image_b64/image_url required.",
    )
    image_url: Optional[str] = Field(
        default=None,
        description="https URL to PNG/WebP. Exactly one of image_b64/image_url required.",
    )
    pack: str = Field(default="user-authored", max_length=40)
    frame_count: int = Field(default=1, ge=1, le=64)
    fps: int = Field(default=0, ge=0, le=30)
    frame_layout: FrameLayout = "horizontal"
    overwrite: bool = False


class SpriteTileDecl(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=SPRITE_SLUG_PATTERN)
    col: int = Field(ge=0, le=1024)
    row: int = Field(ge=0, le=1024)
    frame_count: int = Field(default=1, ge=1, le=64)
    fps: int = Field(default=0, ge=0, le=30)
    pack: str = Field(default="user-authored", max_length=40)


class RegisterSpriteBatchIn(_Base):
    sheet_b64: Optional[str] = None
    sheet_url: Optional[str] = None
    tile_size: int = Field(ge=8, le=256)
    tiles: list[SpriteTileDecl] = Field(min_length=1, max_length=200)
    overwrite: bool = False


class ListSpritesIn(_Base):
    pack: Optional[str] = None
    limit: int = Field(default=200, ge=1, le=500)


class DeleteSpriteIn(_Base):
    slug: str = Field(min_length=1, max_length=64, pattern=SPRITE_SLUG_PATTERN)
```

- [ ] **Step 2: Verify schemas load cleanly**

Run: `docker compose exec django python -c "from apps.mcp_server.schemas import RegisterSpriteIn, RegisterSpriteBatchIn, ListSpritesIn, DeleteSpriteIn; print('OK')"`

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add apps/mcp_server/schemas.py
git commit -m "feat: Pydantic schemas for sprite authoring MCP tools"
```

---

### Task 12: MCP tool wrappers — four new tools

**Files:**
- Create: `apps/mcp_server/tools/sprite_authoring.py`
- Modify: `apps/mcp_server/tools/__init__.py` (if needed to register module — usually auto-discovered)
- Create: `apps/mcp_server/tests/test_tools_sprite_authoring.py`

- [ ] **Step 1: Write the failing test**

Create `apps/mcp_server/tests/test_tools_sprite_authoring.py`:

```python
import base64
import io
from PIL import Image
from django.test import TestCase
from apps.accounts.models import User
from apps.rpg.models import SpriteAsset

from apps.mcp_server.context import _current_user_ctx  # context var used by get_current_user
from apps.mcp_server.schemas import (
    RegisterSpriteIn, RegisterSpriteBatchIn, ListSpritesIn, DeleteSpriteIn,
    SpriteTileDecl,
)
from apps.mcp_server.tools.sprite_authoring import (
    register_sprite as tool_register_sprite,
    register_sprite_batch as tool_register_sprite_batch,
    list_sprites as tool_list_sprites,
    delete_sprite as tool_delete_sprite,
)


def _png_b64(size=(32, 32)):
    img = Image.new("RGBA", size, (0, 0, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class SpriteAuthoringToolTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="kid", password="pw", role="child")

    def _as_parent(self):
        return _current_user_ctx.set(self.parent)

    def _as_child(self):
        return _current_user_ctx.set(self.child)

    def test_register_sprite_requires_parent(self):
        tok = self._as_child()
        try:
            from apps.mcp_server.errors import MCPPermissionDenied
            with self.assertRaises(MCPPermissionDenied):
                tool_register_sprite(RegisterSpriteIn(slug="x", image_b64=_png_b64()))
        finally:
            _current_user_ctx.reset(tok)

    def test_register_sprite_happy_path(self):
        tok = self._as_parent()
        try:
            result = tool_register_sprite(RegisterSpriteIn(slug="t1", image_b64=_png_b64()))
            self.assertEqual(result["slug"], "t1")
            self.assertTrue(SpriteAsset.objects.filter(slug="t1").exists())
        finally:
            _current_user_ctx.reset(tok)

    def test_list_sprites(self):
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(slug="t2", image_b64=_png_b64()))
            tool_register_sprite(RegisterSpriteIn(slug="t3", image_b64=_png_b64(), pack="other"))
            result = tool_list_sprites(ListSpritesIn())
            slugs = {s["slug"] for s in result["sprites"]}
            self.assertIn("t2", slugs)
            self.assertIn("t3", slugs)
        finally:
            _current_user_ctx.reset(tok)

    def test_list_sprites_filter_by_pack(self):
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(slug="t4", image_b64=_png_b64(), pack="a"))
            tool_register_sprite(RegisterSpriteIn(slug="t5", image_b64=_png_b64(), pack="b"))
            result = tool_list_sprites(ListSpritesIn(pack="a"))
            self.assertEqual({s["slug"] for s in result["sprites"]}, {"t4"})
        finally:
            _current_user_ctx.reset(tok)

    def test_delete_sprite(self):
        tok = self._as_parent()
        try:
            tool_register_sprite(RegisterSpriteIn(slug="bye", image_b64=_png_b64()))
            result = tool_delete_sprite(DeleteSpriteIn(slug="bye"))
            self.assertEqual(result, {"slug": "bye", "deleted": True})
            self.assertFalse(SpriteAsset.objects.filter(slug="bye").exists())
        finally:
            _current_user_ctx.reset(tok)

    def test_register_sprite_batch(self):
        tok = self._as_parent()
        try:
            sheet = _png_b64((64, 32))
            result = tool_register_sprite_batch(RegisterSpriteBatchIn(
                sheet_b64=sheet,
                tile_size=32,
                tiles=[
                    SpriteTileDecl(slug="b1", col=0, row=0),
                    SpriteTileDecl(slug="b2", col=1, row=0),
                ],
            ))
            self.assertEqual(len(result["registered"]), 2)
            self.assertEqual(result["skipped"], [])
        finally:
            _current_user_ctx.reset(tok)
```

- [ ] **Step 2: Verify context variable name**

Confirm the exact context variable used for the authenticated user:

```bash
grep -n "ContextVar\|get_current_user\|_current_user" apps/mcp_server/context.py | head
```

If the variable is named differently than `_current_user_ctx`, update the test imports above.

- [ ] **Step 3: Run, verify fail**

Run: `docker compose exec django python manage.py test apps.mcp_server.tests.test_tools_sprite_authoring -v 2`

Expected: FAIL — `ModuleNotFoundError: No module named 'apps.mcp_server.tools.sprite_authoring'`.

Note: the existing file `apps/mcp_server/tools/sprite_assets.py` stays untouched during Phase 1 per the spec's rollout plan. We add a NEW file alongside it.

- [ ] **Step 4: Create `apps/mcp_server/tools/sprite_authoring.py`**

Create `apps/mcp_server/tools/sprite_authoring.py`:

```python
"""MCP tools for runtime sprite authoring.

Replaces the build-time scripts/sprite_manifest.yaml flow with four
focused tools: register_sprite (single), register_sprite_batch (sheet →
many tiles), list_sprites, delete_sprite. All write through the
SpriteAsset model and the dedicated ``abby-sprites`` Ceph bucket.

The legacy ``register_sprite_assets`` tool in sprite_assets.py stays
wired for local-dev source-tree authoring until the Deploy 3 cleanup
PR removes it.
"""
from __future__ import annotations

from typing import Any

from apps.rpg import sprite_authoring as svc
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import SpriteAuthoringError

from ..context import require_parent, get_current_user
from ..errors import MCPValidationError, safe_tool
from ..schemas import (
    DeleteSpriteIn,
    ListSpritesIn,
    RegisterSpriteBatchIn,
    RegisterSpriteIn,
)
from ..server import tool


def _wrap_svc_call(fn, **kwargs) -> dict[str, Any]:
    try:
        return fn(**kwargs)
    except SpriteAuthoringError as exc:
        raise MCPValidationError(str(exc))


@tool()
@safe_tool
def register_sprite(params: RegisterSpriteIn) -> dict[str, Any]:
    """Register one sprite (static or animation strip) from bytes or a URL.

    Parent-only. Returns the sprite's URL + dimensions + animation metadata
    so the LLM can confirm the upload and reference the slug in
    subsequent content YAML.
    """
    require_parent()
    return _wrap_svc_call(
        svc.register_sprite,
        slug=params.slug,
        image_b64=params.image_b64,
        image_url=params.image_url,
        pack=params.pack,
        frame_count=params.frame_count,
        fps=params.fps,
        frame_layout=params.frame_layout,
        overwrite=params.overwrite,
        actor=get_current_user(),
    )


@tool()
@safe_tool
def register_sprite_batch(params: RegisterSpriteBatchIn) -> dict[str, Any]:
    """Upload one spritesheet and register many named tiles in one call.

    Parent-only. Per-tile errors surface in the ``skipped`` list without
    aborting the batch, so a partial sheet registration always completes.
    Source sheet is NOT persisted — re-authoring requires re-upload.
    """
    require_parent()
    tiles = [t.model_dump() for t in params.tiles]
    return _wrap_svc_call(
        svc.register_sprite_batch,
        sheet_b64=params.sheet_b64,
        sheet_url=params.sheet_url,
        tile_size=params.tile_size,
        tiles=tiles,
        overwrite=params.overwrite,
        actor=get_current_user(),
    )


@tool()
@safe_tool
def list_sprites(params: ListSpritesIn) -> dict[str, Any]:
    """Enumerate registered sprites (parent-only, read-only).

    Used before authoring to check for slug collisions. Returns a list
    ordered by slug; filter by ``pack`` for quick narrowing.
    """
    require_parent()
    qs = SpriteAsset.objects.all()
    if params.pack:
        qs = qs.filter(pack=params.pack)
    qs = qs.order_by("slug")[: params.limit]
    return {
        "sprites": [
            {
                "slug": a.slug,
                "url": a.image.url,
                "pack": a.pack,
                "frame_count": a.frame_count,
                "fps": a.fps,
                "frame_width_px": a.frame_width_px,
                "frame_height_px": a.frame_height_px,
                "frame_layout": a.frame_layout,
            }
            for a in qs
        ],
    }


@tool()
@safe_tool
def delete_sprite(params: DeleteSpriteIn) -> dict[str, Any]:
    """Remove a sprite (DB row + Ceph blob, blob-first).

    Parent-only. Dangling ``sprite_key`` references in content YAML or
    model rows are NOT cleaned up — they emoji-fallback in the UI, which
    is the existing contract when a slug is unknown.
    """
    require_parent()
    return _wrap_svc_call(svc.delete_sprite, slug=params.slug)
```

- [ ] **Step 5: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.mcp_server.tests.test_tools_sprite_authoring -v 2`

Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/mcp_server/tools/sprite_authoring.py apps/mcp_server/tests/test_tools_sprite_authoring.py
git commit -m "feat: four MCP tools for runtime sprite authoring"
```

---

### Task 13: API endpoint `GET /api/sprites/catalog/`

**Files:**
- Modify: `apps/rpg/views.py`
- Modify: `apps/rpg/urls.py`
- Create: `apps/rpg/tests/test_sprite_catalog_api.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_sprite_catalog_api.py`:

```python
import base64
import io
from PIL import Image
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.rpg.sprite_authoring import register_sprite


def _png_b64():
    img = Image.new("RGBA", (32, 32), (200, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class SpriteCatalogAPITests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        register_sprite(slug="in-catalog", image_b64=_png_b64(), actor=self.parent)
        self.client = APIClient()

    def test_catalog_endpoint_works_unauthenticated(self):
        resp = self.client.get(reverse("sprite-catalog"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("sprites", body)
        self.assertIn("in-catalog", body["sprites"])
        self.assertIn("etag", body)
        self.assertEqual(resp["ETag"], f'"{body["etag"]}"')

    def test_catalog_304_on_matching_etag(self):
        first = self.client.get(reverse("sprite-catalog"))
        etag = first["ETag"]
        resp = self.client.get(reverse("sprite-catalog"), HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(resp.status_code, 304)
        self.assertEqual(resp.content, b"")

    def test_catalog_cache_control(self):
        resp = self.client.get(reverse("sprite-catalog"))
        self.assertIn("max-age=60", resp["Cache-Control"])
        self.assertIn("stale-while-revalidate", resp["Cache-Control"])
```

- [ ] **Step 2: Run, verify fail**

Expected: `NoReverseMatch: Reverse for 'sprite-catalog' not found.`

- [ ] **Step 3: Implement the view in `apps/rpg/views.py`**

Append to `apps/rpg/views.py`:

```python
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rpg.sprite_authoring import get_catalog


class SpriteCatalogView(APIView):
    """Public read-only sprite catalog used by the frontend provider.

    Anonymous access — the sprite URLs themselves are public-read on
    Ceph, and no child-scoped data is exposed. ETag + short max-age
    make re-fetches cheap.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        catalog = get_catalog()
        etag = f'"{catalog["etag"]}"'
        if_none_match = request.META.get("HTTP_IF_NONE_MATCH")
        if if_none_match and if_none_match == etag:
            resp = Response(status=304)
            resp["ETag"] = etag
            resp["Cache-Control"] = "public, max-age=60, stale-while-revalidate=600"
            return resp
        resp = Response(catalog)
        resp["ETag"] = etag
        resp["Cache-Control"] = "public, max-age=60, stale-while-revalidate=600"
        return resp
```

- [ ] **Step 4: Register the URL in `apps/rpg/urls.py`**

In `apps/rpg/urls.py`, append to `urlpatterns`:

```python
    path("sprites/catalog/", views.SpriteCatalogView.as_view(), name="sprite-catalog"),
```

- [ ] **Step 5: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_sprite_catalog_api -v 2`

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/rpg/views.py apps/rpg/urls.py apps/rpg/tests/test_sprite_catalog_api.py
git commit -m "feat: GET /api/sprites/catalog/ endpoint with ETag revalidation"
```

---

### Task 14: Data migration importing 72 legacy sprites

**Files:**
- Create: `apps/rpg/migrations/0013_import_legacy_sprites.py`
- Create: `apps/rpg/tests/test_legacy_sprite_migration.py`

- [ ] **Step 1: Write the failing test**

Create `apps/rpg/tests/test_legacy_sprite_migration.py`:

```python
from django.test import TestCase, override_settings
from django.core.management import call_command
from apps.rpg.models import SpriteAsset


class LegacySpriteMigrationTests(TestCase):
    """Runs the import_legacy_sprites data migration's forward function
    directly against the test DB, using the repo's real manifest +
    artwork files.

    Migration runs are idempotent, so it's safe to invoke twice.
    """

    def test_forward_creates_rows_for_every_manifest_entry(self):
        from apps.rpg.migrations import _0013_import_legacy_sprites_impl as impl
        from django.apps import apps as django_apps

        impl.import_legacy_sprites(django_apps, None)

        # Every slug in the manifest should now be a SpriteAsset with pack="core"
        count = SpriteAsset.objects.filter(pack="core").count()
        self.assertGreater(count, 50)   # there are 72 sprites today, be lenient
        # Spot-check a well-known slug from the existing manifest
        self.assertTrue(SpriteAsset.objects.filter(slug="apple").exists())

    def test_forward_is_idempotent(self):
        from apps.rpg.migrations import _0013_import_legacy_sprites_impl as impl
        from django.apps import apps as django_apps

        impl.import_legacy_sprites(django_apps, None)
        initial = SpriteAsset.objects.filter(pack="core").count()
        impl.import_legacy_sprites(django_apps, None)  # second run — should no-op
        after = SpriteAsset.objects.filter(pack="core").count()
        self.assertEqual(initial, after)
```

- [ ] **Step 2: Run, verify fail**

Expected: `ModuleNotFoundError: No module named 'apps.rpg.migrations._0013_import_legacy_sprites_impl'`.

- [ ] **Step 3: Create implementation module**

Create `apps/rpg/migrations/_0013_import_legacy_sprites_impl.py`:

```python
"""Forward/reverse functions for 0013_import_legacy_sprites.

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
```

- [ ] **Step 4: Create the migration file**

Create `apps/rpg/migrations/0013_import_legacy_sprites.py`:

```python
from django.db import migrations

from ._0013_import_legacy_sprites_impl import import_legacy_sprites, remove_legacy_sprites


class Migration(migrations.Migration):
    dependencies = [
        ("rpg", "0012_sprite_asset"),
    ]

    operations = [
        migrations.RunPython(import_legacy_sprites, remove_legacy_sprites),
    ]
```

- [ ] **Step 5: Apply the migration**

Run: `docker compose exec django python manage.py migrate rpg`

Expected: applies 0013, no errors, stdout shows migration applied.

- [ ] **Step 6: Run tests, confirm pass**

Run: `docker compose exec django python manage.py test apps.rpg.tests.test_legacy_sprite_migration -v 2`

Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/rpg/migrations/0013_import_legacy_sprites.py apps/rpg/migrations/_0013_import_legacy_sprites_impl.py apps/rpg/tests/test_legacy_sprite_migration.py
git commit -m "feat: data migration importing 72 legacy sprites to DB + Ceph"
```

---

### Task 15: Backend Phase 1 smoke check (manual / verification)

**Files:** none — operational.

- [ ] **Step 1: Deploy backend + migrations to staging/prod**

Push the Phase 1 commits. Watch CI, confirm green. Deploy to Coolify.

- [ ] **Step 2: Confirm migrations ran on prod**

```bash
docker compose exec django python manage.py showmigrations rpg | tail -5
```

Expected output includes `[X] 0012_sprite_asset` and `[X] 0013_import_legacy_sprites`.

- [ ] **Step 3: Verify 72 core sprites are in prod DB**

```bash
docker compose exec django python manage.py shell -c "from apps.rpg.models import SpriteAsset; print(SpriteAsset.objects.filter(pack='core').count())"
```

Expected: `72` (or whatever the current manifest count is — verify against `grep -c '^  [a-z]' scripts/sprite_manifest.yaml`).

- [ ] **Step 4: Verify Ceph bucket has the 72 PNGs**

```bash
aws --endpoint-url https://s3.neato.digital s3 ls s3://abby-sprites/rpg-sprites/ | wc -l
```

Expected: `72`.

- [ ] **Step 5: Verify the catalog endpoint returns them**

```bash
curl -s https://abby.bos.lol/api/sprites/catalog/ | python -c "import json, sys; d=json.load(sys.stdin); print(len(d['sprites']), 'sprites'); print('sample:', list(d['sprites'].items())[:1])"
```

Expected: `72 sprites` with a sample URL from `abby-sprites` bucket.

- [ ] **Step 6: Verify one sprite URL is publicly fetchable**

```bash
curl -I "$(curl -s https://abby.bos.lol/api/sprites/catalog/ | python -c "import json, sys; print(next(iter(json.load(sys.stdin)['sprites'].values()))['url'])")"
```

Expected: `HTTP/2 200` with `Cache-Control: public, max-age=31536000, immutable`.

If anything above fails, pause. Phase 2 assumes backend + migration are stable in prod.

---

## Phase 2: Frontend — catalog provider + animated renderer

### Task 16: API client — `fetchSpriteCatalog`

**Files:**
- Modify: `frontend/src/api/index.js`

- [ ] **Step 1: Add the fetch function**

In `frontend/src/api/index.js`, find the section with other `fetch`-style helpers and append:

```javascript
/**
 * Fetches the runtime sprite catalog. No auth; endpoint is public.
 * Supports ETag revalidation via the optional `etag` argument — pass
 * the etag from a previous response and get 304 Not Modified back
 * (returned as { notModified: true }) if nothing changed.
 */
export async function fetchSpriteCatalog(etag = null) {
  const headers = { Accept: 'application/json' };
  if (etag) headers['If-None-Match'] = `"${etag}"`;
  const resp = await fetch('/api/sprites/catalog/', { headers });
  if (resp.status === 304) return { notModified: true };
  if (!resp.ok) throw new Error(`sprite catalog fetch failed: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 2: No test here — exercised by the provider's tests in Task 17**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/index.js
git commit -m "feat: fetchSpriteCatalog API client"
```

---

### Task 17: `SpriteCatalogProvider` + `useSpriteCatalog` hook

**Files:**
- Create: `frontend/src/providers/SpriteCatalogProvider.jsx`
- Create: `frontend/src/providers/SpriteCatalogProvider.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/providers/SpriteCatalogProvider.test.jsx`:

```jsx
import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderHook, waitFor } from '@testing-library/react';
import { SpriteCatalogProvider, useSpriteCatalog } from './SpriteCatalogProvider';
import { server } from '../test/server';

function wrap({ children }) {
  return <SpriteCatalogProvider>{children}</SpriteCatalogProvider>;
}

const fakeCatalog = {
  etag: 'abc123def456',
  sprites: {
    dragon: { url: 'https://s.example/dragon.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' },
    flame: { url: 'https://s.example/flame.png', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal' },
  },
};

describe('SpriteCatalogProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    server.use(
      http.get('/api/sprites/catalog/', () =>
        HttpResponse.json(fakeCatalog, { headers: { ETag: `"${fakeCatalog.etag}"` } })
      )
    );
  });

  it('fetches the catalog and exposes getSpriteUrl/getSpriteMeta', async () => {
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    await waitFor(() => expect(result.current.getSpriteUrl('dragon')).toBe('https://s.example/dragon.png'));
    expect(result.current.getSpriteUrl('unknown')).toBeNull();

    const meta = result.current.getSpriteMeta('flame');
    expect(meta).toEqual({
      url: 'https://s.example/flame.png', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal',
    });
  });

  it('persists catalog to localStorage for warm mounts', async () => {
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    await waitFor(() => expect(result.current.getSpriteUrl('dragon')).toBeTruthy());
    expect(JSON.parse(localStorage.getItem('spriteCatalog')).sprites.dragon).toBeTruthy();
    expect(localStorage.getItem('spriteCatalogEtag')).toBe(fakeCatalog.etag);
  });

  it('honors 304 Not Modified by using cached data', async () => {
    localStorage.setItem('spriteCatalogEtag', fakeCatalog.etag);
    localStorage.setItem('spriteCatalog', JSON.stringify(fakeCatalog));

    server.use(
      http.get('/api/sprites/catalog/', () => new HttpResponse(null, { status: 304 }))
    );
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    await waitFor(() => expect(result.current.getSpriteUrl('dragon')).toBeTruthy());
  });

  it('returns null for unknown slug while catalog is still loading', () => {
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    // before waitFor triggers — fetch hasn't resolved
    expect(result.current.getSpriteUrl('dragon')).toBeNull();
  });
});
```

- [ ] **Step 2: Run, verify fail**

Run: `cd frontend && npm run test -- SpriteCatalogProvider.test.jsx`

Expected: FAIL — cannot resolve `./SpriteCatalogProvider`.

- [ ] **Step 3: Create `frontend/src/providers/SpriteCatalogProvider.jsx`**

Create `frontend/src/providers/SpriteCatalogProvider.jsx`:

```jsx
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { fetchSpriteCatalog } from '../api';

const SpriteCatalogContext = createContext({
  getSpriteUrl: () => null,
  getSpriteMeta: () => null,
});

const STORAGE_KEY = 'spriteCatalog';
const ETAG_KEY = 'spriteCatalogEtag';

/**
 * Fetches the sprite catalog once at mount, caches it in localStorage
 * for warm mounts, and revalidates via ETag. Exposes getSpriteUrl (slug → url)
 * for shape compatibility with the old Vite-bundle map, plus getSpriteMeta
 * (slug → full metadata) for animated-sprite rendering.
 *
 * Returns null from both functions while the catalog is loading (cold first
 * mount) — existing call sites already handle null via emoji fallback.
 */
export function SpriteCatalogProvider({ children }) {
  const [catalog, setCatalog] = useState(() => {
    const cached = localStorage.getItem(STORAGE_KEY);
    if (!cached) return null;
    try {
      return JSON.parse(cached);
    } catch {
      return null;
    }
  });

  useEffect(() => {
    let cancelled = false;
    const prevEtag = localStorage.getItem(ETAG_KEY);
    fetchSpriteCatalog(prevEtag)
      .then((resp) => {
        if (cancelled) return;
        if (resp.notModified) return; // cached catalog is still good
        setCatalog(resp);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(resp));
        localStorage.setItem(ETAG_KEY, resp.etag);
      })
      .catch((err) => {
        // Network failure on cold start — let call sites emoji-fallback.
        // Don't clear cached data; a stale catalog still beats no catalog.
        // eslint-disable-next-line no-console
        console.warn('sprite catalog fetch failed', err);
      });
    return () => { cancelled = true; };
  }, []);

  const value = useMemo(() => ({
    getSpriteUrl: (slug) => (catalog?.sprites?.[slug]?.url ?? null),
    getSpriteMeta: (slug) => (catalog?.sprites?.[slug] ?? null),
  }), [catalog]);

  return (
    <SpriteCatalogContext.Provider value={value}>
      {children}
    </SpriteCatalogContext.Provider>
  );
}

export function useSpriteCatalog() {
  return useContext(SpriteCatalogContext);
}
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd frontend && npm run test -- SpriteCatalogProvider.test.jsx`

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/providers/SpriteCatalogProvider.jsx frontend/src/providers/SpriteCatalogProvider.test.jsx
git commit -m "feat: SpriteCatalogProvider fetches sprite map with ETag caching"
```

---

### Task 18: Mount the provider in `App.jsx`

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Locate the AuthProvider wrapping in `App.jsx`**

Open `frontend/src/App.jsx`. Find the render tree, look for `<AuthProvider>` (or the existing root wrapper).

- [ ] **Step 2: Wrap the app with `SpriteCatalogProvider` inside `AuthProvider`**

Add import at top:

```jsx
import { SpriteCatalogProvider } from './providers/SpriteCatalogProvider';
```

Find:

```jsx
<AuthProvider>
  {/* ... existing children ... */}
</AuthProvider>
```

Replace with:

```jsx
<AuthProvider>
  <SpriteCatalogProvider>
    {/* ... existing children ... */}
  </SpriteCatalogProvider>
</AuthProvider>
```

- [ ] **Step 3: Run the existing App smoke tests**

Run: `cd frontend && npm run test -- App`

Expected: all existing App-level tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: mount SpriteCatalogProvider at app root"
```

---

### Task 19: Animation keyframes injection

**Files:**
- Modify: `frontend/src/providers/SpriteCatalogProvider.jsx`
- Modify: `frontend/src/providers/SpriteCatalogProvider.test.jsx` (append test)

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/providers/SpriteCatalogProvider.test.jsx`:

```jsx
  it('emits @keyframes for each distinct frame_count in the catalog', async () => {
    const animCatalog = {
      etag: 'anim-etag',
      sprites: {
        'flame-4':    { url: 'x', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal' },
        'flicker-2':  { url: 'x', frames: 2, fps: 4, w: 16, h: 16, layout: 'horizontal' },
        'also-4':     { url: 'x', frames: 4, fps: 8, w: 32, h: 32, layout: 'horizontal' },
        'static':     { url: 'x', frames: 1, fps: 0, w: 16, h: 16, layout: 'horizontal' },
      },
    };
    server.use(
      http.get('/api/sprites/catalog/', () =>
        HttpResponse.json(animCatalog, { headers: { ETag: `"${animCatalog.etag}"` } })
      )
    );
    renderHook(() => useSpriteCatalog(), { wrapper: wrap });

    await waitFor(() => {
      const styleTag = document.getElementById('sprite-keyframes');
      expect(styleTag).toBeTruthy();
      expect(styleTag.textContent).toContain('@keyframes sprite-cycle-4');
      expect(styleTag.textContent).toContain('@keyframes sprite-cycle-2');
      // Distinct frame_count=4 appears once, not twice
      expect(styleTag.textContent.match(/sprite-cycle-4/g).length).toBe(2); // @keyframes declaration + its body reference
    });
  });
```

- [ ] **Step 2: Run, verify fail**

Expected: FAIL — `document.getElementById('sprite-keyframes')` returns null.

- [ ] **Step 3: Add keyframe injection to the provider**

In `frontend/src/providers/SpriteCatalogProvider.jsx`, replace the `useEffect` block with:

```jsx
  useEffect(() => {
    let cancelled = false;
    const prevEtag = localStorage.getItem(ETAG_KEY);
    fetchSpriteCatalog(prevEtag)
      .then((resp) => {
        if (cancelled) return;
        if (resp.notModified) return;
        setCatalog(resp);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(resp));
        localStorage.setItem(ETAG_KEY, resp.etag);
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.warn('sprite catalog fetch failed', err);
      });
    return () => { cancelled = true; };
  }, []);

  // Emit @keyframes for each distinct frame_count present in the catalog.
  // One <style id="sprite-keyframes"> tag; one rule per distinct count.
  useEffect(() => {
    if (!catalog) return;
    const counts = new Set();
    Object.values(catalog.sprites || {}).forEach((s) => {
      if (s.frames > 1) counts.add(s.frames);
    });
    if (counts.size === 0) return;

    const rules = Array.from(counts).sort().map((n) => {
      // Width translation — background-position moves by -100% of the strip
      // width to cycle through all frames. Using percent lets the keyframe
      // work at any render size.
      return `@keyframes sprite-cycle-${n} { from { background-position: 0 0 } to { background-position: -100% 0 } }`;
    }).join('\n');

    let tag = document.getElementById('sprite-keyframes');
    if (!tag) {
      tag = document.createElement('style');
      tag.id = 'sprite-keyframes';
      document.head.appendChild(tag);
    }
    tag.textContent = rules;
  }, [catalog]);
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd frontend && npm run test -- SpriteCatalogProvider.test.jsx`

Expected: 5 PASS (4 from Task 17 + new one).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/providers/SpriteCatalogProvider.jsx frontend/src/providers/SpriteCatalogProvider.test.jsx
git commit -m "feat: inject @keyframes for each distinct animation frame_count"
```

---

### Task 20: Update `RpgSprite.jsx` for animation rendering

**Files:**
- Modify: `frontend/src/components/rpg/RpgSprite.jsx`
- Modify: `frontend/src/components/rpg/RpgSprite.test.jsx`

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/components/rpg/RpgSprite.test.jsx` with:

```jsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import RpgSprite from './RpgSprite';
import { SpriteCatalogProvider } from '../../providers/SpriteCatalogProvider';

// Seed the catalog via localStorage so the provider resolves immediately
// without network.
function seedCatalog(sprites) {
  const catalog = { etag: 'test', sprites };
  localStorage.setItem('spriteCatalog', JSON.stringify(catalog));
  localStorage.setItem('spriteCatalogEtag', 'test');
}

function renderWithCatalog(node, sprites) {
  seedCatalog(sprites);
  return render(<SpriteCatalogProvider>{node}</SpriteCatalogProvider>);
}

describe('RpgSprite', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders a static sprite as an <img>', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="dragon" icon="🐉" size={32} alt="dragon" />,
      { dragon: { url: 'https://s/dragon.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' } }
    );
    const img = screen.getByAltText('dragon');
    expect(img.tagName).toBe('IMG');
    expect(img.src).toBe('https://s/dragon.png');
  });

  it('renders an animated sprite as a span with computed animation style', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="flame" icon="🔥" size={32} alt="flame" />,
      { flame: { url: 'https://s/flame.png', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal' } }
    );
    const el = screen.getByLabelText('flame');
    expect(el.tagName).toBe('SPAN');
    const style = el.getAttribute('style') || '';
    expect(style).toContain('animation: sprite-cycle-4');
    // duration = frames/fps = 4/6 ≈ 0.666s
    expect(style).toMatch(/0\.6+s/);
    expect(style).toContain('steps(4)');
  });

  it('emoji-fallbacks for unknown slug', () => {
    renderWithCatalog(<RpgSprite spriteKey="missing" icon="✨" size={32} />, {});
    expect(screen.getByText('✨')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, verify fail**

Run: `cd frontend && npm run test -- RpgSprite.test.jsx`

Expected: FAILs on the animated-sprite test (existing component has no animation branch).

- [ ] **Step 3: Rewrite `frontend/src/components/rpg/RpgSprite.jsx`**

Replace the entire contents of `frontend/src/components/rpg/RpgSprite.jsx` with:

```jsx
import { useSpriteCatalog } from '../../providers/SpriteCatalogProvider';

const SIZE_TO_TEXT_CLASS = {
  24: 'text-xl',
  32: 'text-2xl',
  40: 'text-3xl',
  48: 'text-4xl',
  56: 'text-5xl',
  64: 'text-6xl',
  80: 'text-7xl',
  96: 'text-8xl',
};

/**
 * Renders an RPG entity icon. Branches on sprite metadata:
 *  - static (frames=1): plain <img>
 *  - animated (frames>1): <span> with CSS background-position animation
 *  - unknown slug or catalog still loading: emoji fallback
 */
export default function RpgSprite({
  spriteKey,
  icon,
  size = 32,
  className = '',
  alt = '',
}) {
  const { getSpriteMeta } = useSpriteCatalog();
  const meta = getSpriteMeta(spriteKey);

  if (meta && meta.frames === 1) {
    return (
      <img
        src={meta.url}
        alt={alt || spriteKey || 'sprite'}
        width={size}
        height={size}
        style={{ imageRendering: 'pixelated', width: size, height: size }}
        className={className}
      />
    );
  }

  if (meta && meta.frames > 1) {
    const duration = (meta.frames / meta.fps).toFixed(3);
    return (
      <span
        role="img"
        aria-label={alt || spriteKey || 'sprite'}
        className={`inline-block ${className}`}
        style={{
          width: size,
          height: size,
          backgroundImage: `url(${meta.url})`,
          backgroundSize: `${meta.frames * 100}% 100%`,
          imageRendering: 'pixelated',
          animation: `sprite-cycle-${meta.frames} ${duration}s steps(${meta.frames}) infinite`,
        }}
      />
    );
  }

  // Emoji fallback
  const cls = SIZE_TO_TEXT_CLASS[size];
  if (cls) {
    return (
      <span className={`leading-none inline-block ${cls} ${className}`} aria-label={alt}>
        {icon || '✨'}
      </span>
    );
  }
  return (
    <span
      className={`leading-none inline-block ${className}`}
      style={{ fontSize: size }}
      aria-label={alt}
    >
      {icon || '✨'}
    </span>
  );
}
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `cd frontend && npm run test -- RpgSprite.test.jsx`

Expected: 3 PASS.

- [ ] **Step 5: Add prefers-reduced-motion rule**

Append to `frontend/src/index.css` (or whichever global CSS file exists):

```css
@media (prefers-reduced-motion: reduce) {
  [style*="sprite-cycle-"] {
    animation: none !important;
    background-position: 0 0 !important;
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/rpg/RpgSprite.jsx frontend/src/components/rpg/RpgSprite.test.jsx frontend/src/index.css
git commit -m "feat: RpgSprite animation branch + reduced-motion CSS"
```

---

### Task 21: Remove the Vite sprite bundle

**Files:**
- Delete: `frontend/src/assets/rpg-sprites/index.js`
- Delete: `frontend/src/assets/rpg-sprites/*.png` (72 files)

- [ ] **Step 1: Confirm no remaining imports of the bundle**

```bash
grep -rn "from .*assets/rpg-sprites" frontend/src || echo "CLEAN"
```

Expected: `CLEAN`. If any file still imports `../../assets/rpg-sprites`, update it to use `useSpriteCatalog` (should already be done — `RpgSprite` was the only consumer).

- [ ] **Step 2: Delete the bundle files**

```bash
rm -r frontend/src/assets/rpg-sprites
```

- [ ] **Step 3: Run the whole frontend test suite to catch regressions**

```bash
cd frontend && npm run test:run
```

Expected: all PASS. If the Vitest coverage exclusion list references the deleted path, remove that entry from `vitest.config.js`.

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/assets
git commit -m "chore: remove Vite sprite bundle (now served via /api/sprites/catalog/)"
```

---

### Task 22: End-to-end prod verification (manual)

**Files:** none — operational.

- [ ] **Step 1: Deploy Phase 2 to prod**

Merge Phase 2 PR, watch CI, verify deploy.

- [ ] **Step 2: Load prod, verify existing sprites render**

Open `https://abby.bos.lol`. Visit the Inventory, Stable, Character, and Quests pages — every page that previously rendered RPG icons should still render them via Ceph URLs. Open devtools Network tab, confirm sprite requests hit `abby-sprites` bucket and return 200 with the expected `Cache-Control` header.

- [ ] **Step 3: Register a test sprite via MCP and confirm it renders**

With an MCP client (Claude Desktop, or a raw curl call), authenticate as parent and call:

```json
{"name": "register_sprite", "arguments": {"params": {
  "slug": "test-smoke-2026-04-20",
  "image_b64": "<base64 of a 32x32 PNG>",
  "pack": "smoketest"
}}}
```

Refresh the page. Open React devtools, find a component that could render this slug (or use browser console: `fetch('/api/sprites/catalog/').then(r=>r.json()).then(d=>console.log(d.sprites['test-smoke-2026-04-20']))`). Confirm the URL resolves to `abby-sprites` and the PNG loads.

- [ ] **Step 4: Register an animated sprite and confirm it animates**

Same as above, with a 128×32 PNG strip + `frame_count: 4, fps: 6`. Render via `<RpgSprite spriteKey="anim-smoke-...">` in a test page or by using an existing page that has emoji-fallback (edit the slug in browser console temporarily).

- [ ] **Step 5: Delete both test sprites via MCP**

```json
{"name": "delete_sprite", "arguments": {"params": {"slug": "test-smoke-2026-04-20"}}}
{"name": "delete_sprite", "arguments": {"params": {"slug": "anim-smoke-..."}}}
```

Confirm `curl https://abby.bos.lol/api/sprites/catalog/` no longer contains either slug.

---

## Phase 3: Cleanup — deferred

**Do not execute in the same PR chain.** Hold for 1 week after Phase 2 is stable in prod. Open a separate PR.

Files to delete:
- `apps/mcp_server/tools/sprite_assets.py`
- `apps/rpg/content/sprites.py` (if no runtime code references it after migrations)
- `scripts/sprite_manifest.yaml`
- `scripts/slice_rpg_sprites.py`
- `scripts/sprite_manifest.yaml.tmp` (if present)
- `reward-icons/` (entire directory)
- `content/rpg/packs/*/sprites/` directories

Update the CLAUDE.md "Atlas hub" / "Drops & inventory" notes to remove references to the deleted bundle path + slicing script.

---

## Notes for the implementer

- **Commits**: One per task (`feat:` or `test:` or `chore:` prefix). Branch name can be `claude/chat-to-prod-sprites` or similar; PR lands on `staging` (or `main` if that's the project convention — check latest PRs).
- **`docker compose` prefix**: all backend test commands assume docker compose is running. Locally you may prefer `python manage.py test` inside an activated venv — equivalent.
- **Legacy migration idempotency**: the data migration is re-runnable. If something goes wrong on Deploy 1, `python manage.py migrate rpg 0011` reverses it (the reverse function deletes `pack="core"` rows + blobs).
- **Ceph costs**: 72 × ~2 KB sprites = ~150 KB storage. Cost is immaterial; don't worry about cleanup on migration retries.
- **Test mocking of `requests`**: Task 6 uses `@patch("apps.rpg.sprite_authoring.requests.get")`. If you choose to use `responses` or `requests-mock` instead, adapt accordingly — they're already in the test dep graph for Anthropic SDK tests.
