"""Homework-related MCP tools."""
from __future__ import annotations

from typing import Any

from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.homework.services import HomeworkError, HomeworkService
from apps.projects.models import User

from ..context import get_current_user, require_parent, resolve_target_user
from ..errors import MCPNotFoundError, safe_tool
from ..schemas import (
    CreateHomeworkIn,
    DecideHomeworkSubmissionIn,
    GetHomeworkIn,
    ListHomeworkIn,
    ListHomeworkSubmissionsIn,
    PlanHomeworkIn,
    SubmitHomeworkIn,
)
from ..server import tool
from ..shapes import homework_assignment_to_dict, homework_submission_to_dict, many


@tool()
@safe_tool
def list_homework(params: ListHomeworkIn) -> dict[str, Any]:
    """List homework assignments. Parents see all; children see their own."""
    user = get_current_user()

    qs = HomeworkAssignment.objects.filter(is_active=True).select_related(
        "assigned_to", "created_by",
    ).prefetch_related("skill_tags__skill", "submissions")

    if user.role == "child":
        qs = qs.filter(assigned_to=user)
    elif params.assigned_to_id:
        qs = qs.filter(assigned_to_id=params.assigned_to_id)

    if params.subject:
        qs = qs.filter(subject=params.subject)

    return {"assignments": many(qs[:params.limit], homework_assignment_to_dict)}


@tool()
@safe_tool
def get_homework(params: GetHomeworkIn) -> dict[str, Any]:
    """Get details for a single homework assignment."""
    get_current_user()
    try:
        assignment = HomeworkAssignment.objects.select_related(
            "assigned_to", "created_by",
        ).prefetch_related(
            "skill_tags__skill", "submissions",
        ).get(pk=params.assignment_id)
    except HomeworkAssignment.DoesNotExist:
        raise MCPNotFoundError(f"Assignment {params.assignment_id} not found.")
    return homework_assignment_to_dict(assignment)


@tool()
@safe_tool
def create_homework(params: CreateHomeworkIn) -> dict[str, Any]:
    """Create a homework assignment. Both parents and children can create."""
    user = get_current_user()

    try:
        child = User.objects.get(pk=params.assigned_to_id, role="child")
    except User.DoesNotExist:
        raise MCPNotFoundError(f"Child {params.assigned_to_id} not found.")

    data = {
        "title": params.title,
        "description": params.description,
        "subject": params.subject,
        "effort_level": params.effort_level,
        "due_date": params.due_date,
        "assigned_to": child,
        "reward_amount": params.reward_amount,
        "coin_reward": params.coin_reward,
        "notes": params.notes,
        "skill_tags": params.skill_tags,
    }

    assignment = HomeworkService.create_assignment(user, data)
    return homework_assignment_to_dict(assignment)


@tool()
@safe_tool
def submit_homework(params: SubmitHomeworkIn) -> dict[str, Any]:
    """Submit homework for review (child-only). Note: images must be uploaded via the REST API."""
    user = get_current_user()
    try:
        assignment = HomeworkAssignment.objects.get(pk=params.assignment_id)
    except HomeworkAssignment.DoesNotExist:
        raise MCPNotFoundError(f"Assignment {params.assignment_id} not found.")

    raise HomeworkError(
        "Homework submission requires image uploads. "
        "Use the REST API endpoint POST /api/homework/{id}/submit/ with multipart form data."
    )


@tool()
@safe_tool
def list_homework_submissions(params: ListHomeworkSubmissionsIn) -> dict[str, Any]:
    """List homework submissions. Parents see all; children see their own."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)

    qs = HomeworkSubmission.objects.select_related(
        "assignment", "user",
    ).prefetch_related("proofs")

    if user.role != "parent":
        qs = qs.filter(user=target)
    elif params.user_id:
        qs = qs.filter(user=target)

    if params.status:
        qs = qs.filter(status=params.status)

    return {
        "submissions": many(
            qs.order_by("-created_at")[:params.limit],
            homework_submission_to_dict,
        ),
    }


@tool()
@safe_tool
def approve_homework_submission(params: DecideHomeworkSubmissionIn) -> dict[str, Any]:
    """Approve a pending homework submission (parent-only). Awards money, coins, and XP."""
    parent = require_parent()
    try:
        submission = HomeworkSubmission.objects.select_related(
            "assignment", "user",
        ).get(pk=params.submission_id)
    except HomeworkSubmission.DoesNotExist:
        raise MCPNotFoundError(f"Submission {params.submission_id} not found.")

    updated = HomeworkService.approve_submission(submission, parent)
    return homework_submission_to_dict(updated)


@tool()
@safe_tool
def reject_homework_submission(params: DecideHomeworkSubmissionIn) -> dict[str, Any]:
    """Reject a pending homework submission (parent-only). Child can re-submit."""
    parent = require_parent()
    try:
        submission = HomeworkSubmission.objects.select_related(
            "assignment", "user",
        ).get(pk=params.submission_id)
    except HomeworkSubmission.DoesNotExist:
        raise MCPNotFoundError(f"Submission {params.submission_id} not found.")

    updated = HomeworkService.reject_submission(submission, parent)
    return homework_submission_to_dict(updated)
