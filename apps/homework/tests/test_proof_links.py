"""Shareable homework proof links use the normal saved review lifecycle."""
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
from apps.homework.services import HomeworkError, HomeworkService
from apps.notifications.models import Notification, NotificationType
from config.tests.factories import make_family


def image():
    output = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format="PNG")
    return SimpleUploadedFile("synthetic-proof.png", output.getvalue(), content_type="image/png")


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class HomeworkProofLinkTests(APITestCase):
    def setUp(self):
        media = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=media))
        household = make_family(
            parents=[{"username": "proof-parent"}],
            children=[{"username": "proof-child"}, {"username": "proof-sibling"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.sibling = household.children[1]
        self.assignment = HomeworkAssignment.objects.create(
            title="Reading response", subject="reading",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        self.submit_url = f"/api/homework/{self.assignment.pk}/submit/"
        self.proof_url = "https://drive.google.com/file/d/synthetic-homework/view?resourcekey=synthetic#page=2"
        self.client.force_authenticate(self.child)

    def test_child_submits_shareable_link_without_photos_for_parent_review(self):
        response = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        submission = HomeworkSubmission.objects.get(pk=response.data["id"])
        self.assertEqual(submission.proof_url, self.proof_url)
        self.assertEqual(submission.proofs.count(), 0)
        self.assertEqual(response.data["proof_url"], self.proof_url)
        self.client.force_authenticate(self.parent)
        pending = self.client.get("/api/homework-submissions/", {"status": "pending"})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.data["results"][0]["proof_url"], self.proof_url)

    def test_json_link_is_trimmed_without_fetching_or_changing_sharing_identifiers(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("Proof links must not resolve DNS")):
            with patch("requests.sessions.Session.request", side_effect=AssertionError("Proof links must not be fetched")):
                response = self.client.post(
                    self.submit_url, {"proof_url": f"  {self.proof_url}  ", "notes": "Finished reading"},
                    format="json",
                )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["proof_url"], self.proof_url)
        self.assertEqual(response.data["notes"], "Finished reading")
        self.assertEqual(response.data["proofs"], [])

    def test_photo_and_link_are_saved_together(self):
        response = self.client.post(
            self.submit_url, {"proof_url": self.proof_url, "images": [image()]}, format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["proof_url"], self.proof_url)
        self.assertEqual(len(response.data["proofs"]), 1)
        self.assertTrue(response.data["proofs"][0]["image"].endswith(".png"))
        self.assertEqual(HomeworkProof.objects.count(), 1)

    def test_shareable_http_and_https_links_are_not_limited_to_google_drive(self):
        for proof_url in (
            "https://www.dropbox.com/s/synthetic/proof.pdf?dl=0",
            "https://school.example/homework/response#section-2",
            "http://school.example/homework/response",
        ):
            with self.subTest(proof_url=proof_url):
                response = self.client.post(self.submit_url, {"proof_url": proof_url}, format="json")
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["proof_url"], proof_url)
                HomeworkSubmission.objects.get(pk=response.data["id"]).delete()

    def test_photo_only_submission_remains_compatible(self):
        response = self.client.post(self.submit_url, {"images": [image()]}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["proof_url"], "")
        self.assertEqual(len(response.data["proofs"]), 1)

    def test_blank_optional_link_with_a_photo_is_saved_as_empty_string(self):
        response = self.client.post(
            self.submit_url, {"images": [image()], "proof_url": "   "}, format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["proof_url"], "")

    def test_missing_or_blank_proof_is_rejected_without_saving(self):
        for payload in ({}, {"proof_url": "   "}):
            with self.subTest(payload=payload):
                response = self.client.post(self.submit_url, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["error"], "Add a proof photo or a proof link.")
        self.assertFalse(HomeworkSubmission.objects.exists())

    def test_unsafe_or_malformed_links_are_rejected_before_saving_or_notifying(self):
        invalid = [
            "javascript:alert(1)", "data:text/html,proof", "ftp://example.com/proof",
            "//drive.google.com/proof", "drive.google.com/proof", "https:///proof",
            "https://[invalid/proof", "https://example.com:invalid/proof", "https://example.com:65536/proof",
            "https://user@example.com/proof", "https://user:secret@example.com/proof",
            "https://example.com/proof\nnext", "\rhttps://example.com/proof",
            "https://example.com/\x00proof", "https://example.com/\x7fproof",
            "https://example.com/" + "a" * 2048,
            None, [], {}, 42, True,
        ]
        for value in invalid:
            with self.subTest(value=repr(value)):
                response = self.client.post(self.submit_url, {"proof_url": value}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data["error"], "Enter a valid proof link starting with http:// or https://.")
        self.assertFalse(HomeworkSubmission.objects.exists())
        self.assertFalse(HomeworkProof.objects.exists())
        self.assertFalse(Notification.objects.filter(notification_type=NotificationType.HOMEWORK_SUBMITTED).exists())

    def test_an_image_does_not_silently_hide_an_invalid_link(self):
        response = self.client.post(
            self.submit_url, {"images": [image()], "proof_url": "javascript:alert(1)"}, format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(HomeworkSubmission.objects.exists())
        self.assertFalse(HomeworkProof.objects.exists())

    def test_unicode_control_characters_in_link_paths_and_queries_are_rejected(self):
        for char in ("\u0080", "\u0081", "\u009f"):
            for location in (f"/proof{char}document", f"/proof?document={char}synthetic"):
                with self.subTest(codepoint=f"U+{ord(char):04X}", location=repr(location)):
                    response = self.client.post(
                        self.submit_url, {"proof_url": f"https://example.com{location}"}, format="json",
                    )
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertEqual(response.data["error"], "Enter a valid proof link starting with http:// or https://.")
                    self.assertFalse(HomeworkSubmission.objects.filter(assignment=self.assignment).exists())
                # Keep every request independent if a regression wrongly saves a submission.
                HomeworkSubmission.objects.filter(assignment=self.assignment).delete()

    def test_browser_bom_whitespace_inside_proof_links_is_rejected(self):
        for location in ("/proof\ufeffdocument", "/proof?key=synthetic\ufeffnext"):
            with self.subTest(location=repr(location)):
                response = self.client.post(
                    self.submit_url, {"proof_url": f"https://example.test{location}"}, format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data["error"], "Enter a valid proof link starting with http:// or https://.")
                self.assertFalse(HomeworkSubmission.objects.filter(assignment=self.assignment).exists())
            HomeworkSubmission.objects.filter(assignment=self.assignment).delete()

    def test_direct_service_call_enforces_the_same_link_validation(self):
        with self.assertRaisesMessage(HomeworkError, "Enter a valid proof link"):
            HomeworkService.submit_completion(
                self.child, self.assignment, [], proof_url="file:///private/proof",
            )
        self.assertFalse(HomeworkSubmission.objects.exists())

    def test_links_do_not_allow_parent_or_other_child_submissions(self):
        self.client.force_authenticate(self.parent)
        response = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="json")
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.sibling)
        response = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(HomeworkSubmission.objects.exists())

    def test_submission_links_stay_within_the_existing_owner_and_family_read_boundaries(self):
        response = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="json")
        self.assertEqual(response.status_code, 201)
        detail_url = f"/api/homework-submissions/{response.data['id']}/"
        other = make_family(
            "Other household", parents=[{"username": "other-proof-parent"}],
            children=[{"username": "other-proof-child"}],
        )
        for actor in (self.sibling, other.parents[0], other.children[0]):
            with self.subTest(actor=actor.username):
                self.client.force_authenticate(actor)
                self.assertEqual(self.client.get(detail_url).status_code, 404)
                listed = self.client.get("/api/homework-submissions/")
                self.assertEqual(listed.status_code, 200)
                self.assertEqual(listed.data["results"], [])
        for actor in (other.parents[0], other.children[0]):
            with self.subTest(submitter=actor.username):
                self.client.force_authenticate(actor)
                self.assertEqual(self.client.post(self.submit_url, {"proof_url": self.proof_url}).status_code, 404)
        for actor in (self.child, self.parent):
            self.client.force_authenticate(actor)
            detail = self.client.get(detail_url)
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.data["proof_url"], self.proof_url)

    def test_withdrawal_removes_the_link_and_allows_resubmission_without_blob_cleanup(self):
        response = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="json")
        self.assertEqual(response.status_code, 201)
        with patch("django.db.models.fields.files.FieldFile.delete") as delete_blob:
            withdrawn = self.client.post(f"/api/homework-submissions/{response.data['id']}/withdraw/")
        self.assertEqual(withdrawn.status_code, 204)
        delete_blob.assert_not_called()
        self.assertFalse(HomeworkSubmission.objects.exists())
        resubmitted = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="json")
        self.assertEqual(resubmitted.status_code, 201)

    def test_rejected_link_remains_in_review_history_after_resubmission(self):
        original = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="json")
        self.assertEqual(original.status_code, 201)
        self.client.force_authenticate(self.parent)
        rejected = self.client.post(f"/api/homework-submissions/{original.data['id']}/reject/")
        self.assertEqual(rejected.status_code, 200)
        self.client.force_authenticate(self.child)
        replacement = "https://docs.google.com/document/d/synthetic-revised-work/edit"
        updated = self.client.post(self.submit_url, {"proof_url": replacement}, format="json")
        self.assertEqual(updated.status_code, 201)
        self.assertEqual(updated.data["proof_url"], replacement)
        self.client.force_authenticate(self.parent)
        reviewed = self.client.get("/api/homework-submissions/", {"status": "reviewed", "user_id": self.child.pk})
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(len(reviewed.data["results"]), 1)
        self.assertEqual(reviewed.data["results"][0]["proof_url"], self.proof_url)

    def test_approval_preserves_link_and_prevents_duplicate_or_withdrawn_submission(self):
        response = self.client.post(self.submit_url, {"proof_url": self.proof_url}, format="json")
        self.assertEqual(response.status_code, 201)
        submission_id = response.data["id"]
        self.client.force_authenticate(self.parent)
        approved = self.client.post(f"/api/homework-submissions/{submission_id}/approve/")
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["proof_url"], self.proof_url)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.post(f"/api/homework-submissions/{submission_id}/withdraw/").status_code, 400)
        self.assertEqual(self.client.post(self.submit_url, {"proof_url": self.proof_url}).status_code, 400)
        self.assertEqual(HomeworkSubmission.objects.count(), 1)
        saved = HomeworkSubmission.objects.get(pk=submission_id)
        self.assertEqual(saved.proof_url, self.proof_url)
        self.assertEqual(saved.status, "approved")
