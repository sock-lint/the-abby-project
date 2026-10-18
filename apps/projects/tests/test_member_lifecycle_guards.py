"""Existing member writes must obey the same lifecycle boundary as self-removal."""
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from apps.projects.views import ChildViewSet, ParentViewSet
from config.tests.factories import make_family


class MemberLifecycleGuardTests(APITestCase):
    def setUp(self):
        self.fam = make_family(
            "Lifecycle family", parents=[{"username": "guard_parent"}],
            children=[{"username": "guard_child"}],
        )
        self.parent = self.fam.parents[0]
        self.child = self.fam.children[0]
        self.token = Token.objects.create(user=self.parent)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_patch_cannot_deactivate_self_or_remove_last_active_parent(self):
        response = self.client.patch(
            f"/api/parents/{self.parent.pk}/", {"is_active": False}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.is_active)
        self.assertTrue(Token.objects.filter(pk=self.token.pk).exists())

    def test_patch_deactivation_revokes_target_credential_and_reactivation_does_not_restore_it(self):
        child_token = Token.objects.create(user=self.child)
        response = self.client.patch(
            f"/api/children/{self.child.pk}/", {"is_active": False}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.child.refresh_from_db()
        self.assertFalse(self.child.is_active)
        self.assertFalse(Token.objects.filter(pk=child_token.pk).exists())
        response = self.client.patch(
            f"/api/children/{self.child.pk}/", {"is_active": True}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertTrue(self.child.is_active)
        self.assertFalse(Token.objects.filter(user=self.child).exists())

    def test_password_patch_requires_existing_password_reset_action(self):
        child_token = Token.objects.create(user=self.child)
        response = self.client.patch(
            f"/api/children/{self.child.pk}/", {"password": "ChangedPassword42!"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.child.refresh_from_db()
        self.assertTrue(self.child.check_password("pw"))
        self.assertTrue(Token.objects.filter(pk=child_token.pk).exists())

    def test_revoked_credential_cannot_finish_authenticated_member_writes(self):
        # DRF has already authenticated these requests before logout/reset.
        # Revalidate inside the serialized write transaction as well.
        factory = APIRequestFactory()
        requests = [
            (ChildViewSet, {"post": "create"}, factory.post(
                "/api/children/", {"username": "late_child", "password": "ChangedPassword42!"}, format="json",
            ), {}),
            (ChildViewSet, {"patch": "partial_update"}, factory.patch(
                "/api/children/", {"display_name": "late change"}, format="json",
            ), {"pk": self.child.pk}),
            (ChildViewSet, {"post": "reset_password"}, factory.post(
                "/api/children/", {"password": "ChangedPassword42!"}, format="json",
            ), {"pk": self.child.pk}),
            (ChildViewSet, {"post": "reactivate"}, factory.post("/api/children/"), {"pk": self.child.pk}),
            (ChildViewSet, {"delete": "destroy"}, factory.delete("/api/children/"), {"pk": self.child.pk}),
            (ParentViewSet, {"post": "deactivate"}, factory.post("/api/parents/"), {"pk": self.parent.pk}),
        ]
        stale_key = self.token.key
        Token.objects.filter(pk=stale_key).delete()
        for viewset, actions, request, kwargs in requests:
            with self.subTest(actions=actions):
                force_authenticate(request, user=self.parent, token=Token(key=stale_key, user=self.parent))
                response = viewset.as_view(actions)(request, **kwargs)
                self.assertEqual(response.status_code, 401, response.data)
        self.child.refresh_from_db()
        self.assertNotEqual(self.child.display_name, "late change")
        self.assertTrue(self.child.check_password("pw"))
        self.assertFalse(self.parent.__class__.objects.filter(username="late_child").exists())
