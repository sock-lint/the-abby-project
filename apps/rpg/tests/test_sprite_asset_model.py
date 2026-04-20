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
        from django.db import IntegrityError, transaction
        SpriteAsset.objects.create(slug="unique", pack="t", frame_width_px=8, frame_height_px=8)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SpriteAsset.objects.create(
                    slug="unique", pack="t", frame_width_px=8, frame_height_px=8,
                )

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

    def test_frame_count_zero_rejected(self):
        asset = SpriteAsset(slug="bad3", pack="t", frame_width_px=8, frame_height_px=8, frame_count=0)
        with self.assertRaises(ValidationError):
            asset.full_clean()
