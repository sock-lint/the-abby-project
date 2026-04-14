import logging
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.achievements.services import BadgeService, SkillService
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.models import Notification
from apps.projects.notifications import get_display_name, notify, notify_parents
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from config.services import finalize_decision

from .models import (
    HomeworkAssignment,
    HomeworkProof,
    HomeworkSkillTag,
    HomeworkSubmission,
    HomeworkTemplate,
)

logger = logging.getLogger(__name__)


class HomeworkError(Exception):
    pass


class HomeworkService:
    # ------------------------------------------------------------------
    # Timeliness helpers
    # ------------------------------------------------------------------
    @staticmethod
    def get_timeliness(due_date, submit_date=None):
        """Return (timeliness_label, multiplier) for a given due date.

        Pure function — no side effects.
        """
        if submit_date is None:
            submit_date = timezone.localdate()

        if submit_date < due_date:
            return (
                HomeworkSubmission.Timeliness.EARLY,
                settings.HOMEWORK_EARLY_BONUS,
            )
        elif submit_date == due_date:
            return (
                HomeworkSubmission.Timeliness.ON_TIME,
                settings.HOMEWORK_ON_TIME_MULTIPLIER,
            )
        else:
            days_late = (submit_date - due_date).days
            if days_late > settings.HOMEWORK_LATE_CUTOFF_DAYS:
                return (
                    HomeworkSubmission.Timeliness.BEYOND_CUTOFF,
                    Decimal("0"),
                )
            return (
                HomeworkSubmission.Timeliness.LATE,
                settings.HOMEWORK_LATE_PENALTY,
            )

    @staticmethod
    def compute_reward(base_amount, effort_level, timeliness_multiplier):
        """Compute final reward: base × effort_multiplier × timeliness_multiplier."""
        effort_mult = settings.HOMEWORK_EFFORT_MULTIPLIERS.get(
            effort_level, Decimal("1.0"),
        )
        return base_amount * effort_mult * timeliness_multiplier

    # ------------------------------------------------------------------
    # Assignment CRUD
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_assignment(user, data):
        """Create a homework assignment.

        Immediately active — no approval needed for creation.
        Child-created assignments auto-set assigned_to=self.
        """
        if user.role == "child":
            data["assigned_to"] = user

        due_date = data.get("due_date")
        if due_date and due_date < timezone.localdate():
            raise HomeworkError("Due date must be in the future.")

        skill_tag_data = data.pop("skill_tags", [])

        assignment = HomeworkAssignment.objects.create(
            created_by=user,
            **data,
        )

        for tag in skill_tag_data:
            HomeworkSkillTag.objects.create(
                assignment=assignment,
                skill_id=tag["skill_id"],
                xp_amount=tag.get("xp_amount", 15),
            )

        # Notify.
        display = get_display_name(user)
        if user.role == "child":
            notify_parents(
                title=f"New homework: {assignment.title}",
                message=f"{display} added homework: \"{assignment.title}\" due {assignment.due_date}.",
                notification_type=Notification.NotificationType.HOMEWORK_CREATED,
                link="/homework",
            )
        else:
            notify(
                assignment.assigned_to,
                title=f"New homework assigned: {assignment.title}",
                message=f"You have new homework: \"{assignment.title}\" due {assignment.due_date}.",
                notification_type=Notification.NotificationType.HOMEWORK_CREATED,
                link="/homework",
            )

        return assignment

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def submit_completion(user, assignment, images, notes=""):
        """Child submits homework with proof images.

        Validates at least 1 image. Computes and snapshots rewards.
        """
        if user.role != "child":
            raise HomeworkError("Only children can submit homework.")

        if not assignment.is_active:
            raise HomeworkError("This assignment is no longer active.")

        if assignment.assigned_to != user:
            raise HomeworkError("This assignment is not assigned to you.")

        if not images:
            raise HomeworkError("At least one proof image is required.")

        # Check for existing non-rejected submission.
        if HomeworkSubmission.objects.filter(
            assignment=assignment, user=user,
        ).exclude(status=HomeworkSubmission.Status.REJECTED).exists():
            raise HomeworkError("You already have a pending or approved submission for this assignment.")

        # Compute timeliness and rewards.
        timeliness_label, timeliness_mult = HomeworkService.get_timeliness(
            assignment.due_date,
        )
        reward_amount = HomeworkService.compute_reward(
            assignment.reward_amount, assignment.effort_level, timeliness_mult,
        )
        coin_reward = int(HomeworkService.compute_reward(
            Decimal(str(assignment.coin_reward)), assignment.effort_level, timeliness_mult,
        ))

        submission = HomeworkSubmission.objects.create(
            assignment=assignment,
            user=user,
            status=HomeworkSubmission.Status.PENDING,
            notes=notes,
            reward_amount_snapshot=reward_amount,
            coin_reward_snapshot=coin_reward,
            timeliness=timeliness_label,
            timeliness_multiplier=timeliness_mult,
        )

        # Create proof records.
        for order, image in enumerate(images):
            HomeworkProof.objects.create(
                submission=submission,
                image=image,
                order=order,
            )

        # Notify parents.
        display = get_display_name(user)
        notify_parents(
            title=f"Homework submitted: {assignment.title}",
            message=(
                f'{display} submitted "{assignment.title}" '
                f"({timeliness_label.replace('_', ' ')}) for review."
            ),
            notification_type=Notification.NotificationType.HOMEWORK_SUBMITTED,
            link="/homework",
        )

        return submission

    # ------------------------------------------------------------------
    # Approval / Rejection
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def approve_submission(submission, parent):
        """Parent approves. Posts to PaymentLedger + CoinLedger + XP + badges."""
        if submission.status != HomeworkSubmission.Status.PENDING:
            return submission

        finalize_decision(submission, HomeworkSubmission.Status.APPROVED, parent)

        assignment = submission.assignment

        # Post payment.
        if submission.reward_amount_snapshot > 0:
            PaymentService.record_entry(
                submission.user,
                submission.reward_amount_snapshot,
                PaymentLedger.EntryType.HOMEWORK_REWARD,
                description=f"Homework: {assignment.title}",
                created_by=parent,
            )

        # Award coins.
        if submission.coin_reward_snapshot > 0:
            CoinService.award_coins(
                submission.user,
                submission.coin_reward_snapshot,
                CoinLedger.Reason.HOMEWORK_REWARD,
                description=f"Homework: {assignment.title}",
                created_by=parent,
            )

        # Distribute XP via HomeworkSkillTags.
        for tag in assignment.skill_tags.select_related("skill"):
            SkillService.award_xp(submission.user, tag.skill, tag.xp_amount)

        # Evaluate badges.
        BadgeService.evaluate_badges(submission.user)

        # Notify child.
        notify(
            submission.user,
            title=f"Homework approved: {assignment.title}",
            message=(
                f'Your homework "{assignment.title}" was approved! '
                f"You earned ${submission.reward_amount_snapshot} "
                f"and {submission.coin_reward_snapshot} coins."
            ),
            notification_type=Notification.NotificationType.HOMEWORK_APPROVED,
            link="/homework",
        )

        return submission

    @staticmethod
    @transaction.atomic
    def reject_submission(submission, parent):
        """Parent rejects. No ledger entries. Child can re-submit."""
        if submission.status != HomeworkSubmission.Status.PENDING:
            return submission

        finalize_decision(submission, HomeworkSubmission.Status.REJECTED, parent)

        notify(
            submission.user,
            title=f"Homework rejected: {submission.assignment.title}",
            message=(
                f'Your homework "{submission.assignment.title}" was not approved. '
                f"You can re-submit with updated proof."
            ),
            notification_type=Notification.NotificationType.HOMEWORK_REJECTED,
            link="/homework",
        )

        return submission

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------
    @staticmethod
    def save_as_template(assignment, user):
        """Save an assignment as a reusable template (parent-only)."""
        skill_tag_data = [
            {"skill_id": tag.skill_id, "xp_amount": tag.xp_amount}
            for tag in assignment.skill_tags.all()
        ]
        return HomeworkTemplate.objects.create(
            title=assignment.title,
            description=assignment.description,
            subject=assignment.subject,
            effort_level=assignment.effort_level,
            reward_amount=assignment.reward_amount,
            coin_reward=assignment.coin_reward,
            created_by=user,
            skill_tags=skill_tag_data,
        )

    @staticmethod
    @transaction.atomic
    def create_from_template(template, assigned_to, due_date):
        """Create a new assignment from a template."""
        assignment = HomeworkAssignment.objects.create(
            title=template.title,
            description=template.description,
            subject=template.subject,
            effort_level=template.effort_level,
            reward_amount=template.reward_amount,
            coin_reward=template.coin_reward,
            due_date=due_date,
            assigned_to=assigned_to,
            created_by=template.created_by,
        )
        for tag_data in template.skill_tags:
            HomeworkSkillTag.objects.create(
                assignment=assignment,
                skill_id=tag_data["skill_id"],
                xp_amount=tag_data.get("xp_amount", 15),
            )

        notify(
            assigned_to,
            title=f"New homework assigned: {assignment.title}",
            message=f"You have new homework: \"{assignment.title}\" due {assignment.due_date}.",
            notification_type=Notification.NotificationType.HOMEWORK_CREATED,
            link="/homework",
        )

        return assignment

    # ------------------------------------------------------------------
    # Dashboard queries
    # ------------------------------------------------------------------
    @staticmethod
    def get_child_dashboard(user):
        """Return structured dashboard data for a child."""
        today = timezone.localdate()
        assignments = HomeworkAssignment.objects.filter(
            assigned_to=user, is_active=True,
        ).prefetch_related("submissions")

        todays = []
        upcoming = []
        overdue = []

        for a in assignments:
            active_sub = a.submissions.exclude(
                status=HomeworkSubmission.Status.REJECTED,
            ).first()

            item = {
                "assignment": a,
                "submission": active_sub,
                "status": active_sub.status if active_sub else None,
            }

            if a.due_date < today and not active_sub:
                overdue.append(item)
            elif a.due_date == today:
                todays.append(item)
            elif a.due_date > today:
                upcoming.append(item)

        # Stats.
        approved_count = HomeworkSubmission.objects.filter(
            user=user, status=HomeworkSubmission.Status.APPROVED,
        ).count()
        total_assigned = HomeworkAssignment.objects.filter(
            assigned_to=user, is_active=True,
        ).count()
        on_time_count = HomeworkSubmission.objects.filter(
            user=user,
            status=HomeworkSubmission.Status.APPROVED,
            timeliness__in=[
                HomeworkSubmission.Timeliness.EARLY,
                HomeworkSubmission.Timeliness.ON_TIME,
            ],
        ).count()

        stats = {
            "completion_rate": (
                round(approved_count / total_assigned * 100) if total_assigned else 0
            ),
            "on_time_rate": (
                round(on_time_count / approved_count * 100) if approved_count else 0
            ),
            "total_approved": approved_count,
        }

        return {
            "today": sorted(todays, key=lambda x: -x["assignment"].effort_level),
            "upcoming": sorted(upcoming, key=lambda x: x["assignment"].due_date),
            "overdue": sorted(overdue, key=lambda x: x["assignment"].due_date),
            "stats": stats,
        }

    @staticmethod
    def get_parent_overview():
        """Return pending submissions queue + per-child stats for parents."""
        pending = (
            HomeworkSubmission.objects
            .filter(status=HomeworkSubmission.Status.PENDING)
            .select_related("assignment", "user")
            .prefetch_related("proofs")
            .order_by("created_at")
        )
        return {"pending_submissions": list(pending)}
