"""Tests for ChoreViewSet and ChoreCompletionViewSet."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreService
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()


class ChoreViewSetTests(_Fixture):
    def test_parent_creates_chore(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/chores/", {
            "title": "Dishes", "reward_amount": "1.50", "coin_reward": 5,
            "recurrence": "daily",
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))

    def test_child_create_produces_pending_proposal(self):
        """Children can now create chores, but they land as pending proposals."""
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/chores/", {
            "title": "Feed cat", "icon": "🐈", "recurrence": "daily",
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        chore = Chore.objects.get(title="Feed cat")
        self.assertTrue(chore.pending_parent_review)
        self.assertEqual(chore.created_by, self.child)
        self.assertEqual(chore.assigned_to, self.child)

    def test_child_create_strips_reward_fields(self):
        """Payload reward fields from a child are ignored — parent sets them."""
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/chores/", {
            "title": "Sneaky",
            "reward_amount": "50.00",
            "coin_reward": 500,
            "xp_reward": 500,
            "recurrence": "daily",
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        chore = Chore.objects.get(title="Sneaky")
        self.assertEqual(chore.reward_amount, Decimal("0.00"))
        self.assertEqual(chore.coin_reward, 0)
        # xp_reward default is 10 — still the model default, not the 500 posted.
        self.assertEqual(chore.xp_reward, 10)

    def test_child_create_strips_skill_tags(self):
        from apps.achievements.models import Skill, SkillCategory
        from apps.chores.models import ChoreSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        skill = Skill.objects.create(name="Persistence", category=cat)
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/chores/", {
            "title": "Tagged", "recurrence": "daily",
            "skill_tags": [{"skill_id": skill.id, "xp_weight": 5}],
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        chore = Chore.objects.get(title="Tagged")
        self.assertEqual(ChoreSkillTag.objects.filter(chore=chore).count(), 0)

    def test_pending_proposal_hidden_from_child_list(self):
        """A pending proposal must not appear in the child's tap surface."""
        Chore.objects.create(
            title="Proposed", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        Chore.objects.create(
            title="Live", created_by=self.parent, reward_amount=Decimal("1"),
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chores/")
        self.assertEqual(resp.status_code, 200)
        titles = [row["title"] for row in resp.json()]
        self.assertIn("Live", titles)
        self.assertNotIn("Proposed", titles)

    def test_child_can_list_own_pending_proposals(self):
        """?pending=true returns the child's own proposals so they can track them."""
        Chore.objects.create(
            title="Mine", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        other_child = User.objects.create_user(
            username="c2", password="pw", role="child",
        )
        Chore.objects.create(
            title="Sibling's", created_by=other_child, assigned_to=other_child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chores/?pending=true")
        self.assertEqual(resp.status_code, 200)
        rows = resp.json().get("results", resp.json())
        titles = [row["title"] for row in rows]
        self.assertEqual(titles, ["Mine"])

    def test_parent_sees_all_pending_proposals(self):
        Chore.objects.create(
            title="From child", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        Chore.objects.create(
            title="Live", created_by=self.parent, reward_amount=Decimal("1"),
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/chores/?pending=true")
        self.assertEqual(resp.status_code, 200)
        rows = resp.json().get("results", resp.json())
        titles = [row["title"] for row in rows]
        self.assertEqual(titles, ["From child"])

    def test_child_cannot_complete_pending_proposal(self):
        """Child's queryset hides pending proposals, so /complete/ 404s.

        The ``ChoreService.submit_completion`` belt-and-suspenders guard
        is separately exercised by a service-level test — see
        ``test_services.py``."""
        chore = Chore.objects.create(
            title="Pending", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chores/{chore.id}/complete/", format="json")
        self.assertEqual(resp.status_code, 404)

    def test_submit_completion_service_refuses_pending_chore(self):
        """Direct service call also refuses, in case a caller bypasses the view."""
        chore = Chore.objects.create(
            title="Pending", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        from apps.chores.services import ChoreNotAvailableError, ChoreService

        with self.assertRaises(ChoreNotAvailableError):
            ChoreService.submit_completion(self.child, chore)

    def test_parent_approves_proposal_with_rewards(self):
        from apps.achievements.models import Skill, SkillCategory
        from apps.chores.models import ChoreSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        skill = Skill.objects.create(name="Persistence", category=cat)
        chore = Chore.objects.create(
            title="Water plants", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/chores/{chore.id}/approve/", {
            "reward_amount": "0.50", "coin_reward": 3, "xp_reward": 20,
            "skill_tags": [{"skill_id": skill.id, "xp_weight": 1}],
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        chore.refresh_from_db()
        self.assertFalse(chore.pending_parent_review)
        self.assertEqual(chore.reward_amount, Decimal("0.50"))
        self.assertEqual(chore.coin_reward, 3)
        self.assertEqual(chore.xp_reward, 20)
        self.assertEqual(ChoreSkillTag.objects.filter(chore=chore).count(), 1)

    def test_child_cannot_approve_proposal(self):
        chore = Chore.objects.create(
            title="Mine", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chores/{chore.id}/approve/", {
            "reward_amount": "10.00", "coin_reward": 100,
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_approve_rejects_already_published_chore(self):
        chore = Chore.objects.create(
            title="Live", created_by=self.parent, reward_amount=Decimal("1"),
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/chores/{chore.id}/approve/", {
            "reward_amount": "2.00",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_parent_destroy_pending_notifies_proposer(self):
        from apps.notifications.models import Notification, NotificationType

        chore = Chore.objects.create(
            title="Feed fish", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.parent)
        resp = self.client.delete(f"/api/chores/{chore.id}/")
        self.assertIn(resp.status_code, (200, 204))
        self.assertTrue(
            Notification.objects.filter(
                user=self.child,
                notification_type=NotificationType.CHORE_PROPOSAL_REJECTED,
            ).exists(),
        )

    def test_child_cannot_destroy_chore(self):
        chore = Chore.objects.create(
            title="Mine", created_by=self.child, assigned_to=self.child,
            pending_parent_review=True,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.delete(f"/api/chores/{chore.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_propose_emits_parent_notification(self):
        from apps.notifications.models import Notification, NotificationType

        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/chores/", {
            "title": "Feed cat", "recurrence": "daily",
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        self.assertTrue(
            Notification.objects.filter(
                user=self.parent,
                notification_type=NotificationType.CHORE_PROPOSED,
            ).exists(),
        )

    def test_complete_action_child_submits(self):
        chore = Chore.objects.create(title="Trash", reward_amount=Decimal("1"), created_by=self.parent)
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chores/{chore.id}/complete/", {"notes": "done"}, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(ChoreCompletion.objects.filter(chore=chore, user=self.child).exists())

    def test_create_chore_with_skill_tags(self):
        """Parent can POST skill_tags inline and the ViewSet applies them."""
        from apps.achievements.models import Skill, SkillCategory
        from apps.chores.models import ChoreSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat)
        s2 = Skill.objects.create(name="Time Management", category=cat)

        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/chores/", {
            "title": "Dishes", "reward_amount": "0.50", "coin_reward": 2,
            "xp_reward": 20, "recurrence": "daily",
            "skill_tags": [
                {"skill_id": s1.id, "xp_weight": 3},
                {"skill_id": s2.id, "xp_weight": 1},
            ],
        }, format="json")
        self.assertIn(resp.status_code, (200, 201), msg=resp.content)
        chore = Chore.objects.get(title="Dishes")
        tags = ChoreSkillTag.objects.filter(chore=chore).order_by("skill__name")
        self.assertEqual(tags.count(), 2)
        self.assertEqual(tags[0].xp_weight, 3)
        self.assertEqual(tags[1].xp_weight, 1)

    def test_update_chore_replaces_skill_tags(self):
        from apps.achievements.models import Skill, SkillCategory
        from apps.chores.models import ChoreSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat)
        s2 = Skill.objects.create(name="Time Management", category=cat)
        chore = Chore.objects.create(
            title="Trash", reward_amount=Decimal("1"), created_by=self.parent,
        )
        ChoreSkillTag.objects.create(chore=chore, skill=s1, xp_weight=1)

        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/chores/{chore.id}/", {
            "skill_tags": [{"skill_id": s2.id, "xp_weight": 5}],
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        tags = list(ChoreSkillTag.objects.filter(chore=chore))
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].skill_id, s2.id)
        self.assertEqual(tags[0].xp_weight, 5)

    def test_update_chore_without_skill_tags_leaves_them_alone(self):
        """Omitting skill_tags from the PATCH body must not strip existing tags."""
        from apps.achievements.models import Skill, SkillCategory
        from apps.chores.models import ChoreSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat)
        chore = Chore.objects.create(
            title="Trash", reward_amount=Decimal("1"), created_by=self.parent,
        )
        ChoreSkillTag.objects.create(chore=chore, skill=s1, xp_weight=2)

        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/chores/{chore.id}/", {
            "title": "Trash & Recycling",
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(
            ChoreSkillTag.objects.filter(chore=chore).count(), 1,
            "PATCH without skill_tags should leave tags untouched",
        )

    def test_create_with_empty_skill_tags_strips_tags(self):
        """POST with explicit empty list clears all tags (replacement semantics)."""
        from apps.achievements.models import Skill, SkillCategory
        from apps.chores.models import ChoreSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat)
        chore = Chore.objects.create(
            title="Trash", reward_amount=Decimal("1"), created_by=self.parent,
        )
        ChoreSkillTag.objects.create(chore=chore, skill=s1, xp_weight=2)

        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/chores/{chore.id}/", {
            "skill_tags": [],
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(
            ChoreSkillTag.objects.filter(chore=chore).count(), 0,
            "Empty skill_tags list should clear all tags",
        )

    def test_skill_tags_are_only_write(self):
        """GET response surfaces skill_tags as a nested-serializer read, not
        the ListField shape used for writes. The write-only ListField would
        otherwise crash on the reverse-FK RelatedManager when DRF tries to
        serialize the response after create."""
        from apps.achievements.models import Skill, SkillCategory
        from apps.chores.models import ChoreSkillTag

        cat = SkillCategory.objects.create(name="Life Skills", icon="🌟")
        s1 = Skill.objects.create(name="Persistence", category=cat, icon="💪")
        chore = Chore.objects.create(
            title="Dishes", reward_amount=Decimal("0.50"),
            created_by=self.parent, xp_reward=20,
        )
        ChoreSkillTag.objects.create(chore=chore, skill=s1, xp_weight=3)

        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/chores/{chore.id}/")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        body = resp.json()
        self.assertIn("skill_tags", body)
        self.assertEqual(len(body["skill_tags"]), 1)
        # Read shape is the nested serializer, not a list of dicts.
        tag = body["skill_tags"][0]
        self.assertEqual(tag["skill_name"], "Persistence")
        self.assertEqual(tag["skill_category"], "Life Skills")
        self.assertEqual(tag["xp_weight"], 3)

    def test_invalid_skill_id_in_skill_tags_returns_400(self):
        """Unknown skill_id in the tag list → 400 with a clear message.

        The view pre-validates skill IDs before the bulk_create because
        SQLite defers FK checks to commit, so without pre-validation the
        API would respond 201 and then rollback on IntegrityError —
        leaving callers confused about whether the chore persisted."""
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/chores/", {
            "title": "Bad Chore", "reward_amount": "0.00",
            "recurrence": "daily",
            "skill_tags": [{"skill_id": 999999, "xp_weight": 1}],
        }, format="json")
        self.assertEqual(resp.status_code, 400, msg=resp.content)
        self.assertIn("skill_tags", resp.json())
        self.assertFalse(
            Chore.objects.filter(title="Bad Chore").exists(),
            "Chore should not persist when skill_tags reference a missing skill",
        )


class ChoreCompletionViewSetTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.chore = Chore.objects.create(
            title="Trash", reward_amount=Decimal("1.00"), coin_reward=2,
            created_by=self.parent,
        )
        self.completion = ChoreService.submit_completion(self.child, self.chore)

    def test_child_sees_own_completions(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/chore-completions/")
        self.assertEqual(resp.status_code, 200)

    def test_parent_approves(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/chore-completions/{self.completion.id}/approve/")
        self.assertIn(resp.status_code, (200, 204))
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, "approved")

    def test_parent_rejects(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post(f"/api/chore-completions/{self.completion.id}/reject/")
        self.assertIn(resp.status_code, (200, 204))
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, "rejected")

    def test_child_cannot_approve(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post(f"/api/chore-completions/{self.completion.id}/approve/")
        self.assertEqual(resp.status_code, 403)
