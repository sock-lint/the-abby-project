import base64
import io
from unittest.mock import patch
from tempfile import TemporaryDirectory

import requests
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage, InMemoryStorage
from django.db import IntegrityError
from django.test import TestCase
from apps.accounts.models import User
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import (
    register_sprite,
    register_sprite_batch,
    delete_sprite,
    get_catalog,
    SpriteAuthoringError,
)


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
        self.assertTrue(row.image.name, "image blob must be saved (image.name should be non-empty)")
        self.assertIn("dragon-", row.image.name)


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
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="x", actor=self.parent)
        self.assertIn("exactly one", str(ctx.exception))

    def test_rejects_malformed_base64(self):
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="x", image_b64="not-base64!!!", actor=self.parent)
        self.assertIn("base64", str(ctx.exception))

    def test_rejects_non_png_bytes(self):
        garbage_b64 = base64.b64encode(b"hello world not a png").decode()
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="x", image_b64=garbage_b64, actor=self.parent)
        self.assertIn("not a valid PNG", str(ctx.exception))

    def test_rejects_unsupported_image_format(self):
        import io as _io
        from PIL import Image as _Image
        # Build a valid JPEG (Pillow can open it, but our allow-list rejects it)
        img = _Image.new("RGB", (32, 32), (255, 0, 0))
        buf = _io.BytesIO()
        img.save(buf, format="JPEG")
        jpeg_b64 = base64.b64encode(buf.getvalue()).decode()

        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="x", image_b64=jpeg_b64, actor=self.parent)
        self.assertIn("not supported", str(ctx.exception))
        self.assertIn("PNG", str(ctx.exception))

    def test_rejects_animated_strip_width_mismatch(self):
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
        b64 = base64.b64encode(_png_bytes()).decode()
        register_sprite(slug="taken", image_b64=b64, actor=self.parent)
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="taken", image_b64=b64, actor=self.parent)
        self.assertIn("already exists", str(ctx.exception))

    def test_slug_collision_with_overwrite_succeeds(self):
        b64_a = base64.b64encode(_png_bytes((16, 16))).decode()
        b64_b = base64.b64encode(_png_bytes((32, 32))).decode()
        register_sprite(slug="replaceable", image_b64=b64_a, actor=self.parent)
        result = register_sprite(
            slug="replaceable", image_b64=b64_b, overwrite=True,
            actor=self.parent,
        )
        self.assertEqual(result["frame_width_px"], 32)
        self.assertEqual(SpriteAsset.objects.filter(slug="replaceable").count(), 1)

    def test_rejects_animated_strip_height_mismatch_vertical(self):
        # 16×30 image with frame_count=4, layout=vertical → 30/4 not integer
        png = _png_bytes((16, 30))
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(
                slug="x", image_b64=base64.b64encode(png).decode(),
                frame_count=4, fps=6, frame_layout="vertical",
                actor=self.parent,
            )
        self.assertIn("divisible", str(ctx.exception))


class SpriteReplacementSafetyTests(TestCase):
    def setUp(self):
        self.enterContext(patch.object(SpriteAsset._meta.get_field("image"), "storage", InMemoryStorage()))
        register_sprite(slug="retained", image_b64=base64.b64encode(_png_bytes()).decode())
        self.asset = SpriteAsset.objects.get(slug="retained")
        self.old_name = self.asset.image.name
        self.storage = self.asset.image.storage
        self.old_bytes = self.storage.open(self.old_name).read()
        self.replacement = base64.b64encode(_png_bytes(color=(0, 255, 0, 255))).decode()

    def assert_original_preserved(self):
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.image.name, self.old_name)
        self.assertTrue(self.storage.exists(self.old_name))
        self.assertEqual(self.storage.open(self.old_name).read(), self.old_bytes)

    def test_invalid_replacement_keeps_saved_image(self):
        with self.assertRaises((SpriteAuthoringError, ValidationError)):
            register_sprite(slug="retained", image_b64=self.replacement, fps=8, overwrite=True)
        self.assert_original_preserved()

    def test_failed_upload_keeps_saved_image(self):
        with patch.object(self.storage, "save", side_effect=OSError("storage unavailable")):
            with self.assertRaises(OSError):
                register_sprite(slug="retained", image_b64=self.replacement, overwrite=True)
        self.assert_original_preserved()

    def test_failed_database_save_keeps_saved_image_and_removes_new_upload(self):
        original_save = self.storage.save
        uploaded_names = []

        def upload(*args, **kwargs):
            name = original_save(*args, **kwargs)
            uploaded_names.append(name)
            return name

        with patch.object(self.storage, "save", side_effect=upload):
            with patch.object(SpriteAsset, "save", side_effect=OSError("database unavailable")):
                with self.assertRaises(OSError):
                    register_sprite(slug="retained", image_b64=self.replacement, overwrite=True)
        self.assert_original_preserved()
        self.assertEqual(len(uploaded_names), 1)
        self.assertFalse(self.storage.exists(uploaded_names[0]))

    def test_successful_replacement_deletes_previous_blob_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            result = register_sprite(slug="retained", image_b64=self.replacement, overwrite=True)
            self.assertTrue(self.storage.exists(self.old_name))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.image.url, result["url"])
        self.assertTrue(self.storage.exists(self.asset.image.name))
        self.assertFalse(self.storage.exists(self.old_name))

    def test_losing_first_creation_cannot_delete_concurrent_winners_image(self):
        # Both creators passed their lookup/uniqueness check before the
        # winner committed. S3-style storage overwrites matching keys; the
        # losing insert hits the real database's unique constraint.
        with TemporaryDirectory() as media_root:
            storage = FileSystemStorage(location=media_root, allow_overwrite=True)
            with patch.object(SpriteAsset._meta.get_field("image"), "storage", storage):
                image_b64 = base64.b64encode(_png_bytes()).decode()
                register_sprite(slug="concurrent-create", image_b64=image_b64)
                winner = SpriteAsset.objects.get(slug="concurrent-create")
                winner_name = winner.image.name
                winner_bytes = storage.open(winner_name).read()
                with patch.object(SpriteAsset.objects, "select_for_update") as lookup:
                    lookup.return_value.filter.return_value.first.return_value = None
                    with patch.object(SpriteAsset, "validate_unique", return_value=None):
                        with self.assertRaises(IntegrityError):
                            register_sprite(slug="concurrent-create", image_b64=image_b64)
                winner.refresh_from_db()
                self.assertEqual(winner.image.name, winner_name)
                self.assertTrue(storage.exists(winner_name))
                self.assertEqual(storage.open(winner_name).read(), winner_bytes)


class RegisterSpriteAnimatedTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p2", password="pw", role="parent")

    def test_horizontal_strip_4_frames(self):
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
        self.assertEqual(result["frame_layout"], "horizontal")
        row = SpriteAsset.objects.get(slug="flame")
        self.assertEqual(row.frame_count, 4)
        self.assertEqual(row.fps, 6)
        self.assertEqual(row.frame_width_px, 32)
        self.assertEqual(row.frame_layout, "horizontal")

    def test_vertical_strip_3_frames(self):
        png = _png_bytes((16, 48))  # 3 frames of 16x16
        result = register_sprite(
            slug="coin", image_b64=base64.b64encode(png).decode(),
            frame_count=3, fps=8, frame_layout="vertical",
            actor=self.parent,
        )
        self.assertEqual(result["frame_count"], 3)
        self.assertEqual(result["fps"], 8)
        self.assertEqual(result["frame_width_px"], 16)
        self.assertEqual(result["frame_height_px"], 16)
        self.assertEqual(result["frame_layout"], "vertical")
        row = SpriteAsset.objects.get(slug="coin")
        self.assertEqual(row.frame_count, 3)
        self.assertEqual(row.fps, 8)
        self.assertEqual(row.frame_height_px, 16)
        self.assertEqual(row.frame_layout, "vertical")


class RegisterSpriteFromUrlTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p3", password="pw", role="parent")

    @patch("apps.rpg.sprite_authoring.safe_get")
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

    @patch("apps.rpg.sprite_authoring.safe_get")
    def test_rejects_non_image_mime(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<html>"
        mock_get.return_value.headers = {"Content-Type": "text/html"}
        mock_get.return_value.raise_for_status = lambda: None
        with self.assertRaises(SpriteAuthoringError) as ctx:
            register_sprite(slug="x", image_url="http://e/x", actor=self.parent)
        self.assertIn("Content-Type", str(ctx.exception))

    @patch("apps.rpg.sprite_authoring.safe_get")
    def test_rejects_http_error(self, mock_get):
        mock_get.return_value.status_code = 404
        mock_get.return_value.raise_for_status = (
            lambda: (_ for _ in ()).throw(requests.HTTPError("404"))
        )
        with self.assertRaises(SpriteAuthoringError):
            register_sprite(slug="x", image_url="http://e/missing", actor=self.parent)


class RegisterSpriteBatchTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p4", password="pw", role="parent")

    def test_slices_sheet_into_multiple_tiles(self):
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


class RegisterSpriteBatchPartialFailureTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p5", password="pw", role="parent")

    def test_out_of_bounds_tile_skipped_others_registered(self):
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

    def test_missing_required_tile_keys_reported_in_skipped(self):
        sheet = _png_bytes((64, 32))
        result = register_sprite_batch(
            sheet_b64=base64.b64encode(sheet).decode(),
            tile_size=32,
            tiles=[
                {"slug": "ok", "col": 0, "row": 0},
                {"col": 1, "row": 0},  # missing slug
                {"slug": "no-col", "row": 0},  # missing col
            ],
            actor=self.parent,
        )
        self.assertEqual(len(result["registered"]), 1)
        self.assertEqual(len(result["skipped"]), 2)
        # The missing-slug one reports "<unknown>"; the other reports its slug
        slugs_reported = {s["slug"] for s in result["skipped"]}
        self.assertIn("<unknown>", slugs_reported)
        self.assertIn("no-col", slugs_reported)
        for s in result["skipped"]:
            self.assertIn("missing required keys", s["reason"])

    def test_nonpositive_tile_size_raises(self):
        sheet = _png_bytes((64, 32))
        for bad in (0, -1):
            with self.assertRaises(SpriteAuthoringError) as ctx:
                register_sprite_batch(
                    sheet_b64=base64.b64encode(sheet).decode(),
                    tile_size=bad,
                    tiles=[{"slug": "x", "col": 0, "row": 0}],
                    actor=self.parent,
                )
            self.assertIn("tile_size", str(ctx.exception))


class DeleteSpriteTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p6", password="pw", role="parent")

    def test_delete_removes_row_and_blob(self):
        b64 = base64.b64encode(_png_bytes()).decode()
        register_sprite(slug="gone", image_b64=b64, actor=self.parent)
        self.assertEqual(SpriteAsset.objects.filter(slug="gone").count(), 1)

        delete_sprite(slug="gone")

        self.assertEqual(SpriteAsset.objects.filter(slug="gone").count(), 0)

    def test_delete_unknown_slug_raises(self):
        with self.assertRaises(SpriteAuthoringError) as ctx:
            delete_sprite(slug="never-existed")
        self.assertIn("not found", str(ctx.exception))

    def test_delete_calls_blob_before_row(self):
        b64 = base64.b64encode(_png_bytes()).decode()
        register_sprite(slug="order", image_b64=b64, actor=self.parent)
        asset = SpriteAsset.objects.get(slug="order")

        call_order: list[str] = []
        orig_blob_delete = asset.image.delete
        orig_row_delete = asset.delete

        def record_blob(*a, **kw):
            call_order.append("blob")
            return orig_blob_delete(*a, **kw)

        def record_row(*a, **kw):
            call_order.append("row")
            return orig_row_delete(*a, **kw)

        with patch.object(SpriteAsset.objects, "get", return_value=asset):
            with patch.object(asset.image, "delete", side_effect=record_blob):
                with patch.object(asset, "delete", side_effect=record_row):
                    delete_sprite(slug="order")

        self.assertEqual(call_order, ["blob", "row"])


class GetCatalogTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p7", password="pw", role="parent")
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
