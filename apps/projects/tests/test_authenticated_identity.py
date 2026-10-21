"""Current-account capability data never grants or changes server authority."""
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import SkillCategory
from apps.projects.serializers import UserSerializer
from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=['testserver'])
class AuthenticatedIdentityTests(APITestCase):
    def setUp(self):
        family = make_family(
            parents=[{'username': 'staff-parent', 'is_staff': True}, {'username': 'ordinary-parent'}],
            children=[{'username': 'child'}],
        )
        self.staff, self.parent = family.parents
        self.child = family.children[0]
        self.category = SkillCategory.objects.create(name='Identity review practice')

    def sign_in(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=user).key}')

    def test_me_patch_cannot_remove_staff_authority(self):
        self.sign_in(self.staff)
        self.assertIs(self.client.get('/api/auth/me/').json()['is_staff'], True)
        response = self.client.patch('/api/auth/me/', {'is_staff': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()['is_staff'], True)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_staff)
        self.assertEqual(self.client.patch(
            f'/api/categories/{self.category.pk}/', {'is_retired': True}, format='json',
        ).status_code, 200)

    def test_me_patch_cannot_grant_staff_to_parent_or_child(self):
        for user in (self.parent, self.child):
            with self.subTest(role=user.role):
                self.sign_in(user)
                response = self.client.patch('/api/auth/me/', {'is_staff': True}, format='json')
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json()['is_staff'], False)
                user.refresh_from_db()
                self.assertFalse(user.is_staff)
                self.assertEqual(self.client.patch(
                    f'/api/categories/{self.category.pk}/', {'is_retired': True}, format='json',
                ).status_code, 403)

    def test_nested_user_response_keeps_its_existing_shape(self):
        self.assertNotIn('is_staff', UserSerializer(self.staff).data)
