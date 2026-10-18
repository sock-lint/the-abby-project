"""Real ORM cascades and stored bytes; only storage/database failures are mocked."""
import tempfile
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event
from unittest.mock import patch

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from apps.accounts.file_cleanup import process_pending_file_deletions
from apps.accounts.models import PendingFileDeletion
from apps.achievements.models import Skill, SkillCategory
from apps.creations.models import Creation
from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
from apps.ingestion.models import ProjectIngestionJob
from apps.portfolio.models import ProjectPhoto
from apps.printing.models import PrintRequest
from apps.projects.models import MaterialItem, Project
from apps.rewards.models import Reward
from apps.rpg.models import SpriteAsset
from config.tests.factories import make_family


class AccountCascadeFileRegression(TestCase):
    def test_account_delete_must_retain_a_durable_file_cleanup_reference(self):
        # This assertion was run against unmodified d3584779 and failed:
        # account cascades kept avatar bytes but discarded every cleanup pointer.
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            user = make_family(
                "Synthetic cleanup repro", parents=[{"username": "parent"}], children=[{"username": "child"}],
            ).children[0]
            user.avatar.save("synthetic.png", ContentFile(b"synthetic fixture"), save=True)
            storage, name = user.avatar.storage, user.avatar.name
            user.delete()
            candidates = [
                model for model in apps.get_app_config("accounts").get_models()
                if model.__name__ == "PendingFileDeletion"
            ]
            retained_reference = bool(candidates and candidates[0].objects.filter(storage_key=name).exists())
            self.assertTrue(
                not storage.exists(name) or retained_reference,
                "Account CASCADE kept avatar bytes but discarded every durable cleanup pointer",
            )


class FileCleanupTests(TransactionTestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings = override_settings(MEDIA_ROOT=self.media.name)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.family = make_family(
            "Deleted family", parents=[{"username": "parent"}], children=[{"username": "child"}],
        )
        self.parent = self.family.parents[0]
        self.child = self.family.children[0]

    def save_file(self, instance, field, name):
        file = getattr(instance, field)
        file.save(name, ContentFile(b"synthetic private fixture"), save=True)
        return file.name

    def queue_avatar(self):
        name = self.save_file(self.child, "avatar", "portrait.png")
        self.child.delete()
        return name

    def test_family_cascade_covers_every_private_file_field_and_preserves_other_family_and_global_art(self):
        project = Project.objects.create(title="Project", assigned_to=self.child, created_by=self.parent)
        material = MaterialItem.objects.create(project=project, name="Material")
        photo = ProjectPhoto.objects.create(project=project, user=self.child)
        assignment = HomeworkAssignment.objects.create(
            title="Homework", assigned_to=self.child, created_by=self.parent, due_date=timezone.localdate(),
        )
        submission = HomeworkSubmission.objects.create(assignment=assignment, user=self.child, timeliness="on_time")
        proof = HomeworkProof.objects.create(submission=submission)
        skill = Skill.objects.create(name="Drawing", category=SkillCategory.objects.create(name="Art & Crafts"))
        creation = Creation.objects.create(user=self.child, primary_skill=skill, occurred_on=timezone.localdate())
        imported = ProjectIngestionJob.objects.create(created_by=self.parent, source_type="pdf")
        reward = Reward.objects.create(family=self.family.family, name="Reward", cost_coins=5)
        print_request = PrintRequest.objects.create(user=self.child, title="Print", color="blue", reason="Learn")
        fields = [
            (self.child, "avatar", "portrait.png"),
            (project, "cover_photo", "cover.png"),
            (material, "receipt_photo", "receipt.png"),
            (photo, "image", "project.png"),
            (proof, "image", "homework.png"),
            (creation, "image", "creation.png"),
            (creation, "audio", "recording.webm"),
            (imported, "source_file", "source.pdf"),
            (reward, "image", "reward.png"),
            (print_request, "thumbnail", "thumbnail.png"),
            (print_request, "model_file", "part.stl"),
        ]
        names = [self.save_file(instance, field, name) for instance, field, name in fields]
        other = make_family("Other family", children=[{"username": "other"}]).children[0]
        other_name = self.save_file(other, "avatar", "other.png")
        sprite = SpriteAsset.objects.create(
            slug="retained-global", image="rpg-sprites/global.png", created_by=self.parent,
            frame_width_px=1, frame_height_px=1,
        )

        self.family.family.delete()

        self.assertCountEqual(PendingFileDeletion.objects.values_list("storage_key", flat=True), names)
        self.assertTrue(all(default_storage.exists(name) for name in names))
        self.assertEqual(process_pending_file_deletions(limit=100), {"deleted": 11, "failed": 0, "referenced": 0})
        self.assertTrue(all(not default_storage.exists(name) for name in names))
        self.assertTrue(default_storage.exists(other_name))
        sprite.refresh_from_db()
        self.assertIsNone(sprite.created_by)
        self.assertEqual(sprite.image.name, "rpg-sprites/global.png")
        self.assertFalse(PendingFileDeletion.objects.exists())
        self.assertEqual(process_pending_file_deletions(), {"deleted": 0, "failed": 0, "referenced": 0})

    def test_rollback_preserves_file_and_removes_uncommitted_outbox_rows(self):
        name = self.save_file(self.child, "avatar", "portrait.png")
        child_pk = self.child.pk
        with self.assertRaisesMessage(RuntimeError, "rollback"):
            with transaction.atomic():
                self.child.delete()
                self.assertTrue(PendingFileDeletion.objects.filter(storage_key=name).exists())
                raise RuntimeError("rollback")
        self.assertTrue(self.child.__class__.objects.filter(pk=child_pk).exists())
        self.assertTrue(default_storage.exists(name))
        self.assertFalse(PendingFileDeletion.objects.exists())

    def test_worker_refuses_to_remove_storage_inside_a_callers_transaction(self):
        name = self.queue_avatar()
        with transaction.atomic(), self.assertRaisesMessage(RuntimeError, "committed transaction"):
            process_pending_file_deletions()
        self.assertTrue(default_storage.exists(name))
        self.assertTrue(PendingFileDeletion.objects.exists())

    def test_storage_failure_retains_private_pointer_and_due_retry_succeeds(self):
        name = self.queue_avatar()
        with patch("apps.accounts.file_cleanup.default_storage.delete", side_effect=OSError("private path/secret")):
            self.assertEqual(process_pending_file_deletions(), {"deleted": 0, "failed": 1, "referenced": 0})
        job = PendingFileDeletion.objects.get()
        self.assertEqual(job.storage_key, name)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.last_error, "storage_error")
        self.assertGreater(job.retry_at, job.last_attempt_at)
        self.assertTrue(default_storage.exists(name))
        self.assertEqual(process_pending_file_deletions(), {"deleted": 0, "failed": 0, "referenced": 0})
        self.assertEqual(process_pending_file_deletions(now=job.retry_at), {"deleted": 1, "failed": 0, "referenced": 0})
        self.assertFalse(default_storage.exists(name))
        self.assertFalse(PendingFileDeletion.objects.exists())

    def test_shared_key_survives_until_other_family_removes_its_reference(self):
        name = self.save_file(self.child, "avatar", "shared.png")
        other = make_family("Other", children=[{"username": "other"}]).children[0]
        other.avatar = name
        other.save(update_fields=["avatar"])
        self.child.delete()
        self.assertEqual(process_pending_file_deletions(), {"deleted": 0, "failed": 0, "referenced": 1})
        job = PendingFileDeletion.objects.get()
        self.assertEqual(job.last_error, "still_referenced")
        self.assertTrue(default_storage.exists(name))
        other.delete()
        self.assertEqual(PendingFileDeletion.objects.count(), 1)
        self.assertEqual(process_pending_file_deletions(now=job.retry_at), {"deleted": 1, "failed": 0, "referenced": 0})
        self.assertFalse(default_storage.exists(name))

    def test_database_failure_after_storage_success_leaves_idempotent_retry(self):
        name = self.queue_avatar()
        with patch.object(PendingFileDeletion, "delete", side_effect=DatabaseError("lost connection")):
            with self.assertRaises(DatabaseError):
                process_pending_file_deletions()
        self.assertTrue(PendingFileDeletion.objects.filter(storage_key=name).exists())
        self.assertFalse(default_storage.exists(name))
        self.assertEqual(process_pending_file_deletions(), {"deleted": 1, "failed": 0, "referenced": 0})
        self.assertFalse(PendingFileDeletion.objects.exists())

    def test_batch_limit_and_operator_output_do_not_disclose_keys(self):
        first = self.queue_avatar()
        second = default_storage.save("ingestion/other-private-name.pdf", ContentFile(b"synthetic"))
        PendingFileDeletion.objects.create(storage_key=second)
        output = StringIO()
        call_command("cleanup_deleted_files", limit=1, stdout=output)
        self.assertIn("deleted=1 failed=0 referenced=0 pending=1", output.getvalue())
        self.assertNotIn(first, output.getvalue())
        self.assertNotIn(second, output.getvalue())

    def test_beat_task_retries_due_outbox_without_returning_private_metadata(self):
        from apps.accounts.tasks import cleanup_deleted_files

        self.queue_avatar()
        with self.assertLogs("apps.accounts.tasks", level="INFO") as logs:
            self.assertEqual(cleanup_deleted_files(), {"deleted": 1, "failed": 0, "referenced": 0})
        self.assertEqual(len(logs.output), 1)
        self.assertIn("Private file cleanup: deleted=1 failed=0 referenced=0", logs.output[0])
        self.assertNotIn("portrait.png", logs.output[0])

    def test_operator_status_is_read_only_and_reports_failure_counts_without_keys(self):
        name = self.queue_avatar()
        with patch("apps.accounts.file_cleanup.default_storage.delete", side_effect=OSError("private error")):
            from apps.accounts.tasks import cleanup_deleted_files

            with self.assertLogs("apps.accounts.tasks", level="WARNING"):
                cleanup_deleted_files()
        output = StringIO()
        with patch("apps.accounts.file_cleanup.default_storage.delete") as delete:
            call_command("cleanup_deleted_files", status=True, stdout=output)
        delete.assert_not_called()
        self.assertIn("due=0 pending=1 failed=1 referenced=0 oldest_pending=", output.getvalue())
        self.assertNotIn(name, output.getvalue())
        self.assertNotIn("private error", output.getvalue())
        self.assertTrue(PendingFileDeletion.objects.exists())

    @skipUnlessDBFeature("has_select_for_update_skip_locked")
    def test_concurrent_workers_skip_the_same_claimed_file(self):
        self.queue_avatar()
        entered = Event()
        release = Event()
        real_delete = default_storage.delete

        def blocked_delete(name):
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test did not release storage call")
            real_delete(name)

        def run_worker():
            close_old_connections()
            try:
                return process_pending_file_deletions()
            finally:
                connections["default"].close()

        with patch("apps.accounts.file_cleanup.default_storage.delete", side_effect=blocked_delete) as delete:
            with ThreadPoolExecutor(max_workers=1) as pool:
                worker = pool.submit(run_worker)
                try:
                    self.assertTrue(entered.wait(timeout=10))
                    self.assertEqual(
                        process_pending_file_deletions(), {"deleted": 0, "failed": 0, "referenced": 0},
                    )
                finally:
                    release.set()
                self.assertEqual(worker.result(timeout=10), {"deleted": 1, "failed": 0, "referenced": 0})
            self.assertEqual(delete.call_count, 1)
        self.assertFalse(PendingFileDeletion.objects.exists())
