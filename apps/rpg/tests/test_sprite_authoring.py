import base64
import io
from PIL import Image
from django.test import TestCase
from apps.accounts.models import User
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import register_sprite, SpriteAuthoringError


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
