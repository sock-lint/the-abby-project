"""Bonus state transitions cannot replay awards or hide failed rewards."""
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.achievements.services import AwardService
from apps.creations.models import Creation
from apps.creations.services import CreationError, CreationService
from apps.creations.views import CreationViewSet
from config.tests.factories import make_family


class CreationBonusIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "parent"}], children=[{"username": "child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        category = SkillCategory.objects.create(name="Art & Crafts")
        self.skill = Skill.objects.create(category=category, name="Drawing")
        # String image references exercise bonus logic without writing blobs.
        self.creation = Creation.objects.create(
            user=self.child, image="creations/example.png", occurred_on=timezone.localdate(),
            primary_skill=self.skill, status="pending", xp_awarded=10,
        )
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=10)
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def xp(self):
        return SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points

    def test_repeated_api_approval_awards_bonus_once(self):
        for _ in range(2):
            response = self.client.post(f"/api/creations/{self.creation.pk}/approve/", {}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], "approved")
            self.assertEqual(response.data["bonus_xp_awarded"], 15)
        self.assertEqual(self.xp(), 25)
        self.assertEqual(self.child.notifications.filter(notification_type="creation_approved").count(), 1)

    def test_stale_approval_cannot_award_again_or_change_bonus(self):
        stale = Creation.objects.get(pk=self.creation.pk)
        CreationService.approve_bonus(self.creation, self.parent)
        decided_at = self.creation.decided_at
        result = CreationService.approve_bonus(stale, self.parent, bonus_xp=99)
        self.assertEqual(result.status, "approved")
        self.assertEqual(result.bonus_xp_awarded, 15)
        self.assertEqual(result.decided_at, decided_at)
        self.assertEqual(self.xp(), 25)

    def test_only_pending_creations_can_be_approved(self):
        for state in ("logged", "rejected"):
            with self.subTest(state=state):
                Creation.objects.filter(pk=self.creation.pk).update(status=state)
                response = self.client.post(f"/api/creations/{self.creation.pk}/approve/", {}, format="json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["status"], state)
                self.assertEqual(response.data["bonus_xp_awarded"], 0)
        self.assertEqual(self.xp(), 10)
        self.assertFalse(self.child.notifications.filter(notification_type="creation_approved").exists())

    def test_stale_reject_cannot_reopen_an_approved_bonus(self):
        stale = Creation.objects.get(pk=self.creation.pk)
        CreationService.approve_bonus(self.creation, self.parent)
        with patch.object(CreationViewSet, "get_object", return_value=stale):
            response = self.client.post(f"/api/creations/{self.creation.pk}/reject/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "approved")
        CreationService.submit_for_bonus(stale)
        self.assertEqual(stale.status, "approved")
        self.assertEqual(self.xp(), 25)
        self.assertFalse(self.child.notifications.filter(notification_type="creation_rejected").exists())

    def test_stale_approve_cannot_award_a_rejected_bonus(self):
        stale = Creation.objects.get(pk=self.creation.pk)
        CreationService.reject_bonus(self.creation, self.parent)
        result = CreationService.approve_bonus(stale, self.parent)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(self.xp(), 10)

    def test_repeated_stale_rejection_notifies_once(self):
        stale = Creation.objects.get(pk=self.creation.pk)
        CreationService.reject_bonus(self.creation, self.parent)
        CreationService.reject_bonus(stale, self.parent)
        self.assertEqual(stale.status, "rejected")
        self.assertEqual(self.child.notifications.filter(notification_type="creation_rejected").count(), 1)

    def test_rejected_creation_can_be_resubmitted_and_awarded_once(self):
        CreationService.reject_bonus(self.creation, self.parent)
        CreationService.submit_for_bonus(self.creation)
        self.assertEqual(self.creation.status, "pending")
        CreationService.approve_bonus(self.creation, self.parent)
        CreationService.approve_bonus(self.creation, self.parent)
        self.assertEqual(self.xp(), 25)

    def test_stale_logged_submit_cannot_reopen_approved_bonus(self):
        Creation.objects.filter(pk=self.creation.pk).update(status="logged")
        stale = Creation.objects.get(pk=self.creation.pk)
        CreationService.submit_for_bonus(self.creation)
        CreationService.approve_bonus(self.creation, self.parent)
        result = CreationService.submit_for_bonus(stale)
        self.assertEqual(result.status, "approved")
        self.assertEqual(self.parent.notifications.filter(notification_type="creation_submitted").count(), 1)

    def test_repeated_stale_submit_notifies_once(self):
        Creation.objects.filter(pk=self.creation.pk).update(status="logged")
        stale = Creation.objects.get(pk=self.creation.pk)
        CreationService.submit_for_bonus(self.creation)
        CreationService.submit_for_bonus(stale)
        self.assertEqual(stale.status, "pending")
        self.assertEqual(self.parent.notifications.filter(notification_type="creation_submitted").count(), 1)

    def test_stale_service_withdraw_cannot_reopen_approved_bonus(self):
        stale = Creation.objects.get(pk=self.creation.pk)
        CreationService.approve_bonus(self.creation, self.parent)
        result = CreationService.withdraw_bonus_request(stale)
        self.assertEqual(result.status, "approved")
        self.assertEqual(self.xp(), 25)

    def test_approval_between_withdraw_lookup_and_lock_is_preserved(self):
        original_get_object = CreationViewSet.get_object

        def approve_after_read(view):
            stale = original_get_object(view)
            CreationService.approve_bonus(Creation.objects.get(pk=stale.pk), self.parent)
            return stale

        self.client.force_authenticate(self.child)
        with patch.object(CreationViewSet, "get_object", approve_after_read):
            response = self.client.post(f"/api/creations/{self.creation.pk}/withdraw/")
        self.assertEqual(response.status_code, 400)
        self.creation.refresh_from_db()
        self.assertEqual(self.creation.status, "approved")
        self.assertEqual(self.xp(), 25)

    def test_service_reward_failure_rolls_back_xp_tags_and_decision(self):
        grant = AwardService.grant

        def grant_then_fail(*args, **kwargs):
            grant(*args, **kwargs)
            raise RuntimeError("bonus processing failed")

        with patch.object(AwardService, "grant", side_effect=grant_then_fail):
            with self.assertRaises(CreationError):
                CreationService.approve_bonus(
                    self.creation, self.parent,
                    extra_skill_tags=[{"skill_id": self.skill.pk, "xp_weight": 1}],
                )
        self.creation.refresh_from_db()
        self.assertEqual(self.creation.status, "pending")
        self.assertEqual(self.creation.bonus_xp_awarded, 0)
        self.assertIsNone(self.creation.decided_at)
        self.assertFalse(self.creation.bonus_skill_tags.exists())
        self.assertEqual(self.xp(), 10)
        self.assertFalse(self.child.notifications.filter(notification_type="creation_approved").exists())

    def test_api_reward_failure_is_handled_and_retry_awards_once(self):
        grant = AwardService.grant

        def grant_then_fail(*args, **kwargs):
            grant(*args, **kwargs)
            raise RuntimeError("bonus processing failed")

        with patch.object(AwardService, "grant", side_effect=grant_then_fail):
            failed = self.client.post(f"/api/creations/{self.creation.pk}/approve/", {}, format="json")
        self.assertEqual(failed.status_code, 400)
        self.assertIn("Please try again", failed.data["error"])
        self.creation.refresh_from_db()
        self.assertEqual(self.creation.status, "pending")
        self.assertEqual(self.xp(), 10)
        retried = self.client.post(f"/api/creations/{self.creation.pk}/approve/", {}, format="json")
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(self.xp(), 25)
