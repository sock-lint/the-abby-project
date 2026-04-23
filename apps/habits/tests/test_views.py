"""Tests for HabitViewSet — CRUD, log action, permissions."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.rpg.models import CharacterProfile


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        # Ensure CharacterProfile exists (normally created by signal).
        CharacterProfile.objects.get_or_create(user=self.child)
        self.client = APIClient()


class HabitCRUDTests(_Fixture):
    def test_child_creates_habit_as_pending_proposal(self):
        """Children can create habits, but they land as pending proposals."""
        from apps.habits.models import Habit

        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/habits/", {
            "name": "Drink water",
            "icon": "💧",
            "habit_type": "positive",
            "user": self.child.id,
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        habit = Habit.objects.get(name="Drink water")
        self.assertTrue(habit.pending_parent_review)
        self.assertEqual(habit.user, self.child)
        self.assertEqual(habit.created_by, self.child)

    def test_parent_creates_habit_for_child(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/habits/", {
            "name": "Read",
            "icon": "📖",
            "habit_type": "positive",
            "user": self.child.id,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))

    def test_child_cannot_delete(self):
        from apps.habits.models import Habit
        habit = Habit.objects.create(
            name="Test", habit_type="positive",
            user=self.child, created_by=self.child,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.delete(f"/api/habits/{habit.pk}/")
        self.assertEqual(resp.status_code, 403)

    def test_create_habit_with_skill_tags(self):
        """Parent can POST skill_tags inline and the ViewSet applies them."""
        from apps.achievements.models import Skill, SkillCategory
        from apps.habits.models import Habit, HabitSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat)
        s2 = Skill.objects.create(name="Communication", category=cat)

        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/habits/", {
            "name": "Read 20 min",
            "icon": "📖",
            "habit_type": "positive",
            "user": self.child.id,
            "xp_reward": 10,
            "skill_tags": [
                {"skill_id": s1.id, "xp_weight": 2},
                {"skill_id": s2.id, "xp_weight": 1},
            ],
        }, format="json")
        self.assertIn(resp.status_code, (200, 201), msg=resp.content)
        habit = Habit.objects.get(name="Read 20 min")
        self.assertEqual(HabitSkillTag.objects.filter(habit=habit).count(), 2)

    def test_update_habit_replaces_skill_tags(self):
        from apps.achievements.models import Skill, SkillCategory
        from apps.habits.models import Habit, HabitSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat)
        s2 = Skill.objects.create(name="Communication", category=cat)
        habit = Habit.objects.create(
            name="Read", habit_type="positive",
            user=self.child, created_by=self.parent, xp_reward=10,
        )
        HabitSkillTag.objects.create(habit=habit, skill=s1, xp_weight=1)

        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/habits/{habit.pk}/", {
            "skill_tags": [{"skill_id": s2.id, "xp_weight": 4}],
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        tags = list(HabitSkillTag.objects.filter(habit=habit))
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].skill_id, s2.id)
        self.assertEqual(tags[0].xp_weight, 4)

    def test_update_habit_without_skill_tags_leaves_them_alone(self):
        """Omitting skill_tags on PATCH must not wipe them."""
        from apps.achievements.models import Skill, SkillCategory
        from apps.habits.models import Habit, HabitSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat)
        habit = Habit.objects.create(
            name="Read", habit_type="positive",
            user=self.child, created_by=self.parent, xp_reward=10,
        )
        HabitSkillTag.objects.create(habit=habit, skill=s1, xp_weight=2)

        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/habits/{habit.pk}/", {
            "name": "Read 20 min",
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(
            HabitSkillTag.objects.filter(habit=habit).count(), 1,
            "PATCH without skill_tags should leave tags untouched",
        )

    def test_child_sees_own_habits(self):
        # Parent creates a live habit for the child (not a pending proposal),
        # so the child's default list shows it.
        self.client.force_authenticate(self.parent)
        self.client.post("/api/habits/", {
            "name": "Mine", "habit_type": "positive",
            "user": self.child.id,
        }, format="json")
        # Create habit for another child.
        child2 = User.objects.create_user(username="c2", password="pw", role="child")
        CharacterProfile.objects.get_or_create(user=child2)
        self.client.post("/api/habits/", {
            "name": "Theirs", "habit_type": "positive", "user": child2.id,
        }, format="json")

        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/habits/")
        self.assertEqual(resp.status_code, 200)
        names = [h["name"] for h in resp.json()["results"]]
        self.assertIn("Mine", names)
        self.assertNotIn("Theirs", names)


class HabitProposalTests(_Fixture):
    def test_child_create_strips_xp_reward(self):
        from apps.habits.models import Habit

        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/habits/", {
            "name": "Sneaky",
            "habit_type": "positive",
            "user": self.child.id,
            "xp_reward": 9999,
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        habit = Habit.objects.get(name="Sneaky")
        # xp_reward default is 5 (model default), not the 9999 posted.
        self.assertEqual(habit.xp_reward, 5)

    def test_child_create_strips_skill_tags(self):
        from apps.achievements.models import Skill, SkillCategory
        from apps.habits.models import Habit, HabitSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        skill = Skill.objects.create(name="Persistence", category=cat)
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/habits/", {
            "name": "Tagged",
            "habit_type": "positive",
            "user": self.child.id,
            "skill_tags": [{"skill_id": skill.id, "xp_weight": 5}],
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        habit = Habit.objects.get(name="Tagged")
        self.assertEqual(HabitSkillTag.objects.filter(habit=habit).count(), 0)

    def test_pending_proposal_hidden_from_child_default_list(self):
        from apps.habits.models import Habit

        Habit.objects.create(
            name="Pending", habit_type="positive",
            user=self.child, created_by=self.child,
            pending_parent_review=True,
        )
        Habit.objects.create(
            name="Live", habit_type="positive",
            user=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/habits/")
        self.assertEqual(resp.status_code, 200)
        names = [h["name"] for h in resp.json()["results"]]
        self.assertIn("Live", names)
        self.assertNotIn("Pending", names)

    def test_child_lists_own_pending_with_query(self):
        from apps.habits.models import Habit

        Habit.objects.create(
            name="Mine", habit_type="positive",
            user=self.child, created_by=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/habits/?pending=true")
        self.assertEqual(resp.status_code, 200)
        names = [h["name"] for h in resp.json()["results"]]
        self.assertEqual(names, ["Mine"])

    def test_log_tap_refuses_pending_habit_via_view(self):
        """Child's queryset hides pending habits → 404 via /log/ route."""
        from apps.habits.models import Habit

        habit = Habit.objects.create(
            name="Pending", habit_type="positive",
            user=self.child, created_by=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/habits/{habit.pk}/log/", {
            "direction": 1,
        }, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_log_tap_service_refuses_pending_habit(self):
        """Belt-and-suspenders — even a direct service call fails."""
        from apps.habits.models import Habit
        from apps.habits.services import HabitService

        habit = Habit.objects.create(
            name="Pending", habit_type="positive",
            user=self.child, created_by=self.child,
            pending_parent_review=True,
        )
        with self.assertRaises(ValueError):
            HabitService.log_tap(self.child, habit, 1)

    def test_parent_approves_habit_proposal(self):
        from apps.achievements.models import Skill, SkillCategory
        from apps.habits.models import Habit, HabitSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        skill = Skill.objects.create(name="Persistence", category=cat)
        habit = Habit.objects.create(
            name="Tidy room", habit_type="positive",
            user=self.child, created_by=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/habits/{habit.pk}/approve/", {
            "xp_reward": 12,
            "skill_tags": [{"skill_id": skill.id, "xp_weight": 1}],
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        habit.refresh_from_db()
        self.assertFalse(habit.pending_parent_review)
        self.assertEqual(habit.xp_reward, 12)
        self.assertEqual(HabitSkillTag.objects.filter(habit=habit).count(), 1)

    def test_child_cannot_approve_habit(self):
        from apps.habits.models import Habit

        habit = Habit.objects.create(
            name="Mine", habit_type="positive",
            user=self.child, created_by=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/habits/{habit.pk}/approve/", {
            "xp_reward": 50,
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_parent_destroy_pending_notifies_proposer(self):
        from apps.habits.models import Habit
        from apps.notifications.models import Notification, NotificationType

        habit = Habit.objects.create(
            name="Silly", habit_type="positive",
            user=self.child, created_by=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/habits/{habit.pk}/")
        self.assertIn(resp.status_code, (200, 204))
        self.assertTrue(
            Notification.objects.filter(
                user=self.child,
                notification_type=NotificationType.HABIT_PROPOSAL_REJECTED,
            ).exists(),
        )

    def test_propose_emits_parent_notification(self):
        from apps.notifications.models import Notification, NotificationType

        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/habits/", {
            "name": "Stretch", "habit_type": "positive",
            "user": self.child.id,
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        self.assertTrue(
            Notification.objects.filter(
                user=self.parent,
                notification_type=NotificationType.HABIT_PROPOSED,
            ).exists(),
        )


class HabitLogTests(_Fixture):
    def _make_habit(self, habit_type="positive", name="H"):
        from apps.habits.models import Habit
        return Habit.objects.create(
            name=name, habit_type=habit_type,
            user=self.child, created_by=self.child,
        )

    @patch("apps.rpg.services.GameLoopService.on_task_completed", return_value={})
    def test_positive_tap(self, mock_gl):
        habit = self._make_habit(name="Water")
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/habits/{habit.pk}/log/", {
            "direction": 1,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        mock_gl.assert_called_once()

    def test_negative_tap_on_positive_habit_rejected(self):
        habit = self._make_habit(name="Good")
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/habits/{habit.pk}/log/", {
            "direction": -1,
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    @patch("apps.rpg.services.GameLoopService.on_task_completed", return_value={})
    def test_both_type_accepts_positive_and_negative(self, mock_gl):
        habit = self._make_habit(habit_type="both", name="Snacking")
        self.client.force_authenticate(self.child)
        # +1 tap.
        resp1 = self.client.post(f"/api/habits/{habit.pk}/log/", {
            "direction": 1,
        }, format="json")
        self.assertEqual(resp1.status_code, 200)
        self.assertNotIn("coin_reward", resp1.json())
        # -1 tap.
        resp2 = self.client.post(f"/api/habits/{habit.pk}/log/", {
            "direction": -1,
        }, format="json")
        self.assertEqual(resp2.status_code, 200)

    @patch("apps.rpg.services.GameLoopService.on_task_completed", return_value={})
    def test_positive_tap_rejected_over_daily_cap(self, _mock_gl):
        from apps.habits.models import Habit
        habit = Habit.objects.create(
            name="Brush teeth", habit_type="positive",
            user=self.child, created_by=self.child,
            max_taps_per_day=2,
        )
        self.client.force_authenticate(self.child)
        for _ in range(2):
            ok = self.client.post(f"/api/habits/{habit.pk}/log/", {
                "direction": 1,
            }, format="json")
            self.assertEqual(ok.status_code, 200)
        over = self.client.post(f"/api/habits/{habit.pk}/log/", {
            "direction": 1,
        }, format="json")
        self.assertEqual(over.status_code, 400)
        self.assertIn("Daily limit reached", over.json().get("error", ""))
