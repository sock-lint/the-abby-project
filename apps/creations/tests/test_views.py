"""HTTP-layer tests for apps.creations.views.

Exercises auth/permission boundaries + multipart upload + the three parent
actions (submit/approve/reject) over the DRF test client.
"""
from __future__ import annotations

import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.creations.models import Creation
from apps.projects.models import User


def _fake_image(name: str = "art.jpg") -> SimpleUploadedFile:
    """Real 4×4 JPEG — DRF's ``ImageField`` runs ``PIL.Image.verify()``,
    so the stub bytes pattern used elsewhere isn't enough at the view layer.
    """
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def _unwrap(data):
    """Tolerate pagination — return a flat list whether or not DRF pages."""
    if isinstance(data, list):
        return data
    return data.get("results", data)


class _Fixture(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.other_child = User.objects.create_user(
            username="c2", password="pw", role="child",
        )
        self.art_cat = SkillCategory.objects.create(name="Art & Crafts", icon="🎨")
        self.draw = Skill.objects.create(
            category=self.art_cat, name="Drawing", icon="✏️",
        )


class CreationCreateTests(_Fixture):
    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_creates_own_creation(self, _gl):
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            "/api/creations/",
            {
                "image": _fake_image(),
                "caption": "my cat",
                "primary_skill_id": self.draw.id,
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["user"], self.child.id)
        self.assertEqual(resp.data["caption"], "my cat")
        self.assertEqual(resp.data["xp_awarded"], 10)
        self.assertEqual(resp.data["primary_skill_name"], "Drawing")

    def test_non_creative_skill_rejected_with_400(self):
        math_cat = SkillCategory.objects.create(name="Math", icon="🔢")
        algebra = Skill.objects.create(category=math_cat, name="Algebra", icon="✖️")
        self.client.force_authenticate(self.child)
        resp = self.client.post(
            "/api/creations/",
            {"image": _fake_image(), "primary_skill_id": algebra.id},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Creation.objects.count(), 0)

    def test_unauthenticated_rejected(self):
        resp = self.client.post(
            "/api/creations/",
            {"image": _fake_image(), "primary_skill_id": self.draw.id},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 401)


class CreationDeleteTests(_Fixture):
    def _make(self, user=None):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            return CreationService.log_creation(
                user or self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )

    def test_owner_can_delete(self):
        c = self._make()
        self.client.force_authenticate(self.child)
        resp = self.client.delete(f"/api/creations/{c.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Creation.objects.filter(id=c.id).exists())

    def test_parent_can_delete_any(self):
        c = self._make()
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/creations/{c.id}/")
        self.assertEqual(resp.status_code, 204)

    def test_other_child_cannot_delete(self):
        c = self._make()
        self.client.force_authenticate(self.other_child)
        # Child-scoped queryset hides this creation → 404, not 403.
        resp = self.client.delete(f"/api/creations/{c.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Creation.objects.filter(id=c.id).exists())


class CreationSubmitTests(_Fixture):
    def _make(self):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            return CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )

    def test_owner_can_submit(self):
        c = self._make()
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/creations/{c.id}/submit/")
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.status, Creation.Status.PENDING)

    def test_other_child_cannot_submit(self):
        c = self._make()
        self.client.force_authenticate(self.other_child)
        resp = self.client.post(f"/api/creations/{c.id}/submit/")
        self.assertEqual(resp.status_code, 404)

    def test_parent_can_submit_on_childs_behalf(self):
        c = self._make()
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/creations/{c.id}/submit/")
        self.assertEqual(resp.status_code, 200)


class CreationApproveRejectTests(_Fixture):
    def _make_pending(self):
        from apps.creations.services import CreationService

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            c = CreationService.log_creation(
                self.child, image=_fake_image(),
                primary_skill_id=self.draw.id,
            )
        CreationService.submit_for_bonus(c)
        return c

    def test_parent_approves_with_default_bonus(self):
        c = self._make_pending()
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/creations/{c.id}/approve/", {}, format="json")
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.status, Creation.Status.APPROVED)
        self.assertEqual(c.bonus_xp_awarded, 15)

    def test_parent_approves_with_custom_bonus_and_tags(self):
        c = self._make_pending()
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/creations/{c.id}/approve/",
            {
                "bonus_xp": 25,
                "skill_tags": [{"skill_id": self.draw.id, "xp_weight": 1}],
                "notes": "lovely",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.bonus_xp_awarded, 25)
        self.assertEqual(c.bonus_skill_tags.count(), 1)

    def test_child_cannot_approve(self):
        c = self._make_pending()
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/creations/{c.id}/approve/", {}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_parent_rejects(self):
        c = self._make_pending()
        self.client.force_authenticate(self.parent)
        resp = self.client.post(
            f"/api/creations/{c.id}/reject/",
            {"notes": "not this time"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.status, Creation.Status.REJECTED)

    def test_pending_queue_lists_submitted(self):
        self._make_pending()
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/creations/pending/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(_unwrap(resp.data)), 1)


class PendingQueueFamilyScopingTests(TestCase):
    """Audit C3: ``CreationViewSet.pending`` must be scoped to the parent's
    family. Without ``user__family=request.user.family`` a parent in family A
    sees pending creations from every other family in the deployment.
    """

    def setUp(self):
        from config.tests.factories import make_family

        self.fam_a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.fam_b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        self.art_cat = SkillCategory.objects.create(name="Art & Crafts", icon="🎨")
        self.draw = Skill.objects.create(category=self.art_cat, name="Drawing")
        self.client = APIClient()

    def _submit(self, child):
        from apps.creations.services import CreationService
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            c = CreationService.log_creation(
                child, image=_fake_image(), primary_skill_id=self.draw.id,
            )
        CreationService.submit_for_bonus(c)
        return c

    def test_pending_queue_excludes_other_families(self):
        own = self._submit(self.fam_a.children[0])
        self._submit(self.fam_b.children[0])

        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.get("/api/creations/pending/")
        self.assertEqual(resp.status_code, 200)
        rows = _unwrap(resp.data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], own.id)


class CreationListTests(_Fixture):
    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_parent_sees_all_children_creations(self, _gl):
        from apps.creations.services import CreationService

        CreationService.log_creation(
            self.child, image=_fake_image(),
            primary_skill_id=self.draw.id,
        )
        CreationService.log_creation(
            self.other_child, image=_fake_image(),
            primary_skill_id=self.draw.id,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/creations/")
        self.assertEqual(resp.status_code, 200)
        rows = _unwrap(resp.data)
        self.assertEqual(len(rows), 2)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_sees_only_own_creations(self, _gl):
        from apps.creations.services import CreationService

        CreationService.log_creation(
            self.child, image=_fake_image(),
            primary_skill_id=self.draw.id,
        )
        CreationService.log_creation(
            self.other_child, image=_fake_image(),
            primary_skill_id=self.draw.id,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/creations/")
        self.assertEqual(resp.status_code, 200)
        rows = _unwrap(resp.data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user"], self.child.id)
