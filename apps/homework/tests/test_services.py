"""Tests for HomeworkService business logic."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.homework.models import (
    HomeworkAssignment,
    HomeworkSkillTag,
    HomeworkSubmission,
    HomeworkTemplate,
)
from apps.homework.services import HomeworkError, HomeworkService
from apps.payments.models import PaymentLedger
from apps.projects.models import User
from apps.rewards.models import CoinLedger


def _make_image(name="proof.jpg"):
    return SimpleUploadedFile(name, b"\xff\xd8\xff\xe0" + b"\x00" * 100, content_type="image/jpeg")


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="child", password="pw", role="child",
        )
        self.tomorrow = timezone.localdate() + timedelta(days=1)
        self.yesterday = timezone.localdate() - timedelta(days=1)


class TimelinessTests(_Fixture):
    def test_early_submission(self):
        due = timezone.localdate() + timedelta(days=3)
        self.assertEqual(HomeworkService.get_timeliness(due), "early")

    def test_on_time_submission(self):
        due = timezone.localdate()
        self.assertEqual(HomeworkService.get_timeliness(due), "on_time")

    def test_late_submission(self):
        due = timezone.localdate() - timedelta(days=1)
        self.assertEqual(HomeworkService.get_timeliness(due), "late")

    def test_beyond_cutoff(self):
        due = timezone.localdate() - timedelta(days=5)
        self.assertEqual(HomeworkService.get_timeliness(due), "beyond_cutoff")


class CreateAssignmentTests(_Fixture):
    def test_parent_creates_assignment(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            assignment = HomeworkService.create_assignment(self.parent, {
                "title": "Read Chapter 5",
                "subject": "reading",
                "effort_level": 2,
                "due_date": self.tomorrow,
                "assigned_to": self.child,
            })
        self.assertEqual(assignment.title, "Read Chapter 5")
        self.assertEqual(assignment.assigned_to, self.child)
        self.assertEqual(assignment.created_by, self.parent)
        # Creating fires the homework_created RPG trigger.
        gl.assert_called_once()
        args = gl.call_args
        self.assertEqual(args.args[0], self.child)
        self.assertEqual(args.args[1], "homework_created")

    def test_child_creates_assignment_auto_assigns_self(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            assignment = HomeworkService.create_assignment(self.child, {
                "title": "Math worksheet",
                "subject": "math",
                "effort_level": 3,
                "due_date": self.tomorrow,
            })
        self.assertEqual(assignment.assigned_to, self.child)
        # Children CAN set their own effort — it only weights XP, not pay.
        self.assertEqual(assignment.effort_level, 3)

    def test_past_due_date_raises(self):
        with self.assertRaises(HomeworkError):
            HomeworkService.create_assignment(self.parent, {
                "title": "Late",
                "subject": "other",
                "effort_level": 1,
                "due_date": self.yesterday,
                "assigned_to": self.child,
            })

    def test_skill_tags_created(self):
        from apps.achievements.models import Skill, Subject
        from apps.achievements.models import SkillCategory

        cat = SkillCategory.objects.create(name="Academics")
        subj = Subject.objects.create(name="Math", category=cat)
        skill = Skill.objects.create(name="Algebra", subject=subj, category=cat)

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            assignment = HomeworkService.create_assignment(self.parent, {
                "title": "Algebra HW",
                "subject": "math",
                "effort_level": 3,
                "due_date": self.tomorrow,
                "assigned_to": self.child,
                "skill_tags": [{"skill_id": skill.id, "xp_amount": 20}],
            })
        self.assertEqual(assignment.skill_tags.count(), 1)
        tag = assignment.skill_tags.first()
        self.assertEqual(tag.skill, skill)
        self.assertEqual(tag.xp_amount, 20)

    def test_child_skill_tags_ignored(self):
        """Children can't route XP to skills — that's a parent concern."""
        from apps.achievements.models import Skill, SkillCategory, Subject

        cat = SkillCategory.objects.create(name="Academics")
        subj = Subject.objects.create(name="Reading", category=cat)
        skill = Skill.objects.create(name="Comprehension", subject=subj, category=cat)

        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            assignment = HomeworkService.create_assignment(self.child, {
                "title": "Self HW",
                "subject": "reading",
                "due_date": self.tomorrow,
                "skill_tags": [{"skill_id": skill.id, "xp_amount": 50}],
            })
        self.assertEqual(assignment.skill_tags.count(), 0)

    def test_game_loop_fires_only_for_first_create_today(self):
        """2026-04-23 anti-farm tightening: subsequent same-day creates skip
        the entire game loop call, not just the drop roll. Pre-fix the loop
        ran every time with ``drops_allowed=False``, which still farmed
        quest progress (Scholar's Week, Summer Reading List). Post-fix the
        loop only fires for the first create per local day per child.
        """
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            HomeworkService.create_assignment(self.parent, {
                "title": "A",
                "subject": "math",
                "effort_level": 2,
                "due_date": self.tomorrow,
                "assigned_to": self.child,
            })
            HomeworkService.create_assignment(self.parent, {
                "title": "B",
                "subject": "math",
                "effort_level": 2,
                "due_date": self.tomorrow,
                "assigned_to": self.child,
            })
            HomeworkService.create_assignment(self.parent, {
                "title": "C",
                "subject": "math",
                "effort_level": 2,
                "due_date": self.tomorrow,
                "assigned_to": self.child,
            })
        self.assertEqual(gl.call_count, 1)
        first_ctx = gl.call_args_list[0].args[2]
        self.assertTrue(first_ctx.get("drops_allowed"))

    def test_create_then_delete_then_create_still_skips_second_loop(self):
        """Soft-deleted assignments still count toward the daily cap, so a
        parent-cooperated create→delete→create cycle on the same day can't
        re-arm the loop. This is the load-bearing anti-farm property: the
        DB query in create_assignment doesn't filter on ``is_active``.
        """
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            first = HomeworkService.create_assignment(self.parent, {
                "title": "A",
                "subject": "math",
                "effort_level": 2,
                "due_date": self.tomorrow,
                "assigned_to": self.child,
            })
            # Soft-delete, mirroring HomeworkAssignmentViewSet.perform_destroy.
            first.is_active = False
            first.save(update_fields=["is_active"])

            HomeworkService.create_assignment(self.parent, {
                "title": "B",
                "subject": "math",
                "effort_level": 2,
                "due_date": self.tomorrow,
                "assigned_to": self.child,
            })
        self.assertEqual(gl.call_count, 1)


class SubmitCompletionTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.assignment = HomeworkAssignment.objects.create(
            title="Math HW",
            subject="math",
            effort_level=3,
            due_date=self.tomorrow,
            assigned_to=self.child,
            created_by=self.parent,
        )

    def test_submit_with_images(self):
        images = [_make_image("page1.jpg"), _make_image("page2.jpg")]
        submission = HomeworkService.submit_completion(
            self.child, self.assignment, images, "Done!",
        )
        self.assertEqual(submission.status, "pending")
        self.assertEqual(submission.proofs.count(), 2)
        self.assertEqual(submission.timeliness, "early")

    def test_submit_without_images_raises(self):
        with self.assertRaises(HomeworkError):
            HomeworkService.submit_completion(self.child, self.assignment, [], "")

    def test_parent_cannot_submit(self):
        with self.assertRaises(HomeworkError):
            HomeworkService.submit_completion(
                self.parent, self.assignment, [_make_image()], "",
            )

    def test_duplicate_submission_raises(self):
        HomeworkService.submit_completion(
            self.child, self.assignment, [_make_image()], "",
        )
        with self.assertRaises(HomeworkError):
            HomeworkService.submit_completion(
                self.child, self.assignment, [_make_image()], "",
            )

    def test_rejected_allows_resubmit(self):
        sub = HomeworkService.submit_completion(
            self.child, self.assignment, [_make_image()], "",
        )
        HomeworkService.reject_submission(sub, self.parent)
        # Should not raise.
        sub2 = HomeworkService.submit_completion(
            self.child, self.assignment, [_make_image()], "Updated",
        )
        self.assertEqual(sub2.status, "pending")


class ApproveRejectTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.assignment = HomeworkAssignment.objects.create(
            title="Science HW",
            subject="science",
            effort_level=4,
            due_date=self.tomorrow,
            assigned_to=self.child,
            created_by=self.parent,
        )
        self.submission = HomeworkService.submit_completion(
            self.child, self.assignment, [_make_image()], "",
        )

    def test_approve_does_not_post_to_payment_or_coin_ledger(self):
        """Homework no longer pays money or coins on approval.

        The real invariant is that the approval flow creates zero ledger
        rows for the child — the specific ``HOMEWORK_REWARD`` enum value is
        gone, so we check the full absence rather than a single entry type.
        """
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            HomeworkService.approve_submission(self.submission, self.parent)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "approved")
        self.assertEqual(
            PaymentLedger.objects.filter(user=self.child).count(), 0,
        )
        self.assertEqual(
            CoinLedger.objects.filter(user=self.child).count(), 0,
        )

    def test_approve_fires_homework_complete_trigger_with_on_time(self):
        with patch("apps.rpg.services.GameLoopService.on_task_completed") as gl:
            HomeworkService.approve_submission(self.submission, self.parent)
        gl.assert_called_once()
        args = gl.call_args
        self.assertEqual(args.args[1], "homework_complete")
        self.assertTrue(args.args[2]["on_time"])

    def test_reject_no_ledger_entries(self):
        HomeworkService.reject_submission(self.submission, self.parent)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "rejected")
        self.assertEqual(
            PaymentLedger.objects.filter(user=self.child).count(), 0,
        )


class TemplateTests(_Fixture):
    def test_save_and_create_from_template(self):
        assignment = HomeworkAssignment.objects.create(
            title="Weekly Reading",
            subject="reading",
            effort_level=2,
            due_date=self.tomorrow,
            assigned_to=self.child,
            created_by=self.parent,
        )
        template = HomeworkService.save_as_template(assignment, self.parent)
        self.assertEqual(template.title, "Weekly Reading")

        new_due = timezone.localdate() + timedelta(days=7)
        new_assignment = HomeworkService.create_from_template(
            template, self.child, new_due,
        )
        self.assertEqual(new_assignment.title, "Weekly Reading")
        self.assertEqual(new_assignment.due_date, new_due)
        self.assertEqual(new_assignment.assigned_to, self.child)
