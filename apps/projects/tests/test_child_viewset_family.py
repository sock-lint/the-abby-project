"""ChildViewSet must scope to the requesting parent's family.

Family A's parent should never see Family B's children, nor be able to
create / update / read them. Pinned because the implicit pre-multi-family
behavior was "parents see all".
"""
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.tests.factories import make_family


class ChildViewSetFamilyScopingTests(APITestCase):
    def setUp(self):
        self.a = make_family(
            "Family A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "Family B",
            parents=[{"username": "bp"}],
            children=[{"username": "bc"}],
        )
        self.a_token = Token.objects.create(user=self.a.parents[0])
        self.b_token = Token.objects.create(user=self.b.parents[0])

    def _auth_a(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.a_token.key}")

    def _auth_b(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.b_token.key}")

    def test_parent_lists_only_own_family_children(self):
        self._auth_a()
        response = self.client.get("/api/children/")
        self.assertEqual(response.status_code, 200)
        usernames = {c["username"] for c in response.json()["results"]}
        self.assertEqual(usernames, {"ac"})

    def test_parent_cannot_see_other_family_child(self):
        self._auth_a()
        # Parent A asks for Family B's child by id — must 404.
        response = self.client.get(f"/api/children/{self.b.children[0].id}/")
        self.assertEqual(response.status_code, 404)

    def test_parent_cannot_patch_other_family_child(self):
        self._auth_a()
        response = self.client.patch(
            f"/api/children/{self.b.children[0].id}/",
            {"display_name": "hax"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_parent_can_create_child_in_own_family(self):
        self._auth_a()
        response = self.client.post(
            "/api/children/",
            {
                "username": "newkid",
                "password": "ApbBy1!Strong",
                "display_name": "New Kid",
                "hourly_rate": "8.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        # New child landed in Family A.
        from apps.accounts.models import User
        new_child = User.objects.get(username="newkid")
        self.assertEqual(new_child.family_id, self.a.family.id)
        self.assertEqual(new_child.role, "child")
        # Password was hashed.
        self.assertTrue(new_child.check_password("ApbBy1!Strong"))

    def test_create_rejects_duplicate_username(self):
        self._auth_a()
        response = self.client.post(
            "/api/children/",
            {
                "username": "ac",  # already exists in Family A
                "password": "ApbBy1!Strong",
                "display_name": "Dup",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_child_cannot_use_endpoint(self):
        # Auth as Family A's child — IsParent should block.
        token = Token.objects.create(user=self.a.children[0])
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/api/children/")
        self.assertEqual(response.status_code, 403)
