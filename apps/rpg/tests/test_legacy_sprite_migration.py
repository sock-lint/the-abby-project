from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.apps import apps as django_apps
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase
from PIL import Image

from apps.rpg.migrations import _0014_import_legacy_sprites_impl as impl
from apps.rpg.models import SpriteAsset


class LegacySpriteMigrationTests(TestCase):
    """Exercise the real migration with synthetic PNGs and temporary storage."""

    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.legacy_dir = self.root / "legacy_sprites"
        self.legacy_dir.mkdir()
        self.storage = FileSystemStorage(location=self.root / "storage")
        self.enterContext(patch.object(impl, "_legacy_sprite_dir", return_value=self.legacy_dir))
        self.enterContext(patch.object(SpriteAsset._meta.get_field("image"), "storage", self.storage))

        self.sprite_sizes = {"apple": (12, 8), "owl": (7, 9)}
        for slug, size in self.sprite_sizes.items():
            with Image.new("RGBA", size, (255, 0, 0, 255)) as image:
                image.save(self.legacy_dir / f"{slug}.png")
        (self.legacy_dir / "notes.txt").write_text("Not a sprite", encoding="utf-8")

    def _create_sprite(self, slug="custom", pack="user-authored"):
        asset = SpriteAsset(slug=slug, pack=pack, frame_width_px=12, frame_height_px=8)
        asset.image.save(f"{slug}.png", ContentFile((self.legacy_dir / "apple.png").read_bytes()))
        return asset

    def test_forward_imports_each_png(self):
        impl.import_legacy_sprites(django_apps, None)

        self.assertCountEqual(SpriteAsset.objects.values_list("slug", flat=True), self.sprite_sizes)
        for slug, size in self.sprite_sizes.items():
            with self.subTest(slug=slug):
                asset = SpriteAsset.objects.get(slug=slug)
                self.assertEqual(asset.pack, "core")
                self.assertEqual((asset.frame_width_px, asset.frame_height_px), size)
                self.assertEqual(asset.frame_count, 1)
                self.assertEqual(asset.fps, 0)
                self.assertEqual(asset.frame_layout, "horizontal")
                self.assertRegex(asset.image.name, rf"^rpg-sprites/{slug}-[0-9a-f]{{8}}\.png$")
                with asset.image.open("rb") as stored:
                    self.assertEqual(stored.read(), (self.legacy_dir / f"{slug}.png").read_bytes())

    def test_forward_is_idempotent(self):
        impl.import_legacy_sprites(django_apps, None)
        before = list(SpriteAsset.objects.order_by("slug").values())

        impl.import_legacy_sprites(django_apps, None)

        self.assertEqual(list(SpriteAsset.objects.order_by("slug").values()), before)
        self.assertCountEqual(
            self.storage.listdir("rpg-sprites")[1],
            [Path(row["image"]).name for row in before],
        )

    def test_forward_preserves_existing_sprite(self):
        existing = self._create_sprite(slug="apple")
        before = SpriteAsset.objects.filter(pk=existing.pk).values().get()

        impl.import_legacy_sprites(django_apps, None)

        self.assertEqual(SpriteAsset.objects.filter(pk=existing.pk).values().get(), before)
        self.assertEqual(SpriteAsset.objects.get(slug="owl").pack, "core")
        self.assertEqual(SpriteAsset.objects.count(), 2)
        with existing.image.open("rb") as stored:
            self.assertEqual(stored.read(), (self.legacy_dir / "apple.png").read_bytes())

    def test_reverse_removes_core_rows_and_files_only(self):
        authored = self._create_sprite()
        impl.import_legacy_sprites(django_apps, None)
        core_images = list(SpriteAsset.objects.filter(pack="core").values_list("image", flat=True))
        self.assertEqual(len(core_images), 2)
        for name in core_images:
            self.assertTrue(self.storage.exists(name))

        impl.remove_legacy_sprites(django_apps, None)

        self.assertEqual(SpriteAsset.objects.filter(pack="core").count(), 0)
        for name in core_images:
            self.assertFalse(self.storage.exists(name))
        self.assertEqual(list(SpriteAsset.objects.values_list("pk", flat=True)), [authored.pk])
        with authored.image.open("rb") as stored:
            self.assertEqual(stored.read(), (self.legacy_dir / "apple.png").read_bytes())

    def _assert_import_is_noop(self, source_dir):
        existing = self._create_sprite(pack="core")
        before = SpriteAsset.objects.values().get()
        with patch.object(impl, "_legacy_sprite_dir", return_value=source_dir):
            impl.import_legacy_sprites(django_apps, None)

        self.assertEqual(SpriteAsset.objects.values().get(), before)
        with existing.image.open("rb") as stored:
            self.assertEqual(stored.read(), (self.legacy_dir / "apple.png").read_bytes())
        self.assertEqual(self.storage.listdir("rpg-sprites")[1], [Path(existing.image.name).name])

    def test_forward_with_missing_legacy_directory_is_noop(self):
        self._assert_import_is_noop(self.root / "missing")

    def test_forward_with_empty_legacy_directory_is_noop(self):
        empty_dir = self.root / "empty"
        empty_dir.mkdir()
        self._assert_import_is_noop(empty_dir)
