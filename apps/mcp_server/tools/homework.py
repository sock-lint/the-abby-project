"""Homework-related MCP tools."""
from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.homework.models import (
    HomeworkAssignment,
    HomeworkSkillTag,
    HomeworkSubmission,
    HomeworkTemplate,
)
from apps.homework.services import HomeworkError, HomeworkService

from ..context import get_current_user, require_parent, resolve_target_user
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    CreateHomeworkFromTemplateIn,
    CreateHomeworkIn,
    CreateHomeworkTemplateIn,
    DecideHomeworkSubmissionIn,
    DeleteHomeworkIn,
    DeleteHomeworkTemplateIn,
    GetHomeworkIn,
    GetHomeworkTemplateIn,
    ListHomeworkIn,
    ListHomeworkSubmissionsIn,
    ListHomeworkTemplatesIn,
    PlanHomeworkIn,
    SetHomeworkSkillTagsIn,
    SubmitHomeworkIn,
    UpdateHomeworkIn,
    UpdateHomeworkTemplateIn,
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

    child = resolve_target_user(user, params.assigned_to_id)
    if getattr(child, "role", None) != "child":
        raise MCPNotFoundError(f"Child {params.assigned_to_id} not found.")

    data = {
        "title": params.title,
        "description": params.description,
        "subject": params.subject,
        "effort_level": params.effort_level,
        "due_date": params.due_date,
        "assigned_to": child,
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

    # Audit C3: when a parent calls without user_id, scope to their family
    # rather than returning every household's submissions in the deployment.
    qs = HomeworkSubmission.objects.select_related(
        "assignment", "user",
    ).prefetch_related("proofs")

    if user.role != "parent":
        qs = qs.filter(user=target)
    elif params.user_id:
        qs = qs.filter(user=target)
    else:
        qs = qs.filter(user__family=user.family)

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
    """Approve a pending homework submission (parent-only). Awards XP + fires the RPG loop."""
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


# ---------------------------------------------------------------------------
# Tier 1.4: update/delete + templates + skill tags
# ---------------------------------------------------------------------------


def _get_assignment_parent_only(assignment_id: int) -> HomeworkAssignment:
    require_parent()
    try:
        return HomeworkAssignment.objects.get(pk=assignment_id)
    except HomeworkAssignment.DoesNotExist:
        raise MCPNotFoundError(f"Assignment {assignment_id} not found.")


@tool()
@safe_tool
def update_homework(params: UpdateHomeworkIn) -> dict[str, Any]:
    """Edit fields on a homework assignment (parent-only).

    Use ``set_homework_skill_tags`` to change XP routing. Use
    ``delete_homework`` to soft-delete (sets ``is_active=False``).
    """
    assignment = _get_assignment_parent_only(params.assignment_id)
    data = params.model_dump(exclude={"assignment_id"}, exclude_unset=True)
    for field, value in data.items():
        setattr(assignment, field, value)
    assignment.save()
    assignment.refresh_from_db()
    return homework_assignment_to_dict(assignment)


@tool()
@safe_tool
def delete_homework(params: DeleteHomeworkIn) -> dict[str, Any]:
    """Soft-delete a homework assignment (sets ``is_active=False``). Parent-only.

    Mirrors the REST ``DELETE`` behavior. Submissions stay intact so past
    receipts remain visible in the portfolio.
    """
    assignment = _get_assignment_parent_only(params.assignment_id)
    assignment.is_active = False
    assignment.save(update_fields=["is_active"])
    return {"assignment_id": assignment.id, "deleted": True}


@tool()
@safe_tool
def set_homework_skill_tags(params: SetHomeworkSkillTagsIn) -> dict[str, Any]:
    """Replace the skill-tag set on an assignment (parent-only).

    Passing an empty list removes all tags (the assignment will award no
    XP on approval). Homework no longer pays money or coins — skill
    tags are the only progression reward.
    """
    from apps.achievements.models import Skill

    assignment = _get_assignment_parent_only(params.assignment_id)
    skill_ids = [t.skill_id for t in params.skill_tags]
    known = set(Skill.objects.filter(id__in=skill_ids).values_list("id", flat=True))
    missing = [s for s in skill_ids if s not in known]
    if missing:
        raise MCPValidationError(f"Unknown skill IDs: {missing}")
    with transaction.atomic():
        HomeworkSkillTag.objects.filter(assignment=assignment).delete()
        HomeworkSkillTag.objects.bulk_create([
            HomeworkSkillTag(
                assignment=assignment,
                skill_id=t.skill_id,
                xp_amount=t.xp_amount,
            )
            for t in params.skill_tags
        ])
    assignment.refresh_from_db()
    return homework_assignment_to_dict(assignment)


@tool()
@safe_tool
def plan_homework(params: PlanHomeworkIn) -> dict[str, Any]:
    """Trigger AI project planning for a homework assignment (parent-only).

    Calls the underlying ``HomeworkService.plan_assignment`` which uses
    Claude + the MCP ``create_project`` tool to generate a full project
    linked to the assignment. Returns the updated assignment (now with
    ``project_id`` set).

    Raises ``MCPValidationError`` if the assignment already has a linked
    project or if AI planning is not yet configured.
    """
    parent = require_parent()
    try:
        assignment = HomeworkAssignment.objects.get(pk=params.assignment_id)
    except HomeworkAssignment.DoesNotExist:
        raise MCPNotFoundError(f"Assignment {params.assignment_id} not found.")
    if assignment.project_id:
        raise MCPValidationError(
            "This assignment already has a linked project "
            f"(project_id={assignment.project_id}).",
        )
    if not hasattr(HomeworkService, "plan_assignment"):
        raise MCPValidationError(
            "AI planning is not yet configured on this server.",
        )
    try:
        HomeworkService.plan_assignment(assignment, parent=parent)
    except HomeworkError as exc:
        raise MCPValidationError(str(exc)) from exc
    assignment.refresh_from_db()
    return homework_assignment_to_dict(assignment)


# ---- Templates -----------------------------------------------------------


def _template_to_dict(template: HomeworkTemplate) -> dict[str, Any]:
    from apps.homework.serializers import HomeworkTemplateSerializer
    from ..shapes import to_plain

    return to_plain(HomeworkTemplateSerializer(template).data)


@tool()
@safe_tool
def list_homework_templates(params: ListHomeworkTemplatesIn) -> dict[str, Any]:
    """List homework templates owned by the calling parent."""
    parent = require_parent()
    qs = HomeworkTemplate.objects.filter(created_by=parent).order_by("title")
    items = [_template_to_dict(t) for t in qs[: params.limit]]
    return {"templates": items, "count": len(items)}


@tool()
@safe_tool
def get_homework_template(params: GetHomeworkTemplateIn) -> dict[str, Any]:
    """Return a single template owned by the calling parent."""
    parent = require_parent()
    try:
        template = HomeworkTemplate.objects.get(
            pk=params.template_id, created_by=parent,
        )
    except HomeworkTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    return _template_to_dict(template)


@tool()
@safe_tool
def create_homework_template(params: CreateHomeworkTemplateIn) -> dict[str, Any]:
    """Create a reusable homework template (parent-only)."""
    parent = require_parent()
    template = HomeworkTemplate.objects.create(
        title=params.title,
        description=params.description,
        subject=params.subject,
        effort_level=params.effort_level,
        created_by=parent,
        skill_tags=[t.model_dump() for t in params.skill_tags],
    )
    return _template_to_dict(template)


@tool()
@safe_tool
def update_homework_template(params: UpdateHomeworkTemplateIn) -> dict[str, Any]:
    """Edit a homework template (parent-only)."""
    parent = require_parent()
    try:
        template = HomeworkTemplate.objects.get(
            pk=params.template_id, created_by=parent,
        )
    except HomeworkTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    data = params.model_dump(
        exclude={"template_id", "skill_tags"}, exclude_unset=True,
    )
    for field, value in data.items():
        setattr(template, field, value)
    if params.skill_tags is not None:
        template.skill_tags = [t.model_dump() for t in params.skill_tags]
    template.save()
    return _template_to_dict(template)


@tool()
@safe_tool
def delete_homework_template(params: DeleteHomeworkTemplateIn) -> dict[str, Any]:
    """Delete a homework template (parent-only)."""
    parent = require_parent()
    try:
        template = HomeworkTemplate.objects.get(
            pk=params.template_id, created_by=parent,
        )
    except HomeworkTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    template_id = template.pk
    template.delete()
    return {"template_id": template_id, "deleted": True}


@tool()
@safe_tool
def create_homework_from_template(
    params: CreateHomeworkFromTemplateIn,
) -> dict[str, Any]:
    """Spawn a homework assignment for a child from a template (parent-only)."""
    parent = require_parent()
    try:
        template = HomeworkTemplate.objects.get(
            pk=params.template_id, created_by=parent,
        )
    except HomeworkTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    child = resolve_target_user(parent, params.assigned_to_id)
    if getattr(child, "role", None) != "child":
        raise MCPValidationError(
            f"Child {params.assigned_to_id} not found.",
        )
    try:
        assignment = HomeworkService.create_from_template(
            template, child, params.due_date,
        )
    except HomeworkError as exc:
        raise MCPValidationError(str(exc))
    return homework_assignment_to_dict(assignment)
