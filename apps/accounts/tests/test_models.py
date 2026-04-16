"""Tests for accounts — User model and CustomUserManager."""
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User


class UserModelTests(TestCase):
    def test_create_user_with_defaults(self):
        user = User.objects.create_user(username="kid", password="pw")
        self.assertEqual(user.role, User.Role.CHILD)
        self.assertEqual(user.hourly_rate, Decimal("8.00"))
        self.assertEqual(user.theme, "summer")

    def test_create_user_with_parent_role(self):
        user = User.objects.create_user(username="dad", password="pw", role="parent")
        self.assertEqual(user.role, "parent")

    def test_display_label_uses_display_name(self):
        user = User.objects.create_user(username="kid", password="pw", display_name="Abby")
        self.assertEqual(user.display_label, "Abby")

    def test_display_label_falls_back_to_username(self):
        user = User.objects.create_user(username="kid", password="pw")
        self.assertEqual(user.display_label, "kid")

    def test_str_uses_display_label(self):
        user = User.objects.create_user(username="kid", password="pw", display_name="Abby")
        self.assertEqual(str(user), "Abby")

    def test_str_without_display_name(self):
        user = User.objects.create_user(username="kid", password="pw")
        self.assertEqual(str(user), "kid")


class CustomUserManagerTests(TestCase):
    def test_create_user_requires_username(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(username="", password="pw")

    def test_create_superuser_sets_staff_and_superuser(self):
        user = User.objects.create_superuser(username="admin", password="pw")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.role, "parent")

    def test_create_user_hashes_password(self):
        user = User.objects.create_user(username="kid", password="secret")
        self.assertTrue(user.check_password("secret"))
        self.assertNotEqual(user.password, "secret")
