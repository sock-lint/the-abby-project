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
