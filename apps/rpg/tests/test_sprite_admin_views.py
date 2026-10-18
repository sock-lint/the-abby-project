"""Tests for prepared sprite administration and retired generation routes."""
import base64
import io

from PIL import Image
from django.test import TestCase
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






class SpriteAdminDetailTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.staff_parent = User.objects.create_user(
            username="sp", password="pw", role="parent", is_staff=True,
        )
        self.client = APIClient()
        register_sprite(slug="zed", image_b64=_png_b64(), pack="default", actor=self.staff_parent)

    def test_patch_forbidden_for_non_staff_parent(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(
            reverse("sprite-admin-detail", kwargs={"slug": "zed"}),
            {"pack": "custom"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(SpriteAsset.objects.get(slug="zed").pack, "default")

    def test_delete_forbidden_for_non_staff_parent(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(reverse("sprite-admin-detail", kwargs={"slug": "zed"}))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(SpriteAsset.objects.filter(slug="zed").exists())

    def test_patch_updates_pack(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.patch(
            reverse("sprite-admin-detail", kwargs={"slug": "zed"}),
            {"pack": "custom"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SpriteAsset.objects.get(slug="zed").pack, "custom")

    def test_patch_empty_body_returns_400(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.patch(
            reverse("sprite-admin-detail", kwargs={"slug": "zed"}),
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_delete_removes_row(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.delete(reverse("sprite-admin-detail", kwargs={"slug": "zed"}))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SpriteAsset.objects.filter(slug="zed").exists())

    def test_delete_unknown_slug_returns_400(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.delete(reverse("sprite-admin-detail", kwargs={"slug": "ghost"}))
        self.assertEqual(resp.status_code, 400)


class RetiredSpriteGenerationTests(TestCase):
    def test_generation_endpoints_cannot_mutate_or_replace_artwork(self):
        parent = User.objects.create_user(username="staff", role="parent", is_staff=True)
        register_sprite(slug="retained", image_b64=_png_b64(), actor=parent)
        asset = SpriteAsset.objects.get(slug="retained")
        old_image = asset.image.name
        SpriteAsset.objects.filter(pk=asset.pk).update(prompt="historical prompt")
        client = APIClient()
        client.force_authenticate(parent)

        generate = client.post("/api/sprites/admin/generate/", {
            "slug": "retained", "prompt": "replacement", "overwrite": True,
        }, format="json")
        reroll = client.post("/api/sprites/admin/retained/reroll/", {}, format="json")

        self.assertEqual(generate.status_code, 410)
        self.assertEqual(reroll.status_code, 410)
        asset.refresh_from_db()
        self.assertEqual(asset.image.name, old_image)
        self.assertEqual(asset.prompt, "historical prompt")
        self.assertTrue(asset.image.storage.exists(old_image))

    def test_retired_generation_still_requires_staff_parent(self):
        client = APIClient()
        unauthenticated = client.post("/api/sprites/admin/generate/", {}, format="json")
        self.assertIn(unauthenticated.status_code, (401, 403))
        parent = User.objects.create_user(username="regular", role="parent")
        child = User.objects.create_user(username="child", role="child")
        for user in (parent, child):
            client.force_authenticate(user)
            for url in ("/api/sprites/admin/generate/", "/api/sprites/admin/retained/reroll/"):
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(client.post(url, {}, format="json").status_code, 403)
