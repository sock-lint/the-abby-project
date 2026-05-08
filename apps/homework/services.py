import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.achievements.services import AwardService, BadgeService
from apps.notifications.models import NotificationType
from apps.notifications.services import get_display_name, notify, notify_parents
from config.services import bump_daily_counter, finalize_decision

from .models import (
    HomeworkAssignment,
    HomeworkDailyCounter,
    HomeworkProof,
    HomeworkSkillTag,
    HomeworkSubmission,
    HomeworkTemplate,
)

logger = logging.getLogger(__name__)


@dataclass
class _HomeworkXpTag:
    """Duck-type shim so HomeworkSkillTag rows fit AwardService.grant.

    AwardService distributes a pool by ``xp_weight``; HomeworkSkillTag stores
    a fixed ``xp_amount`` per tag. Setting weight=amount and pool=sum(amounts)
    yields the same per-skill totals (see ``approve_submission``).
    """

    skill: object
    xp_weight: int


class HomeworkError(Exception):
    pass


class HomeworkService:
    # ------------------------------------------------------------------
    # Timeliness helpers
    # ------------------------------------------------------------------
    @staticmethod
    def get_timeliness(due_date, submit_date=None):
        """Return the ``Timeliness`` label for a submission date vs. due date.

        Pure function — no side effects. Homework pays no money and no
        coins, so there's no multiplier to return; the label alone is
        what goes on ``HomeworkSubmission.timeliness`` and gates the
        ``on_time`` quest filter.
        """
        if submit_date is None:
            submit_date = timezone.localdate()

        if submit_date < due_date:
            return HomeworkSubmission.Timeliness.EARLY
        if submit_date == due_date:
            return HomeworkSubmission.Timeliness.ON_TIME
        days_late = (submit_date - due_date).days
        if days_late > settings.HOMEWORK_LATE_CUTOFF_DAYS:
            return HomeworkSubmission.Timeliness.BEYOND_CUTOFF
        return HomeworkSubmission.Timeliness.LATE

    # ------------------------------------------------------------------
    # Assignment CRUD
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_assignment(user, data):
        """Create a homework assignment.

        Immediately active — no approval needed for creation. Homework no
        longer pays money or coins; effort is just an XP-weighting hint.
        Children may set their own effort; skill tags remain parent-only
        because XP routing is a parent decision.

        On successful creation, fires the RPG ``homework_created`` game
        loop for the assigned child — always records streak and quest
        progress; caps drop rolls to the first creation per calendar day
        so the loop can't be farmed.
        """
        if user.role == "child":
            data["assigned_to"] = user
            # Skill tags are parent-only (XP routing decision).
            data.pop("skill_tags", None)

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

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="approval",
            event_type="homework.create",
            summary=f"Homework assigned: {assignment.title}",
            actor=user,
            subject=assignment.assigned_to,
            target=assignment,
            breakdown=[
                {"label": "subject", "value": assignment.subject or "—", "op": "note"},
                {"label": "effort", "value": assignment.effort_level, "op": "note"},
                {"label": "due", "value": str(assignment.due_date), "op": "note"},
            ],
            extras={
                "assignment_id": assignment.pk,
                "subject": assignment.subject,
                "effort_level": assignment.effort_level,
                "due_date": str(assignment.due_date),
            },
        )

        # Notify.
        display = get_display_name(user)
        if user.role == "child":
            notify_parents(
                title=f"New homework: {assignment.title}",
                message=f"{display} added homework: \"{assignment.title}\" due {assignment.due_date}.",
                notification_type=NotificationType.HOMEWORK_CREATED,
                link="/homework",
                about_user=user,
            )
        else:
            notify(
                assignment.assigned_to,
                title=f"New homework assigned: {assignment.title}",
                message=f"You have new homework: \"{assignment.title}\" due {assignment.due_date}.",
                notification_type=NotificationType.HOMEWORK_CREATED,
                link="/homework",
            )

        # RPG game loop + planner badge evaluation.
        child = assignment.assigned_to
        if child is not None:
            # Anti-farm: only the FIRST homework_created per child per local
            # day fires the game loop. ``HomeworkDailyCounter`` survives both
            # soft-delete (``is_active=False``) and hard-delete, so a
            # parent-cooperated create→delete→create cycle on the same day
            # still skips the second loop call. Closes:
            #   • drop farming (would already skip via drops_allowed gate)
            #   • streak credit (per-day idempotent — would no-op anyway)
            #   • quest progress farming (Scholar's Week, Summer Reading List
            #     count homework_created — pre-2026-04-23 the Nth create per
            #     day still advanced these quests).
            prior_count = bump_daily_counter(
                HomeworkDailyCounter, child, timezone.localdate(),
            )
            if prior_count == 0:
                from apps.rpg.constants import TriggerType
                from apps.rpg.services import safe_game_loop_call
                safe_game_loop_call(
                    child, TriggerType.HOMEWORK_CREATED,
                    {"assignment_id": assignment.id, "drops_allowed": True},
                )

            # Planner badges depend on the new row existing, so evaluate now.
            # Audit H8: only the planner ladder + meta can flip on create.
            BadgeService.evaluate_badges(child, scopes={"homework_create", "badges"})

        return assignment

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def submit_completion(user, assignment, images, notes=""):
        """Child submits homework with proof images.

        Validates at least 1 image. Records timeliness for later badge
        evaluation. Homework no longer pays money or coins, so there is
        no snapshot to compute and no AI effort estimation — effort
        stays as whatever was set on the assignment and only weights XP
        distribution on approval.
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

        timeliness_label = HomeworkService.get_timeliness(assignment.due_date)

        submission = HomeworkSubmission.objects.create(
            assignment=assignment,
            user=user,
            status=HomeworkSubmission.Status.PENDING,
            notes=notes,
            timeliness=timeliness_label,
        )

        # Create proof records.
        for order, image in enumerate(images):
            HomeworkProof.objects.create(
                submission=submission,
                image=image,
                order=order,
            )

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="approval",
            event_type="homework.submit",
            summary=f"Homework submitted: {assignment.title}",
            actor=user,
            subject=user,
            target=submission,
            breakdown=[
                {"label": "timeliness", "value": timeliness_label, "op": "note"},
                {"label": "proofs", "value": len(images), "op": "note"},
            ],
            extras={
                "assignment_id": assignment.pk,
                "timeliness": timeliness_label,
                "proof_count": len(images),
            },
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
            about_user=user,
        )

        return submission

    # ------------------------------------------------------------------
    # Approval / Rejection
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def approve_submission(submission, parent, notes=""):
        """Parent approves. Awards XP + evaluates badges + fires RPG loop.

        Homework no longer pays money or coins — approval just routes
        XP through skill tags, fires the ``homework_complete`` RPG trigger
        (drop rolls, streak, quest progress), and re-evaluates badges.

        ``notes`` is accepted for uniform signature with other approval
        services; HomeworkSubmission has no parent_notes field so the value
        is silently dropped by ``finalize_decision``.
        """
        # Race guard: two parents tapping "approve" within ms of each
        # other would each see ``status == PENDING`` and double-fire the
        # XP grant + RPG game loop. Re-fetch under a row lock so the
        # status check + state transition are serialized.
        submission = HomeworkSubmission.objects.select_for_update().get(
            pk=submission.pk,
        )
        if submission.status != HomeworkSubmission.Status.PENDING:
            return submission

        finalize_decision(
            # HomeworkSubmission has no ``parent_notes`` field — the
            # caller's note is preserved on the activity-log row instead
            # so the audit trail still has it.
            submission, HomeworkSubmission.Status.APPROVED, parent, "",
            activity_category="approval",
            activity_event_type="homework.approve",
            activity_summary=f"Homework approved: {submission.assignment.title}",
            activity_subject=submission.user,
            activity_extras={
                "assignment_id": submission.assignment_id,
                "timeliness": submission.timeliness,
                "parent_notes": notes or None,
            },
        )

        assignment = submission.assignment

        # Distribute XP via HomeworkSkillTags through the unified award path.
        # ``HomeworkSkillTag.xp_amount`` is fixed-per-tag, but
        # ``AwardService.grant`` distributes a pool by ``xp_weight``. Using
        # ``xp_weight = xp_amount`` and ``xp = sum(amounts)`` is mathematically
        # identical (each tag's share is ``total * weight/sum_of_weights``,
        # which collapses back to ``xp_amount``) while routing through the
        # same XP-boost-aware pipeline that chores / projects / quests use.
        # Going through AwardService also re-evaluates badges, so the
        # explicit BadgeService.evaluate_badges call that used to live here
        # is no longer needed.
        homework_tags = list(assignment.skill_tags.select_related("skill"))
        total_xp = sum(tag.xp_amount for tag in homework_tags)
        if total_xp > 0:
            shim_tags = [
                _HomeworkXpTag(skill=tag.skill, xp_weight=tag.xp_amount)
                for tag in homework_tags
            ]
            AwardService.grant(
                submission.user,
                xp_tags=shim_tags,
                xp=total_xp,
                xp_source_label=f"Homework: {assignment.title}",
                created_by=parent,
                # Audit H8: homework approval moves on-time counters,
                # skill XP, and the BADGES_EARNED meta. No coin/money.
                badge_scopes={"homework_complete", "skill_xp", "badges"},
            )
        else:
            # No skill tags → still re-evaluate badges so on_time counters tick.
            BadgeService.evaluate_badges(
                submission.user,
                created_by=parent,
                scopes={"homework_complete", "badges"},
            )

        # Notify child.
        notify(
            submission.user,
            title=f"Homework approved: {assignment.title}",
            message=(
                f'Your homework "{assignment.title}" was approved! '
                f"Great work — you earned XP toward your skills."
            ),
            notification_type=NotificationType.HOMEWORK_APPROVED,
            link="/homework",
        )

        # RPG game loop (streaks, drops, quest progress). Pass on_time so
        # quests with ``trigger_filter.on_time=true`` can count only
        # early/on-time submissions.
        on_time = submission.timeliness in (
            HomeworkSubmission.Timeliness.EARLY,
            HomeworkSubmission.Timeliness.ON_TIME,
        )
        from apps.rpg.constants import TriggerType
        from apps.rpg.services import safe_game_loop_call
        safe_game_loop_call(
            submission.user, TriggerType.HOMEWORK_COMPLETE,
            {"assignment_id": assignment.id, "on_time": on_time},
        )

        return submission

    @staticmethod
    @transaction.atomic
    def reject_submission(submission, parent, notes=""):
        """Parent rejects. No ledger entries. Child can re-submit.

        ``notes`` is accepted for uniform signature; see ``approve_submission``.
        """
        # Race guard mirrors approve_submission — without the lock, an
        # approve + reject racing on the same row could both succeed.
        submission = HomeworkSubmission.objects.select_for_update().get(
            pk=submission.pk,
        )
        if submission.status != HomeworkSubmission.Status.PENDING:
            return submission

        finalize_decision(
            submission, HomeworkSubmission.Status.REJECTED, parent, "",
            activity_category="approval",
            activity_event_type="homework.reject",
            activity_summary=f"Homework rejected: {submission.assignment.title}",
            activity_subject=submission.user,
            activity_extras={
                "assignment_id": submission.assignment_id,
                "parent_notes": notes or None,
            },
        )

        body = (
            f'Your homework "{submission.assignment.title}" was not approved. '
            f"You can re-submit with updated proof."
        )
        if notes:
            body = f'{body}\n\nNote from your parent: "{notes.strip()}"'
        notify(
            submission.user,
            title=f"Homework rejected: {submission.assignment.title}",
            message=body,
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
    # NOTE: this template is rendered via ``str.format(...)`` below, so every
    # literal ``{`` / ``}`` in the JSON example block is doubled (``{{`` /
    # ``}}``) to escape it. Only the actual placeholders at the bottom
    # (``{title}``, ``{subject}``, ``{effort_level}``, ``{due_date}``,
    # ``{description}``) use single braces. Adding a new literal-JSON example
    # here? Double the braces, or you'll get a KeyError at format time.
    _PLAN_PROMPT = (
        "You are helping break a homework assignment into a kid-friendly "
        "multi-step project so a child can work through it and check off "
        "progress. Return ONLY a JSON object with this shape:\n"
        '{{\n'
        '  "title": "short project title (<= 80 chars)",\n'
        '  "description": "1-2 sentence plain-English summary for a kid",\n'
        '  "difficulty": 1-5 integer (1 easiest, 5 hardest),\n'
        '  "milestones": [ {{"title": "chapter title", "description": "1-2 sentences"}}, ... ],\n'
        '  "steps": [ {{"title": "short \'do this next\' (<= 60 chars)", "description": "1-3 kid-friendly sentences", "milestone_index": 0-based index into milestones or null}} ],\n'
        '  "materials": [ {{"name": "string", "description": "string", "estimated_cost": number-or-null}} ]\n'
        "}}\n\n"
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
    def can_self_plan(user, assignment) -> bool:
        """Whether ``user`` may trigger ``plan_assignment`` on ``assignment``.

        Parents always can. Children can self-trigger only on their own
        assignments, only when the due date is at least
        ``settings.HOMEWORK_SELF_PLAN_LEAD_DAYS`` days out — the
        "planning ahead" virtue rule. Short-lead / urgent assignments stay
        parent-only on purpose: the conversation matters more than the AI
        plan when a child has waited too long.
        """
        if assignment.project_id is not None:
            return False
        if user.role == "parent":
            return True
        if assignment.assigned_to_id != user.id:
            return False
        lead_days = (assignment.due_date - timezone.localdate()).days
        return lead_days >= settings.HOMEWORK_SELF_PLAN_LEAD_DAYS

    @staticmethod
    @transaction.atomic
    def plan_assignment(assignment, parent):
        """Use an LLM to generate a multi-step Project for a homework assignment.

        Raises HomeworkError if:
        - the assignment already has a linked project,
        - no LLM backend is configured (see :mod:`config.llm`), or
        - the LLM call / JSON parse fails.
        """
        from apps.projects.models import (
            MaterialItem,
            Project,
            ProjectMilestone,
            ProjectStep,
        )
        from config.llm import LLMError, LLMUnavailable, complete_json

        if assignment.project_id:
            raise HomeworkError("This assignment already has a linked project.")

        prompt = HomeworkService._PLAN_PROMPT.format(
            title=assignment.title,
            subject=assignment.get_subject_display(),
            effort_level=assignment.effort_level,
            due_date=assignment.due_date.isoformat(),
            description=(assignment.description or "(none)")[:4000],
        )

        try:
            spec = complete_json(prompt=prompt, max_tokens=2048)
        except LLMUnavailable as exc:
            raise HomeworkError("AI planning is not configured.") from exc
        except LLMError as exc:
            logger.warning("Homework AI planning failed for assignment %s: %s", assignment.pk, exc)
            raise HomeworkError(f"AI planning failed: {exc}") from exc
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
    def get_parent_overview(parent):
        """Return pending submissions + active assignments list for parents.

        Scoped to ``parent.family`` — without this filter a parent in family A
        would see pending homework + assignments from every other family on
        the deployment. Parents manage (edit/delete) assignments from the
        ``assignments`` list — ordered by due date ascending so overdue floats
        to the top.
        """
        family = parent.family
        pending = (
            HomeworkSubmission.objects
            .filter(
                status=HomeworkSubmission.Status.PENDING,
                user__family=family,
            )
            .select_related("assignment", "user")
            .prefetch_related("proofs")
            .order_by("created_at")
        )
        assignments = (
            HomeworkAssignment.objects
            .filter(is_active=True, assigned_to__family=family)
            .select_related("assigned_to", "created_by")
            .prefetch_related("skill_tags__skill", "submissions")
            .order_by("due_date")
        )
        return {
            "pending_submissions": list(pending),
            "assignments": list(assignments),
        }
