from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import CharacterProfile


class CharacterProfileTests(TestCase):
    def test_profile_auto_created_on_user_save(self):
        user = User.objects.create_user(username="testchild", password="testpass")
        self.assertTrue(CharacterProfile.objects.filter(user=user).exists())

    def test_profile_defaults(self):
        user = User.objects.create_user(username="testchild2", password="testpass")
        profile = user.character_profile
        self.assertEqual(profile.level, 0)
        self.assertEqual(profile.login_streak, 0)
        self.assertEqual(profile.longest_login_streak, 0)
        self.assertIsNone(profile.last_active_date)
        self.assertEqual(profile.perfect_days_count, 0)

    def test_str(self):
        user = User.objects.create_user(username="abby", password="testpass", display_name="Abby")
        profile = user.character_profile
        self.assertEqual(str(profile), "Abby (Level 0)")

    def test_str_no_display_name(self):
        user = User.objects.create_user(username="kiduser", password="testpass")
        profile = user.character_profile
        self.assertEqual(str(profile), "kiduser (Level 0)")
