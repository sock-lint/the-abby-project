"""Tests for user-authored MovementType creation + deletion.

Pinned invariants:

1. A child can create a type with a primary + optional secondary Physical
   skill, tagged 7/3 (70/30) or solo at weight 1.
2. Non-Physical skills are rejected.
3. Same primary + secondary is rejected.
4. Duplicate name is rejected (case-insensitive).
5. Daily rate limit (5 creates per user per local day) blocks the 6th.
6. Slug collisions auto-suffix with -2, -3, …
7. The creator is always ``request.user`` — even when a parent submits.
8. Seeded types (``created_by=None``) can only be deleted by parents.
9. A type with any referencing session returns 409 on DELETE.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.movement.models import (
    MovementSession,
    MovementType,
    MovementTypeSkillTag,
)
from apps.movement.services import (
    MovementTypeError,
    MovementTypeService,
)
from apps.projects.models import User


class _TypeFixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.other_child = User.objects.create_user(
            username="kid2", password="pw", role="child",
        )
        self.physical = SkillCategory.objects.create(name="Physical", icon="💪")
        self.non_physical = SkillCategory.objects.create(name="Making", icon="🔨")
        body = Subject.objects.create(category=self.physical, name="Body Work", icon="💪")
        sports = Subject.objects.create(category=self.physical, name="Sports", icon="⚽")
        self.endurance = Skill.objects.create(
            category=self.physical, subject=body, name="Endurance", icon="🏃",
        )
        self.strength = Skill.objects.create(
            category=self.physical, subject=body, name="Strength", icon="💪",
        )
        self.flexibility = Skill.objects.create(
            category=self.physical, subject=body, name="Flexibility", icon="🧘",
        )
        self.running = Skill.objects.create(
            category=self.physical, subject=sports, name="Running", icon="🏃",
        )
        self.non_physical_skill = Skill.objects.create(
            category=self.non_physical, name="Soldering", icon="🔌",
        )

    def _auth(self, user):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}",
        )
        return client


class CreateTypeServiceTests(_TypeFixture):
    def test_happy_path_primary_plus_secondary(self):
        mt = MovementTypeService.create_type(
            self.child,
            name="Parkour",
            icon="🧗",
            default_intensity="high",
            primary_skill_id=self.strength.id,
            secondary_skill_id=self.flexibility.id,
        )
        self.assertEqual(mt.name, "Parkour")
        self.assertEqual(mt.icon, "🧗")
        self.assertEqual(mt.default_intensity, "high")
        self.assertEqual(mt.created_by_id, self.child.id)
        self.assertTrue(mt.is_active)

        tags = {t.skill_id: t.xp_weight for t in mt.skill_tags.all()}
        self.assertEqual(tags[self.strength.id], 7)
        self.assertEqual(tags[self.flexibility.id], 3)

    def test_primary_only_uses_weight_one(self):
        mt = MovementTypeService.create_type(
            self.child,
            name="Hiking",
            primary_skill_id=self.endurance.id,
        )
        tags = list(mt.skill_tags.all())
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].skill_id, self.endurance.id)
        self.assertEqual(tags[0].xp_weight, 1)

    def test_non_physical_primary_rejected(self):
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="Soldering Practice",
                primary_skill_id=self.non_physical_skill.id,
            )
        self.assertEqual(MovementType.objects.count(), 0)

    def test_non_physical_secondary_rejected(self):
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="Mixed Training",
                primary_skill_id=self.endurance.id,
                secondary_skill_id=self.non_physical_skill.id,
            )
        self.assertEqual(MovementType.objects.count(), 0)

    def test_primary_equals_secondary_rejected(self):
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="Dup",
                primary_skill_id=self.endurance.id,
                secondary_skill_id=self.endurance.id,
            )

    def test_duplicate_name_rejected_case_insensitive(self):
        MovementType.objects.create(slug="run", name="Run")
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="run",
                primary_skill_id=self.endurance.id,
            )

    def test_empty_name_rejected(self):
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="   ",
                primary_skill_id=self.endurance.id,
            )

    def test_unknown_primary_skill_rejected(self):
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="Mystery",
                primary_skill_id=99999,
            )

    def test_unknown_intensity_rejected(self):
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="Crazy",
                default_intensity="extreme",
                primary_skill_id=self.endurance.id,
            )

    def test_daily_rate_limit(self):
        for i in range(MovementTypeService.DAILY_CREATE_LIMIT):
            MovementTypeService.create_type(
                self.child,
                name=f"Activity {i}",
                primary_skill_id=self.endurance.id,
            )
        with self.assertRaises(MovementTypeError):
            MovementTypeService.create_type(
                self.child,
                name="One more",
                primary_skill_id=self.endurance.id,
            )

    def test_rate_limit_is_per_user(self):
        for i in range(MovementTypeService.DAILY_CREATE_LIMIT):
            MovementTypeService.create_type(
                self.child,
                name=f"Activity {i}",
                primary_skill_id=self.endurance.id,
            )
        # Different user isn't blocked.
        mt = MovementTypeService.create_type(
            self.other_child,
            name="Different",
            primary_skill_id=self.endurance.id,
        )
        self.assertIsNotNone(mt.pk)

    def test_slug_collision_auto_suffixes(self):
        MovementType.objects.create(slug="parkour", name="Existing")
        mt = MovementTypeService.create_type(
            self.child,
            name="Parkour",  # name ok (new), slug would collide.
            primary_skill_id=self.endurance.id,
        )
        # Name uniqueness check happens on name exact match; this one is
        # fine because "Existing" ≠ "Parkour". Slug is auto-suffixed.
        self.assertEqual(mt.slug, "parkour-2")


class CreateTypeRouteTests(_TypeFixture):
    def test_child_creates_type_via_post(self):
        client = self._auth(self.child)
        resp = client.post(
            "/api/movement-types/",
            {
                "name": "Parkour",
                "icon": "🧗",
                "default_intensity": "high",
                "primary_skill_id": self.strength.id,
                "secondary_skill_id": self.flexibility.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["name"], "Parkour")
        self.assertEqual(resp.data["created_by"], self.child.id)
        tag_weights = {t["skill"]: t["xp_weight"] for t in resp.data["skill_tags"]}
        self.assertEqual(tag_weights[self.strength.id], 7)
        self.assertEqual(tag_weights[self.flexibility.id], 3)

    def test_parent_post_records_parent_as_creator(self):
        """Always use request.user — no parent-on-behalf-of-child back door."""
        client = self._auth(self.parent)
        resp = client.post(
            "/api/movement-types/",
            {
                "name": "Pickleball",
                "primary_skill_id": self.endurance.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        mt = MovementType.objects.get(slug="pickleball")
        self.assertEqual(mt.created_by_id, self.parent.id)

    def test_sibling_sees_new_type(self):
        # Child creates.
        client = self._auth(self.child)
        resp = client.post(
            "/api/movement-types/",
            {
                "name": "Skateboarding",
                "primary_skill_id": self.flexibility.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

        # Sibling lists.
        client_other = self._auth(self.other_child)
        resp = client_other.get("/api/movement-types/")
        names = [t["name"] for t in resp.data["results"]]
        self.assertIn("Skateboarding", names)

    def test_non_physical_skill_returns_400(self):
        client = self._auth(self.child)
        resp = client.post(
            "/api/movement-types/",
            {
                "name": "Not a sport",
                "primary_skill_id": self.non_physical_skill.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Physical", resp.data["error"])

    def test_missing_primary_skill_returns_400(self):
        client = self._auth(self.child)
        resp = client.post(
            "/api/movement-types/",
            {"name": "Stuff"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_anonymous_post_rejected(self):
        client = APIClient()
        resp = client.post(
            "/api/movement-types/",
            {
                "name": "Sneaky",
                "primary_skill_id": self.endurance.id,
            },
            format="json",
        )
        self.assertIn(resp.status_code, (401, 403))


class DeleteTypeRouteTests(_TypeFixture):
    def test_creator_can_delete_unused_type(self):
        mt = MovementTypeService.create_type(
            self.child,
            name="Mine",
            primary_skill_id=self.endurance.id,
        )
        client = self._auth(self.child)
        resp = client.delete(f"/api/movement-types/{mt.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(MovementType.objects.filter(pk=mt.pk).exists())

    def test_non_creator_child_forbidden(self):
        mt = MovementTypeService.create_type(
            self.child,
            name="Mine",
            primary_skill_id=self.endurance.id,
        )
        client = self._auth(self.other_child)
        resp = client.delete(f"/api/movement-types/{mt.id}/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(MovementType.objects.filter(pk=mt.pk).exists())

    def test_parent_can_delete_seeded_type(self):
        # Seeded rows have created_by=None.
        seeded = MovementType.objects.create(slug="run", name="Run")
        MovementTypeSkillTag.objects.create(
            movement_type=seeded, skill=self.endurance, xp_weight=1,
        )
        client = self._auth(self.parent)
        resp = client.delete(f"/api/movement-types/{seeded.id}/")
        self.assertEqual(resp.status_code, 204)

    def test_child_cannot_delete_seeded_type(self):
        seeded = MovementType.objects.create(slug="run", name="Run")
        client = self._auth(self.child)
        resp = client.delete(f"/api/movement-types/{seeded.id}/")
        self.assertEqual(resp.status_code, 403)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_delete_used_type_returns_409(self, _gl):
        mt = MovementTypeService.create_type(
            self.child,
            name="Hopping",
            primary_skill_id=self.endurance.id,
        )
        MovementSession.objects.create(
            user=self.child,
            movement_type=mt,
            duration_minutes=30,
            intensity="medium",
            occurred_on=timezone.localdate(),
        )
        client = self._auth(self.child)
        resp = client.delete(f"/api/movement-types/{mt.id}/")
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(MovementType.objects.filter(pk=mt.pk).exists())


class ResponseShapeTests(_TypeFixture):
    def test_list_exposes_created_by(self):
        mt = MovementTypeService.create_type(
            self.child,
            name="Parkour",
            primary_skill_id=self.strength.id,
        )
        client = self._auth(self.child)
        resp = client.get("/api/movement-types/")
        self.assertEqual(resp.status_code, 200)
        row = next(
            r for r in resp.data["results"] if r["id"] == mt.id
        )
        self.assertEqual(row["created_by"], self.child.id)

    def test_seeded_rows_have_null_created_by(self):
        MovementType.objects.create(slug="run", name="Run")
        client = self._auth(self.child)
        resp = client.get("/api/movement-types/")
        row = next(
            r for r in resp.data["results"] if r["name"] == "Run"
        )
        self.assertIsNone(row["created_by"])
