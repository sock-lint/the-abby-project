"""Tests for HomeworkService business logic."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
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
        label, mult = HomeworkService.get_timeliness(due)
        self.assertEqual(label, "early")
        self.assertEqual(mult, Decimal("1.25"))

    def test_on_time_submission(self):
        due = timezone.localdate()
        label, mult = HomeworkService.get_timeliness(due)
        self.assertEqual(label, "on_time")
        self.assertEqual(mult, Decimal("1.0"))

    def test_late_submission(self):
        due = timezone.localdate() - timedelta(days=1)
        label, mult = HomeworkService.get_timeliness(due)
        self.assertEqual(label, "late")
        self.assertEqual(mult, Decimal("0.5"))

    def test_beyond_cutoff(self):
        due = timezone.localdate() - timedelta(days=5)
        label, mult = HomeworkService.get_timeliness(due)
        self.assertEqual(label, "beyond_cutoff")
        self.assertEqual(mult, Decimal("0"))


class RewardComputationTests(_Fixture):
    def test_effort_scaling(self):
        result = HomeworkService.compute_reward(
            Decimal("10.00"), 5, Decimal("1.0"),
        )
        self.assertEqual(result, Decimal("20.00"))

    def test_timeliness_scaling(self):
        result = HomeworkService.compute_reward(
            Decimal("10.00"), 3, Decimal("1.25"),
        )
        self.assertEqual(result, Decimal("12.50"))

    def test_combined_scaling(self):
        # effort=5 (2.0x) × timeliness=early (1.25x) × base $10 = $25
        result = HomeworkService.compute_reward(
            Decimal("10.00"), 5, Decimal("1.25"),
        )
        self.assertEqual(result, Decimal("25.00"))


class CreateAssignmentTests(_Fixture):
    def test_parent_creates_assignment(self):
        assignment = HomeworkService.create_assignment(self.parent, {
            "title": "Read Chapter 5",
            "subject": "reading",
            "effort_level": 2,
            "due_date": self.tomorrow,
            "assigned_to": self.child,
            "reward_amount": Decimal("5.00"),
            "coin_reward": 10,
        })
        self.assertEqual(assignment.title, "Read Chapter 5")
        self.assertEqual(assignment.assigned_to, self.child)
        self.assertEqual(assignment.created_by, self.parent)

    def test_child_creates_assignment_auto_assigns_self(self):
        assignment = HomeworkService.create_assignment(self.child, {
            "title": "Math worksheet",
            "subject": "math",
            "effort_level": 3,
            "due_date": self.tomorrow,
            "reward_amount": Decimal("0"),
            "coin_reward": 0,
        })
        self.assertEqual(assignment.assigned_to, self.child)

    def test_past_due_date_raises(self):
        with self.assertRaises(HomeworkError):
            HomeworkService.create_assignment(self.parent, {
                "title": "Late",
                "subject": "other",
                "effort_level": 1,
                "due_date": self.yesterday,
                "assigned_to": self.child,
                "reward_amount": Decimal("0"),
                "coin_reward": 0,
            })

    def test_skill_tags_created(self):
        from apps.achievements.models import Skill, Subject
        from apps.achievements.models import SkillCategory

        cat = SkillCategory.objects.create(name="Academics")
        subj = Subject.objects.create(name="Math", category=cat)
        skill = Skill.objects.create(name="Algebra", subject=subj, category=cat)

        assignment = HomeworkService.create_assignment(self.parent, {
            "title": "Algebra HW",
            "subject": "math",
            "effort_level": 3,
            "due_date": self.tomorrow,
            "assigned_to": self.child,
            "reward_amount": Decimal("5.00"),
            "coin_reward": 10,
            "skill_tags": [{"skill_id": skill.id, "xp_amount": 20}],
        })
        self.assertEqual(assignment.skill_tags.count(), 1)
        tag = assignment.skill_tags.first()
        self.assertEqual(tag.skill, skill)
        self.assertEqual(tag.xp_amount, 20)


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
            reward_amount=Decimal("10.00"),
            coin_reward=20,
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
            reward_amount=Decimal("10.00"),
            coin_reward=20,
        )
        self.submission = HomeworkService.submit_completion(
            self.child, self.assignment, [_make_image()], "",
        )

    def test_approve_posts_to_ledgers(self):
        HomeworkService.approve_submission(self.submission, self.parent)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "approved")

        # Payment ledger entry created.
        self.assertTrue(
            PaymentLedger.objects.filter(
                user=self.child,
                entry_type=PaymentLedger.EntryType.HOMEWORK_REWARD,
            ).exists(),
        )
        # Coin ledger entry created.
        self.assertTrue(
            CoinLedger.objects.filter(
                user=self.child,
                reason=CoinLedger.Reason.HOMEWORK_REWARD,
            ).exists(),
        )

    def test_reject_no_ledger_entries(self):
        HomeworkService.reject_submission(self.submission, self.parent)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "rejected")

        self.assertFalse(
            PaymentLedger.objects.filter(
                user=self.child,
                entry_type=PaymentLedger.EntryType.HOMEWORK_REWARD,
            ).exists(),
        )


class ChildCreateStripsRewardsTests(_Fixture):
    def test_child_create_zeros_rewards_and_flags_pending(self):
        """Client-sent effort/reward/coins are ignored for child creates."""
        assignment = HomeworkService.create_assignment(self.child, {
            "title": "My self-assigned homework",
            "subject": "reading",
            "effort_level": 5,
            "reward_amount": Decimal("100.00"),
            "coin_reward": 999,
            "due_date": self.tomorrow,
        })
        self.assertEqual(assignment.assigned_to, self.child)
        # Defaults restored (field-level defaults: effort=3, $0, 0 coins).
        self.assertEqual(assignment.effort_level, 3)
        self.assertEqual(assignment.reward_amount, Decimal("0.00"))
        self.assertEqual(assignment.coin_reward, 0)
        self.assertTrue(assignment.rewards_pending_review)

    def test_parent_create_keeps_rewards(self):
        assignment = HomeworkService.create_assignment(self.parent, {
            "title": "Parent-set HW",
            "subject": "math",
            "effort_level": 4,
            "reward_amount": Decimal("7.50"),
            "coin_reward": 25,
            "due_date": self.tomorrow,
            "assigned_to": self.child,
        })
        self.assertEqual(assignment.effort_level, 4)
        self.assertEqual(assignment.reward_amount, Decimal("7.50"))
        self.assertEqual(assignment.coin_reward, 25)
        self.assertFalse(assignment.rewards_pending_review)

    def test_child_skill_tags_ignored(self):
        """Children can't route XP to skills — that's a parent concern."""
        from apps.achievements.models import Skill, SkillCategory, Subject

        cat = SkillCategory.objects.create(name="Academics")
        subj = Subject.objects.create(name="Reading", category=cat)
        skill = Skill.objects.create(name="Comprehension", subject=subj, category=cat)

        assignment = HomeworkService.create_assignment(self.child, {
            "title": "Self HW",
            "subject": "reading",
            "due_date": self.tomorrow,
            "skill_tags": [{"skill_id": skill.id, "xp_amount": 50}],
        })
        self.assertEqual(assignment.skill_tags.count(), 0)


class AIEffortEstimationTests(_Fixture):
    def setUp(self):
        super().setUp()
        # Child-authored assignment with rewards_pending_review=True.
        self.assignment = HomeworkService.create_assignment(self.child, {
            "title": "My reading",
            "subject": "reading",
            "due_date": self.tomorrow,
        })
        self.assertTrue(self.assignment.rewards_pending_review)

    def test_submit_calls_ai_and_applies_base_rewards(self):
        with patch("apps.homework.ai.estimate_effort_from_proof", return_value=4) as mock_ai:
            submission = HomeworkService.submit_completion(
                self.child, self.assignment, [_make_image()], "",
            )
        mock_ai.assert_called_once()
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.rewards_pending_review)
        self.assertEqual(self.assignment.effort_level, 4)
        # Base reward: $1.00, base coins: 5 (see config/settings.py).
        self.assertEqual(self.assignment.reward_amount, Decimal("1.00"))
        self.assertEqual(self.assignment.coin_reward, 5)
        # Snapshot: $1 × effort_mult(4)=1.5 × timeliness(early=1.25) = $1.875
        self.assertEqual(
            submission.reward_amount_snapshot, Decimal("1.8750"),
        )

    def test_submit_ai_failure_leaves_zero_snapshot(self):
        with patch(
            "apps.homework.ai.estimate_effort_from_proof",
            side_effect=RuntimeError("no api key"),
        ):
            submission = HomeworkService.submit_completion(
                self.child, self.assignment, [_make_image()], "",
            )
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.rewards_pending_review)
        self.assertEqual(submission.reward_amount_snapshot, Decimal("0.00"))
        self.assertEqual(submission.coin_reward_snapshot, 0)

    def test_parent_created_assignment_skips_ai(self):
        """AI should NOT run when parent already set effort/reward/coins."""
        parent_hw = HomeworkAssignment.objects.create(
            title="Parent HW",
            subject="math",
            effort_level=3,
            due_date=self.tomorrow,
            assigned_to=self.child,
            created_by=self.parent,
            reward_amount=Decimal("10.00"),
            coin_reward=20,
            rewards_pending_review=False,
        )
        with patch("apps.homework.ai.estimate_effort_from_proof") as mock_ai:
            HomeworkService.submit_completion(
                self.child, parent_hw, [_make_image()], "",
            )
        mock_ai.assert_not_called()


class AdjustSubmissionTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.assignment = HomeworkService.create_assignment(self.child, {
            "title": "Child HW",
            "subject": "writing",
            "due_date": self.tomorrow,
        })
        # Submit without AI (AI fails, zero snapshot).
        with patch(
            "apps.homework.ai.estimate_effort_from_proof",
            side_effect=RuntimeError("disabled"),
        ):
            self.submission = HomeworkService.submit_completion(
                self.child, self.assignment, [_make_image()], "",
            )

    def test_adjust_recomputes_snapshot(self):
        updated = HomeworkService.adjust_submission(
            self.submission, self.parent,
            effort_level=5, reward_amount="2.00", coin_reward=10,
        )
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.rewards_pending_review)
        self.assertEqual(self.assignment.effort_level, 5)
        self.assertEqual(self.assignment.reward_amount, Decimal("2.00"))
        self.assertEqual(self.assignment.coin_reward, 10)
        # Snapshot: $2 × effort_mult(5)=2.0 × timeliness(early=1.25) = $5.00
        self.assertEqual(updated.reward_amount_snapshot, Decimal("5.00"))
        # Coins: 10 × 2.0 × 1.25 = 25
        self.assertEqual(updated.coin_reward_snapshot, 25)

    def test_adjust_rejects_non_pending(self):
        HomeworkService.reject_submission(self.submission, self.parent)
        with self.assertRaises(HomeworkError):
            HomeworkService.adjust_submission(
                self.submission, self.parent,
                effort_level=3, reward_amount="1", coin_reward=1,
            )

    def test_adjust_validates_effort_range(self):
        with self.assertRaises(HomeworkError):
            HomeworkService.adjust_submission(
                self.submission, self.parent,
                effort_level=6, reward_amount="1", coin_reward=1,
            )
        with self.assertRaises(HomeworkError):
            HomeworkService.adjust_submission(
                self.submission, self.parent,
                effort_level=0, reward_amount="1", coin_reward=1,
            )

    def test_adjust_rejects_negative_reward(self):
        with self.assertRaises(HomeworkError):
            HomeworkService.adjust_submission(
                self.submission, self.parent,
                effort_level=3, reward_amount="-1", coin_reward=1,
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
            reward_amount=Decimal("3.00"),
            coin_reward=5,
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
