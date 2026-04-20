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
