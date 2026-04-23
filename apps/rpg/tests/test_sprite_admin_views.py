"""Tests for the parent-only sprite admin REST surface.

Gemini is mocked at ``_generate_frame`` so no real API traffic fires.
"""
import base64
import io
from unittest.mock import patch

from PIL import Image
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.rpg.models import SpriteAsset
from apps.rpg.sprite_authoring import register_sprite


def _png_b64(size=(32, 32)):
    img = Image.new("RGBA", size, (150, 50, 50, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _png_bytes(size=(128, 128), color=(200, 50, 50, 255)):
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class SpriteAdminListTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        register_sprite(slug="alpha", image_b64=_png_b64(), pack="default", actor=self.parent)
        register_sprite(slug="beta", image_b64=_png_b64(), pack="ai-generated", actor=self.parent)
        self.client = APIClient()

    def test_list_requires_auth(self):
        resp = self.client.get(reverse("sprite-admin-list"))
        self.assertIn(resp.status_code, (401, 403))

    def test_list_forbidden_for_child(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get(reverse("sprite-admin-list"))
        self.assertEqual(resp.status_code, 403)

    def test_list_returns_all_for_parent(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(reverse("sprite-admin-list"))
        self.assertEqual(resp.status_code, 200)
        slugs = {row["slug"] for row in resp.json()}
        self.assertEqual(slugs, {"alpha", "beta"})

    def test_list_filter_by_pack(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get(reverse("sprite-admin-list"), {"pack": "ai-generated"})
        self.assertEqual(resp.status_code, 200)
        slugs = [row["slug"] for row in resp.json()]
        self.assertEqual(slugs, ["beta"])

    def test_list_includes_authoring_inputs(self):
        SpriteAsset.objects.filter(slug="alpha").update(
            prompt="red fox", motion="idle", style_hint="gameboy",
            tile_size=64, reference_image_url="",
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get(reverse("sprite-admin-list"))
        row = next(r for r in resp.json() if r["slug"] == "alpha")
        self.assertEqual(row["prompt"], "red fox")
        self.assertEqual(row["motion"], "idle")
        self.assertEqual(row["style_hint"], "gameboy")
        self.assertEqual(row["tile_size"], 64)


@override_settings(GEMINI_API_KEY="test-key")
class SpriteGenerateViewTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()

    def test_generate_forbidden_for_child(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            reverse("sprite-admin-generate"),
            {"slug": "foo", "prompt": "a fox"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_generate_happy_path_persists_inputs(self, mock_frame):
        mock_frame.return_value = _png_bytes(size=(512, 512))
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            reverse("sprite-admin-generate"),
            {
                "slug": "newt",
                "prompt": "pixel-art newt",
                "frame_count": 1,
                "tile_size": 64,
                "fps": 0,
                "pack": "ai-generated",
                "style_hint": "nes palette",
                "motion": "idle",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        asset = SpriteAsset.objects.get(slug="newt")
        self.assertEqual(asset.prompt, "pixel-art newt")
        self.assertEqual(asset.style_hint, "nes palette")
        self.assertEqual(asset.motion, "idle")
        self.assertEqual(asset.tile_size, 64)
        self.assertEqual(asset.created_by, self.parent)

    def test_generate_missing_prompt_returns_400(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            reverse("sprite-admin-generate"),
            {"slug": "newt"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("prompt", resp.json()["detail"])


@override_settings(GEMINI_API_KEY="test-key")
class SpriteRerollViewTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        register_sprite(slug="rocky", image_b64=_png_b64(), actor=self.parent)

    def test_reroll_refuses_when_no_stored_prompt(self):
        resp = self.client.post(reverse("sprite-admin-reroll", kwargs={"slug": "rocky"}))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("no stored prompt", resp.json()["detail"])

    def test_reroll_404_for_unknown_slug(self):
        resp = self.client.post(reverse("sprite-admin-reroll", kwargs={"slug": "ghost"}))
        self.assertEqual(resp.status_code, 404)

    @patch("apps.rpg.sprite_generation._generate_frame")
    def test_reroll_replays_stored_inputs(self, mock_frame):
        mock_frame.return_value = _png_bytes(size=(512, 512))
        SpriteAsset.objects.filter(slug="rocky").update(
            prompt="granite boulder", motion="idle", style_hint="moss",
            tile_size=64, reference_image_url="",
        )

        resp = self.client.post(reverse("sprite-admin-reroll", kwargs={"slug": "rocky"}))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(mock_frame.call_count, 1)
        prompt_arg = mock_frame.call_args.kwargs["prompt"]
        self.assertIn("granite boulder", prompt_arg)
        self.assertIn("moss", prompt_arg)


class SpriteAdminDetailTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        register_sprite(slug="zed", image_b64=_png_b64(), pack="default", actor=self.parent)

    def test_patch_updates_pack(self):
        resp = self.client.patch(
            reverse("sprite-admin-detail", kwargs={"slug": "zed"}),
            {"pack": "custom"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SpriteAsset.objects.get(slug="zed").pack, "custom")

    def test_patch_empty_body_returns_400(self):
        resp = self.client.patch(
            reverse("sprite-admin-detail", kwargs={"slug": "zed"}),
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_delete_removes_row(self):
        resp = self.client.delete(reverse("sprite-admin-detail", kwargs={"slug": "zed"}))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SpriteAsset.objects.filter(slug="zed").exists())

    def test_delete_unknown_slug_returns_400(self):
        resp = self.client.delete(reverse("sprite-admin-detail", kwargs={"slug": "ghost"}))
        self.assertEqual(resp.status_code, 400)
