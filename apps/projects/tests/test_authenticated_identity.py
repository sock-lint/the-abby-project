"""Current-account capability data never grants or changes server authority."""
from django.test import override_settings
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import SkillCategory
from apps.families.models import LiveTestFamily
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
        self.assertNotIn('usage_collection_enabled', UserSerializer(self.staff).data)


@override_settings(
    ALLOWED_HOSTS=['testserver'], ALLOW_PARENT_SIGNUP=True,
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class UsageCollectionIdentityTests(APITestCase):
    def setUp(self):
        cache.clear()
        household = make_family(
            'Synthetic observer capability household',
            parents=[{'username': 'capability-staff', 'is_staff': True}, {'username': 'capability-parent'}],
            children=[{'username': 'capability-child'}],
        )
        self.family = household.family
        self.staff, self.parent = household.parents
        self.child = household.children[0]

    def sign_in(self, actor):
        token, _ = Token.objects.get_or_create(user=actor)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def register_observer_receipt(self):
        LiveTestFamily.objects.create(
            namespace='synthetic-observer-ownership', family=self.family,
            parent=self.staff, child=self.child,
        )

    def test_ordinary_accounts_are_enabled_and_profile_patch_cannot_disable_collection(self):
        for actor in (self.staff, self.parent, self.child):
            with self.subTest(role=actor.role, staff=actor.is_staff):
                self.sign_in(actor)
                self.assertIs(self.client.get('/api/auth/me/').json()['usage_collection_enabled'], True)
                response = self.client.patch('/api/auth/me/', {'usage_collection_enabled': False}, format='json')
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json()['usage_collection_enabled'], True)

    def test_receipt_backed_household_disables_login_and_me_collection_for_every_member(self):
        self.register_observer_receipt()
        for actor in (self.staff, self.parent, self.child):
            with self.subTest(role=actor.role, staff=actor.is_staff):
                self.client.credentials()
                response = self.client.post('/api/auth/', {
                    'action': 'login', 'username': actor.username, 'password': 'pw',
                    'usage_collection_enabled': True,
                }, format='json')
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json()['usage_collection_enabled'], False)
                self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.json()['token']}")
                self.assertIs(self.client.get('/api/auth/me/').json()['usage_collection_enabled'], False)
                response = self.client.patch('/api/auth/me/', {'usage_collection_enabled': True}, format='json')
                self.assertIs(response.json()['usage_collection_enabled'], False)
                self.assertNotIn('synthetic-observer-ownership', str(response.json()))

    def test_similar_usernames_and_family_slug_cannot_exempt_an_ordinary_household(self):
        self.family.slug = 'abby-live-checks'
        self.family.save(update_fields=['slug'])
        self.parent.username = 'abby_loop_parent'
        self.parent.save(update_fields=['username'])
        self.child.username = 'abby_loop_child'
        self.child.save(update_fields=['username'])
        for actor in (self.parent, self.child):
            with self.subTest(role=actor.role):
                self.sign_in(actor)
                self.assertIs(self.client.get('/api/auth/me/').json()['usage_collection_enabled'], True)

    def test_existing_token_receives_updated_receipt_backed_capability(self):
        self.sign_in(self.child)
        self.assertIs(self.client.get('/api/auth/me/').json()['usage_collection_enabled'], True)
        self.register_observer_receipt()
        self.assertIs(self.client.get('/api/auth/me/').json()['usage_collection_enabled'], False)

    def test_signup_cannot_claim_observer_exemption(self):
        response = self.client.post('/api/auth/signup/', {
            'username': 'ordinary-signup-capability', 'password': 'Synthetic-new-family-password-71!',
            'family_name': 'New synthetic capability family', 'usage_collection_enabled': False,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.json()['user']['usage_collection_enabled'], True)
