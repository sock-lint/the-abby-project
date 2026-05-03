"""Tests for achievements viewsets and skill-tree endpoint."""
from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.achievements.models import (
    Badge, Skill, SkillProgress, Subject, UserBadge,
)
from apps.achievements.models import SkillCategory
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        # ``parent`` is a regular signup-created parent — not is_staff, so they
        # cannot author global content (Skills/Badges/Subjects/Categories).
        # ``staff_parent`` mirrors what ``createsuperuser`` and the seed-data
        # founding parent get: is_staff=True, allowed to mutate global content.
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.staff_parent = User.objects.create_user(
            username="sp", password="pw", role="parent", is_staff=True,
        )
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()
        self.category = SkillCategory.objects.create(name="Cooking", icon="chef")
        self.subject = Subject.objects.create(name="Baking", category=self.category)


class SkillTreeViewTests(_Fixture):
    def test_tree_returns_subjects_and_skills(self):
        skill = Skill.objects.create(
            name="Bread", category=self.category, subject=self.subject,
        )
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=150, level=1)
        self.client.force_authenticate(self.child)
        resp = self.client.get(f"/api/skills/tree/{self.category.id}/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("subjects", body)
        names = [s["name"] for s in body["subjects"]]
        self.assertIn("Baking", names)


class BadgeViewSetTests(_Fixture):
    def test_list_badges_authenticated(self):
        Badge.objects.create(
            name="First", description="first", criteria_type="first_project",
            criteria_value={},
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/badges/")
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_forbidden(self):
        resp = self.client.get("/api/badges/")
        self.assertEqual(resp.status_code, 401)

    def test_child_cannot_create_badge(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/badges/", {
            "name": "X", "description": "x", "criteria_type": "first_project",
            "criteria_value": {},
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_non_staff_parent_cannot_create_badge(self):
        # Signup-created parents are not is_staff and must not be able to
        # mutate the global Badge catalog visible to every other family.
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/badges/", {
            "name": "Should Fail", "description": "x", "criteria_type": "first_project",
            "criteria_value": {},
        }, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Badge.objects.filter(name="Should Fail").exists())

    def test_staff_parent_can_create_badge(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.post("/api/badges/", {
            "name": "Created", "description": "x", "criteria_type": "first_project",
            "criteria_value": {},
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(Badge.objects.filter(name="Created").exists())


class UserBadgeModelScopingTests(_Fixture):
    """Covers the child-self-scoping invariant at the model level.

    The view is currently shadowed by ``BadgeViewSet.retrieve`` (tracked in a
    separate fix) so we assert the queryset-level behavior directly here.
    """

    def test_child_sees_only_own_earned_badges_via_queryset(self):
        badge = Badge.objects.create(
            name="B", description="d", criteria_type="first_project",
            criteria_value={},
        )
        UserBadge.objects.create(user=self.child, badge=badge)
        UserBadge.objects.create(user=self.parent, badge=badge)

        from types import SimpleNamespace

        from apps.achievements.views import UserBadgeViewSet

        viewset = UserBadgeViewSet()
        viewset.request = SimpleNamespace(user=self.child)
        qs = viewset.get_queryset()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().user, self.child)


class SubjectViewSetTests(_Fixture):
    def test_staff_parent_can_create_subject(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.post("/api/subjects/", {
            "name": "Grilling", "category": self.category.id,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(Subject.objects.filter(name="Grilling").exists())

    def test_non_staff_parent_cannot_create_subject(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/subjects/", {
            "name": "Grilling", "category": self.category.id,
        }, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Subject.objects.filter(name="Grilling").exists())

    def test_child_cannot_create_subject(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/subjects/", {
            "name": "Grilling", "category": self.category.id,
        }, format="json")
        self.assertEqual(resp.status_code, 403)


class SkillViewSetTests(_Fixture):
    def test_staff_parent_can_create_skill(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.post("/api/skills/", {
            "name": "Searing", "category": self.category.id, "subject": self.subject.id,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))

    def test_non_staff_parent_cannot_create_skill(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/skills/", {
            "name": "Searing", "category": self.category.id, "subject": self.subject.id,
        }, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Skill.objects.filter(name="Searing").exists())


class SkillCategoryViewSetTests(_Fixture):
    def test_staff_parent_can_create_category(self):
        self.client.force_authenticate(self.staff_parent)
        resp = self.client.post("/api/categories/", {
            "name": "Music", "icon": "music",
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(SkillCategory.objects.filter(name="Music").exists())

    def test_non_staff_parent_cannot_create_category(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/categories/", {
            "name": "Music", "icon": "music",
        }, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(SkillCategory.objects.filter(name="Music").exists())
