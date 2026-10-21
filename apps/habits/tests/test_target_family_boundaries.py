"""Habit writes validate the replacement owner, before any saved changes."""
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.habits.models import Habit, HabitLog, HabitSkillTag
from apps.habits.serializers import HabitWriteSerializer
from apps.notifications.models import Notification
from apps.quests.models import ChallengeActivity, ChallengeGoal, ChallengeOccurrence
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HabitTargetFamilyBoundaryTests(TestCase):
    def setUp(self):
        family = make_family("Habit owner household", parents=[
            {"username": "habit-owner-parent"}, {"username": "habit-owner-coparent"},
        ], children=[{"username": "habit-owner-child"}, {"username": "habit-owner-sibling"}])
        foreign = make_family("Other habit household", parents=[{"username": "foreign-habit-parent"}],
                              children=[{"username": "foreign-habit-child"}])
        self.parent, self.coparent = family.parents
        self.child, self.sibling = family.children
        self.foreign_targets = [foreign.children[0], foreign.parents[0]]
        category = SkillCategory.objects.create(name="Habit boundary practice")
        self.saved_skill = Skill.objects.create(name="Saved habit skill", category=category)
        self.new_skill = Skill.objects.create(name="New habit skill", category=category)
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def state(self):
        return {model._meta.label: list(model.objects.order_by("pk").values()) for model in (
            Habit, HabitSkillTag, HabitLog, Notification, SkillProgress, ActivityEvent,
            ChallengeActivity, ChallengeGoal, ChallengeOccurrence, CoinLedger,
        )}

    def payload(self, target):
        return {"name": "Unapproved replacement rules", "habit_type": "positive", "user": target.pk,
                "xp_reward": 500, "max_taps_per_day": 20,
                "skill_tags": [{"skill_id": self.new_skill.pk, "xp_weight": 4}]}

    def habit(self, *, pending=False):
        habit = Habit.objects.create(name="Saved household habit", user=self.child,
            created_by=self.child if pending else self.parent, pending_parent_review=pending,
            xp_reward=7, max_taps_per_day=2)
        HabitSkillTag.objects.create(habit=habit, skill=self.saved_skill, xp_weight=2)
        return habit

    def test_parent_create_rejects_foreign_child_and_parent_before_side_effects(self):
        for target in self.foreign_targets:
            with self.subTest(target_role=target.role):
                before = self.state()
                response = self.client.post("/api/habits/", self.payload(target), format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("user", response.data)
                self.assertEqual(self.state(), before)

    def reject_reassignment(self, method):
        for target in self.foreign_targets:
            with self.subTest(method=method, target_role=target.role):
                habit = self.habit()
                before = self.state()
                response = getattr(self.client, method)(f"/api/habits/{habit.pk}/", self.payload(target), format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("user", response.data)
                self.assertEqual(self.state(), before)

    def test_parent_patch_rejects_foreign_reassignment_before_side_effects(self):
        self.reject_reassignment("patch")

    def test_parent_put_rejects_foreign_reassignment_before_side_effects(self):
        self.reject_reassignment("put")

    def test_parent_approval_rejects_foreign_reassignment_before_publishing_or_notifying(self):
        for target in self.foreign_targets:
            with self.subTest(target_role=target.role):
                habit = self.habit(pending=True)
                before = self.state()
                response = self.client.post(f"/api/habits/{habit.pk}/approve/", self.payload(target), format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("user", response.data)
                self.assertEqual(self.state(), before)

    def test_foreign_and_missing_targets_return_the_same_safe_error(self):
        errors = []
        for target_id in (self.foreign_targets[0].pk, 999999):
            response = self.client.post("/api/habits/", {
                "name": "Invalid target", "user": target_id,
            }, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            errors.append(response.data)
        self.assertEqual(errors[0], errors[1])

    def test_write_serializer_without_actor_family_context_rejects_target(self):
        for request in (None, SimpleNamespace(), SimpleNamespace(user=AnonymousUser()),
                        SimpleNamespace(user=SimpleNamespace(role="parent", is_authenticated=True, family_id=None))):
            with self.subTest(request=request):
                context = {} if request is None else {"request": request}
                serializer = HabitWriteSerializer(data=self.payload(self.child), context=context)
                self.assertFalse(serializer.is_valid(), serializer.validated_data)
                self.assertIn("user", serializer.errors)

    def test_parent_can_create_for_same_family_child_self_or_coparent(self):
        for target in (self.child, self.sibling, self.parent, self.coparent):
            with self.subTest(target=target.username):
                response = self.client.post("/api/habits/", self.payload(target), format="json")
                self.assertEqual(response.status_code, 201, response.data)
                habit = Habit.objects.latest("pk")
                self.assertEqual((habit.user_id, habit.created_by_id), (target.pk, self.parent.pk))
                self.assertEqual(list(habit.skill_tags.values_list("skill_id", "xp_weight")), [(self.new_skill.pk, 4)])

    def test_parent_can_reassign_ordinary_habit_within_same_family(self):
        for target in (self.sibling, self.parent, self.coparent):
            with self.subTest(target=target.username):
                habit = self.habit()
                response = self.client.patch(f"/api/habits/{habit.pk}/", self.payload(target), format="json")
                self.assertEqual(response.status_code, 200, response.data)
                habit.refresh_from_db()
                self.assertEqual(habit.user_id, target.pk)

    def test_parent_approval_keeps_same_family_reassignment_supported(self):
        habit = self.habit(pending=True)
        response = self.client.post(f"/api/habits/{habit.pk}/approve/", self.payload(self.sibling), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        habit.refresh_from_db()
        self.assertEqual(habit.user_id, self.sibling.pk)
        self.assertFalse(habit.pending_parent_review)
        self.assertEqual(Notification.objects.filter(user=self.child).count(), 1)

    def test_starter_still_cannot_move_to_same_family_sibling(self):
        habit = self.habit()
        habit.starter_key = "brush_teeth"
        habit.save(update_fields=["starter_key"])
        before = self.state()
        response = self.client.patch(f"/api/habits/{habit.pk}/", self.payload(self.sibling), format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.state(), before)
