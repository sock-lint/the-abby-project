"""Approval's XP and proof history survive a withdrawal with an older snapshot."""
from unittest.mock import patch

from django.db.models.fields.files import FieldFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.homework.models import (
    HomeworkAssignment, HomeworkProof, HomeworkSkillTag, HomeworkSubmission,
)
from apps.homework.services import HomeworkService
from apps.homework.views import HomeworkSubmissionViewSet
from config.tests.factories import make_family


class HomeworkWithdrawalIntegrityTests(TestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "parent"}], children=[{"username": "child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.assignment = HomeworkAssignment.objects.create(
            title="Math review", subject="math", due_date=timezone.localdate(),
            assigned_to=self.child, created_by=self.parent,
        )
        self.skill = Skill.objects.create(
            name="Arithmetic", category=SkillCategory.objects.create(name="Math"),
        )
        HomeworkSkillTag.objects.create(assignment=self.assignment, skill=self.skill, xp_amount=15)
        self.submission = HomeworkSubmission.objects.create(
            assignment=self.assignment, user=self.child, status="pending", timeliness="on_time",
        )
        self.proof = HomeworkProof.objects.create(
            submission=self.submission, image="homework_proofs/example.png",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def test_approval_after_withdraw_lookup_preserves_xp_record_and_blobs(self):
        original_get_object = HomeworkSubmissionViewSet.get_object

        def approve_after_read(view):
            stale = original_get_object(view)
            HomeworkService.approve_submission(HomeworkSubmission.objects.get(pk=stale.pk), self.parent)
            return stale

        with patch.object(HomeworkSubmissionViewSet, "get_object", approve_after_read):
            with patch.object(FieldFile, "delete") as delete_blob:
                response = self.client.post(f"/api/homework-submissions/{self.submission.pk}/withdraw/")
        self.assertEqual(response.status_code, 400)
        delete_blob.assert_not_called()
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "approved")
        self.assertTrue(HomeworkProof.objects.filter(pk=self.proof.pk).exists())
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)
        self.assertEqual(self.assignment.submissions.filter(status="approved").count(), 1)

    def test_rejection_after_stale_lookup_preserves_record_without_blob_cleanup(self):
        stale = HomeworkSubmission.objects.get(pk=self.submission.pk)
        HomeworkService.reject_submission(self.submission, self.parent)
        with patch.object(HomeworkSubmissionViewSet, "get_object", return_value=stale):
            with patch.object(FieldFile, "delete") as delete_blob:
                response = self.client.post(f"/api/homework-submissions/{self.submission.pk}/withdraw/")
        self.assertEqual(response.status_code, 400)
        delete_blob.assert_not_called()
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "rejected")
        self.assertTrue(HomeworkProof.objects.filter(pk=self.proof.pk).exists())

    def test_blob_failure_preserves_pending_submission_and_proof_rows(self):
        with patch.object(FieldFile, "delete", side_effect=RuntimeError("storage unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(f"/api/homework-submissions/{self.submission.pk}/withdraw/")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "pending")
        self.assertTrue(HomeworkProof.objects.filter(pk=self.proof.pk).exists())

    def test_deleted_after_lookup_returns_not_found_without_blob_cleanup(self):
        stale = HomeworkSubmission.objects.get(pk=self.submission.pk)
        pk = self.submission.pk
        self.submission.delete()
        with patch.object(HomeworkSubmissionViewSet, "get_object", return_value=stale):
            with patch.object(FieldFile, "delete") as delete_blob:
                response = self.client.post(f"/api/homework-submissions/{pk}/withdraw/")
        self.assertEqual(response.status_code, 404)
        delete_blob.assert_not_called()

    def test_withdrawal_winning_after_approval_lookup_returns_not_found(self):
        original_get_object = HomeworkSubmissionViewSet.get_object

        def withdraw_after_read(view):
            stale = original_get_object(view)
            HomeworkSubmission.objects.filter(pk=stale.pk).delete()
            return stale

        self.client.force_authenticate(self.parent)
        with patch.object(HomeworkSubmissionViewSet, "get_object", withdraw_after_read):
            response = self.client.post(f"/api/homework-submissions/{self.submission.pk}/approve/")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SkillProgress.objects.filter(user=self.child, skill=self.skill).exists())
