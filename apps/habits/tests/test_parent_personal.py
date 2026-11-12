from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.habits.models import Habit, HabitLog
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParentPersonalHabitTests(TestCase):
    def setUp(self):
        family = make_family("Personal habits", parents=[{"username": "habit-parent"}], children=[{"username": "habit-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.client.credentials(HTTP_X_ABBY_SPACE="personal")

    def test_parent_creates_published_personal_habit_and_taps_it(self):
        created = self.client.post("/api/habits/", {"name": "Stretch", "habit_type": "positive"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        habit = Habit.objects.get(user=self.parent, name="Stretch")
        self.assertEqual(habit.user, self.parent)
        self.assertFalse(habit.pending_parent_review)
        self.assertEqual(self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json").status_code, 200)
        self.assertEqual(HabitLog.objects.get().user, self.parent)

    def test_personal_habits_do_not_show_or_modify_child_habits(self):
        child_habit = Habit.objects.create(user=self.child, created_by=self.parent, name="Child routine")
        self.assertEqual(self.client.get("/api/habits/").data["results"], [])
        self.assertEqual(self.client.patch(f"/api/habits/{child_habit.pk}/", {"name": "Changed"}).status_code, 404)
        response = self.client.post("/api/habits/", {"name": "Wrong owner", "user": self.child.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Habit.objects.count(), 1)

    def test_parent_family_authority_does_not_turn_child_habit_into_own_progress(self):
        habit = Habit.objects.create(user=self.child, created_by=self.parent, name="Child routine")
        self.client.credentials()
        response = self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json")
        self.assertEqual(response.status_code, 400)
        habit.refresh_from_db()
        self.assertEqual(habit.strength, 0)
        self.assertFalse(HabitLog.objects.exists())
