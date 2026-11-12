from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.movement.models import MovementSession, MovementType
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParentPersonalMovementTests(TestCase):
    def setUp(self):
        family = make_family("Personal movement", parents=[{"username": "movement-parent"}], children=[{"username": "movement-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.movement_type = MovementType.objects.create(name="Walk", slug="walk")
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.client.credentials(HTTP_X_ABBY_SPACE="personal")

    def test_parent_logs_own_movement_and_sees_only_personal_history(self):
        child = MovementSession.objects.create(user=self.child, movement_type=self.movement_type, duration_minutes=10, occurred_on=timezone.localdate())
        result = self.client.post("/api/movement-sessions/", {"movement_type_id": self.movement_type.pk, "duration_minutes": 20}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["user"], self.parent.pk)
        self.assertEqual([row["id"] for row in self.client.get("/api/movement-sessions/").data["results"]], [result.data["id"]])
        self.assertEqual(self.client.delete(f"/api/movement-sessions/{child.pk}/").status_code, 404)

    def test_personal_log_rejects_child_target(self):
        result = self.client.post("/api/movement-sessions/", {"movement_type_id": self.movement_type.pk, "duration_minutes": 20, "user_id": self.child.pk}, format="json")
        self.assertIn(result.status_code, (400, 404))
        self.assertFalse(MovementSession.objects.exists())
