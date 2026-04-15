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
from apps.notifications.models import NotificationType
from apps.notifications.services import get_display_name, notify, notify_parents
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
                notification_type=NotificationType.HOMEWORK_CREATED,
                link="/homework",
            )
        else:
            notify(
                assignment.assigned_to,
                title=f"New homework assigned: {assignment.title}",
                message=f"You have new homework: \"{assignment.title}\" due {assignment.due_date}.",
                notification_type=NotificationType.HOMEWORK_CREATED,
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
            notification_type=NotificationType.HOMEWORK_SUBMITTED,
            link="/homework",
        )

        return submission

    # ------------------------------------------------------------------
    # Approval / Rejection
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def approve_submission(submission, parent, notes=""):
        """Parent approves. Posts to PaymentLedger + CoinLedger + XP + badges.

        ``notes`` is accepted for uniform signature with other approval
        services; HomeworkSubmission has no parent_notes field so the value
        is silently dropped by ``finalize_decision``.
        """
        if submission.status != HomeworkSubmission.Status.PENDING:
            return submission

        finalize_decision(submission, HomeworkSubmission.Status.APPROVED, parent, notes)

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
            notification_type=NotificationType.HOMEWORK_APPROVED,
            link="/homework",
        )

        # RPG game loop (streaks, drops, quest progress).
        from apps.rpg.services import GameLoopService
        GameLoopService.on_task_completed(
            submission.user, "homework_complete", {"assignment_id": assignment.id},
        )

        return submission

    @staticmethod
    @transaction.atomic
    def reject_submission(submission, parent, notes=""):
        """Parent rejects. No ledger entries. Child can re-submit.

        ``notes`` is accepted for uniform signature; see ``approve_submission``.
        """
        if submission.status != HomeworkSubmission.Status.PENDING:
            return submission

        finalize_decision(submission, HomeworkSubmission.Status.REJECTED, parent, notes)

        notify(
            submission.user,
            title=f"Homework rejected: {submission.assignment.title}",
            message=(
                f'Your homework "{submission.assignment.title}" was not approved. '
                f"You can re-submit with updated proof."
            ),
            notification_type=NotificationType.HOMEWORK_REJECTED,
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
            notification_type=NotificationType.HOMEWORK_CREATED,
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

    # ------------------------------------------------------------------
    # AI planning — generate a linked Project via Claude
    # ------------------------------------------------------------------
    _PLAN_PROMPT = (
        "You are helping break a homework assignment into a kid-friendly "
        "multi-step project so a child can work through it and check off "
        "progress. Return ONLY a JSON object with this shape:\n"
        '{\n'
        '  "title": "short project title (<= 80 chars)",\n'
        '  "description": "1-2 sentence plain-English summary for a kid",\n'
        '  "difficulty": 1-5 integer (1 easiest, 5 hardest),\n'
        '  "milestones": [ {"title": "chapter title", "description": "1-2 sentences"}, ... ],\n'
        '  "steps": [ {"title": "short \'do this next\' (<= 60 chars)", "description": "1-3 kid-friendly sentences", "milestone_index": 0-based index into milestones or null} ],\n'
        '  "materials": [ {"name": "string", "description": "string", "estimated_cost": number-or-null} ]\n'
        "}\n\n"
        "Rules:\n"
        "- 2-5 milestones, 4-12 steps total.\n"
        "- Every step should belong to a milestone (milestone_index non-null) when possible.\n"
        "- Keep language warm and encouraging; avoid jargon.\n"
        "- Only include materials the child actually needs.\n"
        "- Difficulty should reflect the homework effort_level if sensible.\n\n"
        "Homework assignment:\n"
        "Title: {title}\n"
        "Subject: {subject}\n"
        "Effort level (1-5): {effort_level}\n"
        "Due date: {due_date}\n"
        "Description: {description}\n"
    )

    @staticmethod
    @transaction.atomic
    def plan_assignment(assignment, parent):
        """Use Claude + project model to generate a multi-step Project for a homework assignment.

        Raises HomeworkError if:
        - the assignment already has a linked project,
        - ANTHROPIC_API_KEY is not configured, or
        - the Claude call / JSON parse fails.
        """
        from apps.projects.models import (
            MaterialItem,
            Project,
            ProjectMilestone,
            ProjectStep,
        )

        if assignment.project_id:
            raise HomeworkError("This assignment already has a linked project.")

        api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
        if not api_key:
            raise HomeworkError("AI planning is not configured (ANTHROPIC_API_KEY missing).")

        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise HomeworkError("AI planning requires the 'anthropic' package.") from exc

        prompt = HomeworkService._PLAN_PROMPT.format(
            title=assignment.title,
            subject=assignment.get_subject_display(),
            effort_level=assignment.effort_level,
            due_date=assignment.due_date.isoformat(),
            description=(assignment.description or "(none)")[:4000],
        )

        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=getattr(settings, "CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text = (message.content[0].text or "").strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:].strip()
            import json as _json
            spec = _json.loads(text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Homework AI planning failed for assignment %s", assignment.pk)
            raise HomeworkError(f"AI planning failed: {exc}") from exc

        if not isinstance(spec, dict):
            raise HomeworkError("AI planner returned a non-object response.")

        # Build the project.
        project = Project.objects.create(
            title=str(spec.get("title") or assignment.title)[:200],
            description=str(spec.get("description") or "")[:4000],
            difficulty=max(1, min(5, int(spec.get("difficulty") or assignment.effort_level))),
            status=Project.Status.IN_PROGRESS,
            assigned_to=assignment.assigned_to,
            created_by=parent,
            payment_kind=Project.PaymentKind.REQUIRED,
        )

        # Milestones (kept ordered by list position).
        milestone_rows = []
        for idx, ms in enumerate(spec.get("milestones") or []):
            if not isinstance(ms, dict):
                continue
            milestone_rows.append(
                ProjectMilestone.objects.create(
                    project=project,
                    title=str(ms.get("title") or f"Phase {idx + 1}")[:200],
                    description=str(ms.get("description") or "")[:4000],
                    order=idx,
                )
            )

        # Steps — attach to milestone by index when provided.
        for idx, st in enumerate(spec.get("steps") or []):
            if not isinstance(st, dict):
                continue
            ms_index = st.get("milestone_index")
            milestone = None
            if isinstance(ms_index, int) and 0 <= ms_index < len(milestone_rows):
                milestone = milestone_rows[ms_index]
            ProjectStep.objects.create(
                project=project,
                milestone=milestone,
                title=str(st.get("title") or f"Step {idx + 1}")[:200],
                description=str(st.get("description") or "")[:4000],
                order=idx,
            )

        # Materials — optional.
        for mat in spec.get("materials") or []:
            if not isinstance(mat, dict):
                continue
            cost = mat.get("estimated_cost")
            try:
                cost_dec = Decimal(str(cost)) if cost is not None else Decimal("0.00")
            except Exception:  # noqa: BLE001
                cost_dec = Decimal("0.00")
            MaterialItem.objects.create(
                project=project,
                name=str(mat.get("name") or "Material")[:200],
                description=str(mat.get("description") or "")[:4000],
                estimated_cost=cost_dec,
            )

        assignment.project = project
        assignment.save(update_fields=["project"])

        notify(
            assignment.assigned_to,
            title=f"Project planned: {project.title}",
            message=(
                f'Your homework "{assignment.title}" has been planned out as a '
                f'project with {len(milestone_rows)} phases.'
            ),
            notification_type=NotificationType.HOMEWORK_CREATED,
            link=f"/quests/ventures/{project.pk}",
        )

        return assignment

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
