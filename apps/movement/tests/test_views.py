"""ViewSet integration tests for /api/movement-types/ and /api/movement-sessions/."""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.movement.models import MovementSession, MovementType, MovementTypeSkillTag
from apps.projects.models import User


class _ApiFixture(TestCase):
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
        cat = SkillCategory.objects.create(name="Physical", icon="💪")
        self.endurance = Skill.objects.create(category=cat, name="Endurance", icon="🏃")
        self.run_type = MovementType.objects.create(
            slug="run", name="Run", icon="🏃",
        )
        MovementTypeSkillTag.objects.create(
            movement_type=self.run_type, skill=self.endurance, xp_weight=1,
        )

    def _auth(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
        return client


class MovementTypeRouteTests(_ApiFixture):
    def test_child_can_list_active_types(self):
        client = self._auth(self.child)
        resp = client.get("/api/movement-types/")
        self.assertEqual(resp.status_code, 200)
        names = [t["name"] for t in resp.data["results"]]
        self.assertIn("Run", names)

    def test_inactive_types_are_filtered_out(self):
        MovementType.objects.create(
            slug="archery", name="Archery", icon="🏹", is_active=False,
        )
        client = self._auth(self.child)
        resp = client.get("/api/movement-types/")
        names = [t["name"] for t in resp.data["results"]]
        self.assertNotIn("Archery", names)


class LogSessionRouteTests(_ApiFixture):
    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_logs_session_self_scoped(self, _gl):
        client = self._auth(self.child)
        resp = client.post(
            "/api/movement-sessions/",
            {
                "movement_type_id": self.run_type.id,
                "duration_minutes": 30,
                "intensity": "medium",
                "notes": "felt great",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["user"], self.child.id)
        self.assertEqual(resp.data["movement_type_name"], "Run")
        self.assertEqual(resp.data["duration_minutes"], 30)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_parent_can_log_for_child_via_user_id(self, _gl):
        client = self._auth(self.parent)
        resp = client.post(
            "/api/movement-sessions/",
            {
                "movement_type_id": self.run_type.id,
                "duration_minutes": 20,
                "user_id": self.child.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["user"], self.child.id)

    def test_invalid_movement_type_returns_400(self):
        client = self._auth(self.child)
        resp = client.post(
            "/api/movement-sessions/",
            {"movement_type_id": 9999, "duration_minutes": 30},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_child_cannot_see_other_childs_sessions(self, _gl):
        # other_child logs a session.
        client_other = self._auth(self.other_child)
        client_other.post(
            "/api/movement-sessions/",
            {"movement_type_id": self.run_type.id, "duration_minutes": 30},
            format="json",
        )
        # self.child queries — should see zero sessions.
        client = self._auth(self.child)
        resp = client.get("/api/movement-sessions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 0)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_owner_can_delete_own_session(self, _gl):
        client = self._auth(self.child)
        client.post(
            "/api/movement-sessions/",
            {"movement_type_id": self.run_type.id, "duration_minutes": 30},
            format="json",
        )
        session_id = MovementSession.objects.first().id
        resp = client.delete(f"/api/movement-sessions/{session_id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(MovementSession.objects.count(), 0)

    @patch("apps.rpg.services.GameLoopService.on_task_completed")
    def test_other_child_cannot_delete(self, _gl):
        # child logs a session.
        client = self._auth(self.child)
        client.post(
            "/api/movement-sessions/",
            {"movement_type_id": self.run_type.id, "duration_minutes": 30},
            format="json",
        )
        session_id = MovementSession.objects.first().id
        # other_child tries to delete — should get 403/404 (filtered queryset
        # makes it 404 since they can't even see it).
        client_other = self._auth(self.other_child)
        resp = client_other.delete(f"/api/movement-sessions/{session_id}/")
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(MovementSession.objects.count(), 1)
