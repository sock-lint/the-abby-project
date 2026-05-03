"""Project-related MCP tools.

Wraps the existing Project, ProjectMilestone, MaterialItem models and the
achievements skill-tag tables so Claude can browse, create, and transition
projects without duplicating any business logic.
"""
from __future__ import annotations

from typing import Any

from django.db import models, transaction
from django.utils import timezone

from apps.achievements.models import (
    MilestoneSkillTag,
    ProjectSkillTag,
    Skill,
)
from apps.achievements.services import AwardService, SkillService
from apps.projects.models import (
    MaterialItem,
    Project,
    ProjectCollaborator,
    ProjectMilestone,
    ProjectResource,
    ProjectStep,
)
from apps.achievements.models import SkillCategory
from apps.rewards.models import CoinLedger

from ..context import (
    get_current_user, get_in_family, require_parent, resolve_target_user,
)
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..schemas import (
    AddCollaboratorIn,
    AddMaterialIn,
    AddMilestoneIn,
    AddResourceIn,
    AddStepIn,
    CompleteMilestoneIn,
    CreateProjectIn,
    DeleteMaterialIn,
    DeleteMilestoneIn,
    DeleteProjectIn,
    DeleteResourceIn,
    DeleteStepIn,
    GetProjectIn,
    ListProjectsIn,
    MarkMaterialPurchasedIn,
    ProjectActionIn,
    RemoveCollaboratorIn,
    RequestProjectChangesIn,
    SetProjectSkillTagsIn,
    StepActionIn,
    UpdateMaterialIn,
    UpdateMilestoneIn,
    UpdateProjectIn,
    UpdateProjectStatusIn,
    UpdateResourceIn,
    UpdateStepIn,
)
from ..server import tool
from ..shapes import (
    material_to_dict,
    milestone_to_dict,
    project_detail_to_dict,
    project_list_to_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_project_for_user(project_id: int, user) -> Project:
    """Fetch a project respecting role-based visibility.

    Audit C8: parent path now scopes by ``assigned_to__family`` so a parent
    in family A can't read another family's project by id. Children stay
    self-scoped via ``assigned_to=user``.
    """
    qs = Project.objects.all()
    if user.role == "parent":
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            raise MCPNotFoundError(f"Project {project_id} not found.")
        qs = qs.filter(assigned_to__family_id=family_id)
    else:
        qs = qs.filter(assigned_to=user)
    try:
        return qs.select_related("assigned_to", "created_by", "category").get(
            pk=project_id,
        )
    except Project.DoesNotExist:
        raise MCPNotFoundError(f"Project {project_id} not found.")


def _child_allowed_statuses() -> set[str]:
    return {"active", "in_progress", "in_review"}


def _replace_project_skill_tags(project: Project, tags: list[dict[str, int]]) -> None:
    ProjectSkillTag.objects.filter(project=project).delete()
    if not tags:
        return
    skill_ids = [t["skill_id"] for t in tags]
    known_ids = set(Skill.objects.filter(id__in=skill_ids).values_list("id", flat=True))
    missing = [sid for sid in skill_ids if sid not in known_ids]
    if missing:
        raise MCPValidationError(f"Unknown skill IDs: {missing}")
    ProjectSkillTag.objects.bulk_create([
        ProjectSkillTag(
            project=project, skill_id=t["skill_id"], xp_weight=t["xp_weight"],
        )
        for t in tags
    ])


def _create_milestone_skill_tags(
    milestone: ProjectMilestone, tags: list[dict[str, int]],
) -> None:
    if not tags:
        return
    skill_ids = [t["skill_id"] for t in tags]
    known_ids = set(Skill.objects.filter(id__in=skill_ids).values_list("id", flat=True))
    missing = [sid for sid in skill_ids if sid not in known_ids]
    if missing:
        raise MCPValidationError(f"Unknown skill IDs on milestone: {missing}")
    MilestoneSkillTag.objects.bulk_create([
        MilestoneSkillTag(
            milestone=milestone, skill_id=t["skill_id"], xp_amount=t["xp_amount"],
        )
        for t in tags
    ])


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def list_projects(params: ListProjectsIn) -> dict[str, Any]:
    """List projects visible to the current user.

    Children only ever see projects assigned to themselves. Parents can
    filter by ``assigned_to_id`` to narrow to a specific child.
    """
    user = get_current_user()
    qs = Project.objects.select_related(
        "assigned_to", "category",
    ).prefetch_related("milestones")

    # Audit C8: family-scope every parent query. Without this filter, the
    # MCP ``list_projects`` returned every household's projects to every
    # parent in the deployment.
    if user.role == "parent":
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            return {"projects": [], "count": 0}
        qs = qs.filter(assigned_to__family_id=family_id)
        if params.assigned_to_id is not None:
            qs = qs.filter(assigned_to_id=params.assigned_to_id)
    else:
        qs = qs.filter(assigned_to=user)

    if params.status is not None:
        qs = qs.filter(status=params.status)

    qs = qs.order_by("-created_at")[: params.limit]
    projects = list(qs)
    return {
        "projects": [project_list_to_dict(p) for p in projects],
        "count": len(projects),
    }


@tool()
@safe_tool
def get_project(params: GetProjectIn) -> dict[str, Any]:
    """Get a single project's full detail (milestones, materials, skill tags)."""
    user = get_current_user()
    project = _get_project_for_user(params.project_id, user)
    return project_detail_to_dict(project)


@tool()
@safe_tool
def create_project(params: CreateProjectIn) -> dict[str, Any]:
    """Create a new project with optional inline steps, milestones, resources,
    and skill tags.

    Parent-only. Inline ``skill_tags`` are required for clock-out XP to
    actually distribute to skills — pass at least one unless the project
    is intentionally XP-less.

    When creating a project without an Instructables URL, populate ``steps``
    with 4-10 short walkthrough instructions so the child has "do this next"
    guidance. Attach videos/docs to a step via a ``NewResource`` with
    ``step_index`` pointing at the step's 0-based position, or leave
    ``step_index`` as ``None`` for a project-level reference.
    """
    parent = require_parent()

    # Cross-family safety: must be a child in the calling parent's family.
    # ``resolve_target_user`` raises MCPNotFoundError on miss / cross-family,
    # never leaking existence of foreign users.
    assignee = resolve_target_user(parent, params.assigned_to_id)

    category = None
    if params.category_id is not None:
        try:
            category = SkillCategory.objects.get(pk=params.category_id)
        except SkillCategory.DoesNotExist:
            raise MCPValidationError(
                f"category_id {params.category_id} does not match any category.",
            )

    # Validate step_index and milestone_index references BEFORE any DB writes
    # so a bad payload can't half-create a project.
    step_count = len(params.steps)
    milestone_count = len(params.milestones)
    for r_idx, res in enumerate(params.resources):
        if res.step_index is None:
            continue
        if not (0 <= res.step_index < step_count):
            raise MCPValidationError(
                f"resources[{r_idx}].step_index={res.step_index} is out of range "
                f"(there are {step_count} steps).",
            )
    for s_idx, step in enumerate(params.steps):
        if step.milestone_index is None:
            continue
        if not (0 <= step.milestone_index < milestone_count):
            raise MCPValidationError(
                f"steps[{s_idx}].milestone_index={step.milestone_index} is out of "
                f"range (there are {milestone_count} milestones).",
            )

    with transaction.atomic():
        project = Project.objects.create(
            title=params.title,
            description=params.description,
            assigned_to=assignee,
            created_by=parent,
            difficulty=params.difficulty,
            category=category,
            bonus_amount=params.bonus_amount,
            payment_kind=params.payment_kind,
            materials_budget=params.materials_budget,
            hourly_rate_override=params.hourly_rate_override,
            due_date=params.due_date,
            status=params.status,
        )

        # Keep created milestones indexed so steps can resolve their
        # ``milestone_index`` to a real FK below.
        created_milestones: list[ProjectMilestone] = []
        for idx, ms in enumerate(params.milestones):
            milestone = ProjectMilestone.objects.create(
                project=project,
                title=ms.title,
                description=ms.description,
                order=ms.order or idx,
                bonus_amount=ms.bonus_amount,
            )
            created_milestones.append(milestone)
            _create_milestone_skill_tags(
                milestone,
                [t.model_dump() for t in ms.skill_tags],
            )

        _replace_project_skill_tags(
            project,
            [t.model_dump() for t in params.skill_tags],
        )

        # Steps — the walkthrough surface. Order matches the input list.
        # ``milestone_index`` was validated above; resolve it to a real FK
        # so steps render under the right milestone in the Plan tab.
        created_steps: list[ProjectStep] = []
        for idx, s in enumerate(params.steps):
            step_milestone = (
                created_milestones[s.milestone_index]
                if s.milestone_index is not None
                else None
            )
            created_steps.append(ProjectStep.objects.create(
                project=project,
                milestone=step_milestone,
                title=s.title,
                description=s.description,
                order=s.order or idx,
            ))

        # Resources — resolve step_index to a real FK (or None).
        for r_idx, res in enumerate(params.resources):
            step_fk = None
            if res.step_index is not None:
                step_fk = created_steps[res.step_index]
            ProjectResource.objects.create(
                project=project,
                step=step_fk,
                title=res.title,
                url=res.url,
                resource_type=res.resource_type,
                order=res.order or r_idx,
            )

    project.refresh_from_db()
    return project_detail_to_dict(project)


@tool()
@safe_tool
def update_project_status(params: UpdateProjectStatusIn) -> dict[str, Any]:
    """Transition a project's status.

    Children may only move their own projects through the child-allowed
    states (``active``, ``in_progress``, ``in_review``). Parents may set
    any status; transitioning to ``completed`` stamps ``completed_at``
    and triggers XP/coin/badge evaluation via ``AwardService``.
    """
    user = get_current_user()
    project = _get_project_for_user(params.project_id, user)

    if user.role != "parent" and params.status not in _child_allowed_statuses():
        raise MCPPermissionDenied(
            f"Children cannot transition projects to '{params.status}'.",
        )

    with transaction.atomic():
        project.status = params.status
        if params.status == "in_progress" and project.started_at is None:
            project.started_at = timezone.now()
        if params.status == "completed" and project.completed_at is None:
            project.completed_at = timezone.now()
        project.save()

        if params.status == "completed" and project.assigned_to_id:
            coin_reason = (
                CoinLedger.Reason.BOUNTY_BONUS
                if project.payment_kind == "bounty"
                else CoinLedger.Reason.PROJECT_BONUS
            )
            base_coins = 10 * project.difficulty
            coins = int(round(
                base_coins * (2.5 if project.payment_kind == "bounty" else 1),
            ))
            AwardService.grant(
                project.assigned_to,
                project=project,
                xp=project.xp_reward,
                coins=coins,
                coin_reason=coin_reason,
                coin_description=f"Project completed: {project.title}",
                created_by=user,
            )

    project.refresh_from_db()
    return project_detail_to_dict(project)


@tool()
@safe_tool
def complete_milestone(params: CompleteMilestoneIn) -> dict[str, Any]:
    """Mark a milestone as complete and award its bonus + skill XP."""
    user = get_current_user()
    try:
        milestone = ProjectMilestone.objects.select_related("project").get(
            pk=params.milestone_id,
        )
    except ProjectMilestone.DoesNotExist:
        raise MCPNotFoundError(f"Milestone {params.milestone_id} not found.")

    project = milestone.project
    if user.role != "parent" and project.assigned_to_id != user.id:
        raise MCPPermissionDenied("Milestone is not on your project.")

    if milestone.is_completed:
        return {
            "milestone": milestone_to_dict(milestone),
            "already_completed": True,
            "xp_awarded": 0,
            "coins_awarded": 0,
        }

    with transaction.atomic():
        milestone.is_completed = True
        milestone.completed_at = timezone.now()
        milestone.save(update_fields=["is_completed", "completed_at"])

        xp_total = 0
        skill_xp_tags = list(milestone.skill_tags.select_related("skill").all())
        if skill_xp_tags and project.assigned_to_id:
            for tag in skill_xp_tags:
                SkillService.award_xp(project.assigned_to, tag.skill, tag.xp_amount)
                xp_total += tag.xp_amount

        coins = 0
        if milestone.bonus_amount and project.assigned_to_id:
            coins = min(100, int(round(float(milestone.bonus_amount) * 2)))
            if coins > 0:
                AwardService.grant(
                    project.assigned_to,
                    coins=coins,
                    coin_reason=CoinLedger.Reason.MILESTONE_BONUS,
                    coin_description=f"Milestone: {milestone.title}",
                    created_by=user,
                )

    milestone.refresh_from_db()
    return {
        "milestone": milestone_to_dict(milestone),
        "xp_awarded": xp_total,
        "coins_awarded": coins,
    }


@tool()
@safe_tool
def set_project_skill_tags(params: SetProjectSkillTagsIn) -> dict[str, Any]:
    """Replace the full skill-tag set on a project (parent-only).

    Lets parents route XP to different skills after project creation.
    """
    parent = require_parent()
    project = get_in_family(
        Project, params.project_id, actor=parent,
        family_path="assigned_to__family",
    )

    with transaction.atomic():
        _replace_project_skill_tags(
            project, [t.model_dump() for t in params.skill_tags],
        )
    return project_detail_to_dict(project)


@tool()
@safe_tool
def mark_material_purchased(params: MarkMaterialPurchasedIn) -> dict[str, Any]:
    """Mark a material as purchased; children may only modify their own projects."""
    user = get_current_user()
    # Audit C8: scope the lookup. Parent path was previously unrestricted —
    # any parent could mark materials on any family's project as purchased.
    qs = MaterialItem.objects.select_related("project")
    if user.role == "parent":
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            raise MCPNotFoundError(f"Material {params.material_id} not found.")
        qs = qs.filter(project__assigned_to__family_id=family_id)
    else:
        qs = qs.filter(project__assigned_to=user)
    try:
        material = qs.get(pk=params.material_id)
    except MaterialItem.DoesNotExist:
        raise MCPNotFoundError(f"Material {params.material_id} not found.")

    material.is_purchased = True
    material.purchased_at = timezone.now()
    if params.actual_cost is not None:
        material.actual_cost = params.actual_cost
    elif material.actual_cost is None:
        material.actual_cost = material.estimated_cost
    material.save()
    return material_to_dict(material)


# ---------------------------------------------------------------------------
# Tier 1.1: Project editing + nested CRUD
# ---------------------------------------------------------------------------


def _get_project_parent_only(project_id: int) -> Project:
    """Audit C8: family-scope every parent-only project lookup. Without
    this scope, a parent in family A could enumerate, edit, complete, or
    delete any other family's project by id via the MCP channel — every
    one of the 18+ ``_get_project_parent_only`` call sites was vulnerable.
    """
    parent = require_parent()
    return get_in_family(
        Project, project_id, actor=parent,
        family_path="assigned_to__family",
    )


@tool()
@safe_tool
def update_project(params: UpdateProjectIn) -> dict[str, Any]:
    """Edit project fields (parent-only). Only the provided fields are touched.

    Use ``update_project_status`` for status transitions — this tool refuses
    status changes so it can't bypass the completion-hooks there.
    """
    project = _get_project_parent_only(params.project_id)
    parent = require_parent()

    data = params.model_dump(exclude={"project_id"}, exclude_unset=True)

    if "assigned_to_id" in data:
        # Cross-family safety: same as create_project — only assign to a
        # child in this parent's family. resolve_target_user raises
        # MCPNotFoundError on cross-family.
        resolve_target_user(parent, data["assigned_to_id"])
    if "category_id" in data and data["category_id"] is not None:
        try:
            SkillCategory.objects.get(pk=data["category_id"])
        except SkillCategory.DoesNotExist:
            raise MCPValidationError(
                f"category_id {data['category_id']} does not match any category.",
            )

    for field, value in data.items():
        setattr(project, field, value)
    project.save()
    project.refresh_from_db()
    return project_detail_to_dict(project)


@tool()
@safe_tool
def delete_project(params: DeleteProjectIn) -> dict[str, Any]:
    """Delete a project and all its nested milestones/steps/materials/resources."""
    project = _get_project_parent_only(params.project_id)
    project_id = project.pk
    project.delete()
    return {"project_id": project_id, "deleted": True}


@tool()
@safe_tool
def activate_project(params: ProjectActionIn) -> dict[str, Any]:
    """Move a ``draft``/``in_review`` project to ``in_progress`` (parent-only).

    Matches the REST ``POST /api/projects/{id}/activate/`` behavior —
    stamps ``started_at`` if unset.
    """
    project = _get_project_parent_only(params.project_id)
    if project.status not in ("draft", "in_review"):
        raise MCPValidationError(
            f"Cannot activate from status {project.status!r}. "
            "Expected 'draft' or 'in_review'.",
        )
    project.status = "in_progress"
    if project.started_at is None:
        project.started_at = timezone.now()
    project.save()
    return project_detail_to_dict(project)


@tool()
@safe_tool
def approve_project(params: ProjectActionIn) -> dict[str, Any]:
    """Mark a project as ``completed`` (parent-only).

    Matches ``POST /api/projects/{id}/approve/``. The project-completion
    signals fire on save, awarding XP/coins/badges just like the REST path.
    """
    project = _get_project_parent_only(params.project_id)
    project.status = "completed"
    if project.completed_at is None:
        project.completed_at = timezone.now()
    project.save()
    return project_detail_to_dict(project)


@tool()
@safe_tool
def request_project_changes(params: RequestProjectChangesIn) -> dict[str, Any]:
    """Send a project back to ``in_progress`` with parent notes (parent-only).

    Matches ``POST /api/projects/{id}/request-changes/``. Use this after a
    child submits for review but the work needs iteration.
    """
    project = _get_project_parent_only(params.project_id)
    project.status = "in_progress"
    if project.started_at is None:
        project.started_at = timezone.now()
    project.parent_notes = params.parent_notes
    project.save()
    return project_detail_to_dict(project)


# ---- Milestone CRUD ------------------------------------------------------


def _get_milestone_parent_only(milestone_id: int) -> ProjectMilestone:
    """Audit C8: scope through ``project.assigned_to.family`` so a parent
    can't reach into another family's milestone by id."""
    parent = require_parent()
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(f"Milestone {milestone_id} not found.")
    try:
        return ProjectMilestone.objects.select_related("project").get(
            pk=milestone_id,
            project__assigned_to__family_id=family_id,
        )
    except ProjectMilestone.DoesNotExist:
        raise MCPNotFoundError(f"Milestone {milestone_id} not found.")


@tool()
@safe_tool
def add_milestone(params: AddMilestoneIn) -> dict[str, Any]:
    """Add a milestone (chapter) to an existing project. Parent-only.

    Pass ``skill_tags`` to wire this milestone to XP awards on completion.
    Milestones with a ``bonus_amount`` post to PaymentLedger.milestone_bonus
    when marked complete via ``complete_milestone``.
    """
    project = _get_project_parent_only(params.project_id)
    with transaction.atomic():
        milestone = ProjectMilestone.objects.create(
            project=project,
            title=params.title,
            description=params.description,
            order=params.order,
            bonus_amount=params.bonus_amount,
        )
        _create_milestone_skill_tags(
            milestone, [t.model_dump() for t in params.skill_tags],
        )
    milestone.refresh_from_db()
    return milestone_to_dict(milestone)


@tool()
@safe_tool
def update_milestone(params: UpdateMilestoneIn) -> dict[str, Any]:
    """Edit a milestone. When ``skill_tags`` is provided, replaces the full set."""
    milestone = _get_milestone_parent_only(params.milestone_id)
    data = params.model_dump(
        exclude={"milestone_id", "skill_tags"},
        exclude_unset=True,
    )
    with transaction.atomic():
        for field, value in data.items():
            setattr(milestone, field, value)
        milestone.save()
        if params.skill_tags is not None:
            MilestoneSkillTag.objects.filter(milestone=milestone).delete()
            _create_milestone_skill_tags(
                milestone, [t.model_dump() for t in params.skill_tags],
            )
    milestone.refresh_from_db()
    return milestone_to_dict(milestone)


@tool()
@safe_tool
def delete_milestone(params: DeleteMilestoneIn) -> dict[str, Any]:
    """Delete a milestone. Its steps become ungrouped (milestone=None)."""
    milestone = _get_milestone_parent_only(params.milestone_id)
    milestone_id = milestone.pk
    # ProjectStep.milestone is SET_NULL — deletion un-groups steps rather
    # than cascading. MilestoneSkillTag rows cascade on delete.
    milestone.delete()
    return {"milestone_id": milestone_id, "deleted": True}


# ---- Step CRUD -----------------------------------------------------------


def _get_step_editable(step_id: int) -> ProjectStep:
    """Audit C8: scope through the parent project's family."""
    parent = require_parent()
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(f"Step {step_id} not found.")
    try:
        return ProjectStep.objects.select_related("project").get(
            pk=step_id,
            project__assigned_to__family_id=family_id,
        )
    except ProjectStep.DoesNotExist:
        raise MCPNotFoundError(f"Step {step_id} not found.")


@tool()
@safe_tool
def add_step(params: AddStepIn) -> dict[str, Any]:
    """Add a walkthrough step to a project, optionally grouped under a milestone.

    Steps are parent-authored instructional content; children toggle their
    completion via ``complete_step`` / ``uncomplete_step``.
    """
    project = _get_project_parent_only(params.project_id)
    milestone = None
    if params.milestone_id is not None:
        try:
            milestone = ProjectMilestone.objects.get(
                pk=params.milestone_id, project=project,
            )
        except ProjectMilestone.DoesNotExist:
            raise MCPValidationError(
                f"milestone_id {params.milestone_id} is not on this project.",
            )
    step = ProjectStep.objects.create(
        project=project,
        milestone=milestone,
        title=params.title,
        description=params.description,
        order=params.order,
    )
    return {
        "id": step.id,
        "project_id": step.project_id,
        "milestone_id": step.milestone_id,
        "title": step.title,
        "description": step.description,
        "order": step.order,
        "is_completed": step.is_completed,
    }


@tool()
@safe_tool
def update_step(params: UpdateStepIn) -> dict[str, Any]:
    """Edit a step. Parent-only.

    To unset a step's milestone (ungroup it), pass ``clear_milestone=True``.
    Passing ``milestone_id=<id>`` re-groups under that milestone; leaving
    both unset preserves the current grouping.
    """
    step = _get_step_editable(params.step_id)
    data = params.model_dump(
        exclude={"step_id", "milestone_id", "clear_milestone"},
        exclude_unset=True,
    )
    for field, value in data.items():
        setattr(step, field, value)
    if params.clear_milestone:
        step.milestone = None
    elif params.milestone_id is not None:
        try:
            step.milestone = ProjectMilestone.objects.get(
                pk=params.milestone_id, project=step.project,
            )
        except ProjectMilestone.DoesNotExist:
            raise MCPValidationError(
                f"milestone_id {params.milestone_id} is not on this project.",
            )
    step.save()
    return {
        "id": step.id,
        "project_id": step.project_id,
        "milestone_id": step.milestone_id,
        "title": step.title,
        "description": step.description,
        "order": step.order,
        "is_completed": step.is_completed,
    }


@tool()
@safe_tool
def delete_step(params: DeleteStepIn) -> dict[str, Any]:
    """Delete a walkthrough step (parent-only)."""
    step = _get_step_editable(params.step_id)
    step_id = step.pk
    step.delete()
    return {"step_id": step_id, "deleted": True}


def _can_toggle_step(user, project) -> bool:
    # Audit C8: family-scope the parent path. Without this, a parent in
    # family A could toggle any step in any other family's project.
    if user.role == "parent":
        return project.assigned_to_id is not None and (
            project.assigned_to.family_id == getattr(user, "family_id", None)
        )
    if project.assigned_to_id == user.id:
        return True
    return project.collaborators.filter(user=user).exists()


def _get_toggleable_step(step_id: int, user) -> ProjectStep:
    """Fetch a step the user can toggle, family-scoped (Audit C8).

    Replaces a bare ``ProjectStep.objects.get(pk=...)`` that allowed any
    authenticated parent to enumerate steps from any family by id.
    """
    qs = ProjectStep.objects.select_related("project")
    if user.role == "parent":
        family_id = getattr(user, "family_id", None)
        if family_id is None:
            raise MCPNotFoundError(f"Step {step_id} not found.")
        qs = qs.filter(project__assigned_to__family_id=family_id)
    else:
        qs = qs.filter(
            models.Q(project__assigned_to=user)
            | models.Q(project__collaborators__user=user),
        ).distinct()
    try:
        return qs.get(pk=step_id)
    except ProjectStep.DoesNotExist:
        raise MCPNotFoundError(f"Step {step_id} not found.")


@tool()
@safe_tool
def complete_step(params: StepActionIn) -> dict[str, Any]:
    """Mark a step complete. Child-safe: assignee or collaborators may toggle."""
    user = get_current_user()
    step = _get_toggleable_step(params.step_id, user)
    step.is_completed = True
    step.completed_at = timezone.now()
    step.save(update_fields=["is_completed", "completed_at", "updated_at"])
    return {"step_id": step.id, "is_completed": True}


@tool()
@safe_tool
def uncomplete_step(params: StepActionIn) -> dict[str, Any]:
    """Un-mark a step. Child-safe: assignee or collaborators may toggle."""
    user = get_current_user()
    step = _get_toggleable_step(params.step_id, user)
    step.is_completed = False
    step.completed_at = None
    step.save(update_fields=["is_completed", "completed_at", "updated_at"])
    return {"step_id": step.id, "is_completed": False}


# ---- Material CRUD -------------------------------------------------------


def _get_material_parent_only(material_id: int) -> MaterialItem:
    """Audit C8: scope through the parent project's family."""
    parent = require_parent()
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(f"Material {material_id} not found.")
    try:
        return MaterialItem.objects.select_related("project").get(
            pk=material_id,
            project__assigned_to__family_id=family_id,
        )
    except MaterialItem.DoesNotExist:
        raise MCPNotFoundError(f"Material {material_id} not found.")


@tool()
@safe_tool
def add_material(params: AddMaterialIn) -> dict[str, Any]:
    """Add a material to a project's bill-of-materials (parent-only)."""
    project = _get_project_parent_only(params.project_id)
    material = MaterialItem.objects.create(
        project=project,
        name=params.name,
        description=params.description,
        estimated_cost=params.estimated_cost,
    )
    return material_to_dict(material)


@tool()
@safe_tool
def update_material(params: UpdateMaterialIn) -> dict[str, Any]:
    """Edit a material (parent-only). To mark purchased, use ``mark_material_purchased``."""
    material = _get_material_parent_only(params.material_id)
    data = params.model_dump(exclude={"material_id"}, exclude_unset=True)
    for field, value in data.items():
        setattr(material, field, value)
    material.save()
    return material_to_dict(material)


@tool()
@safe_tool
def delete_material(params: DeleteMaterialIn) -> dict[str, Any]:
    """Delete a material from a project (parent-only)."""
    material = _get_material_parent_only(params.material_id)
    material_id = material.pk
    material.delete()
    return {"material_id": material_id, "deleted": True}


# ---- Resource CRUD -------------------------------------------------------


def _get_resource_parent_only(resource_id: int) -> ProjectResource:
    """Audit C8: scope through the parent project's family."""
    parent = require_parent()
    family_id = getattr(parent, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(f"Resource {resource_id} not found.")
    try:
        return ProjectResource.objects.select_related("project", "step").get(
            pk=resource_id,
            project__assigned_to__family_id=family_id,
        )
    except ProjectResource.DoesNotExist:
        raise MCPNotFoundError(f"Resource {resource_id} not found.")


def _resource_to_dict(resource: ProjectResource) -> dict[str, Any]:
    return {
        "id": resource.id,
        "project_id": resource.project_id,
        "step_id": resource.step_id,
        "url": resource.url,
        "title": resource.title,
        "resource_type": resource.resource_type,
        "order": resource.order,
    }


@tool()
@safe_tool
def add_resource(params: AddResourceIn) -> dict[str, Any]:
    """Add a reference link (video/doc/image/link) to a project or step. Parent-only."""
    project = _get_project_parent_only(params.project_id)
    step = None
    if params.step_id is not None:
        try:
            step = ProjectStep.objects.get(pk=params.step_id, project=project)
        except ProjectStep.DoesNotExist:
            raise MCPValidationError(
                f"step_id {params.step_id} is not on this project.",
            )
    resource = ProjectResource.objects.create(
        project=project,
        step=step,
        url=params.url,
        title=params.title,
        resource_type=params.resource_type,
        order=params.order,
    )
    return _resource_to_dict(resource)


@tool()
@safe_tool
def update_resource(params: UpdateResourceIn) -> dict[str, Any]:
    """Edit a reference link (parent-only).

    Pass ``clear_step=True`` to promote a step-scoped resource to
    project-level. Pass ``step_id=<id>`` to re-scope to a step.
    """
    resource = _get_resource_parent_only(params.resource_id)
    data = params.model_dump(
        exclude={"resource_id", "step_id", "clear_step"},
        exclude_unset=True,
    )
    for field, value in data.items():
        setattr(resource, field, value)
    if params.clear_step:
        resource.step = None
    elif params.step_id is not None:
        try:
            resource.step = ProjectStep.objects.get(
                pk=params.step_id, project=resource.project,
            )
        except ProjectStep.DoesNotExist:
            raise MCPValidationError(
                f"step_id {params.step_id} is not on this project.",
            )
    resource.save()
    return _resource_to_dict(resource)


@tool()
@safe_tool
def delete_resource(params: DeleteResourceIn) -> dict[str, Any]:
    """Delete a reference link (parent-only)."""
    resource = _get_resource_parent_only(params.resource_id)
    resource_id = resource.pk
    resource.delete()
    return {"resource_id": resource_id, "deleted": True}


# ---------------------------------------------------------------------------
# Tier 3.1: Collaborators
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def add_collaborator(params: AddCollaboratorIn) -> dict[str, Any]:
    """Add a child as a collaborator on a project (parent-only).

    Collaborators can toggle step completion alongside the primary assignee.
    ``pay_split_percent`` is informational — the ledger still pays the
    assignee; splits are tracked for reporting.
    """
    project = _get_project_parent_only(params.project_id)
    parent = require_parent()
    child = resolve_target_user(parent, params.user_id)
    if getattr(child, "role", None) != "child":
        raise MCPValidationError(
            f"user_id {params.user_id} does not match any child.",
        )
    if project.assigned_to_id == child.id:
        raise MCPValidationError(
            "This child is already the primary assignee; no need to add as a "
            "collaborator.",
        )
    if ProjectCollaborator.objects.filter(
        project=project, user=child,
    ).exists():
        raise MCPValidationError(
            f"{child.display_label} is already a collaborator on this project.",
        )
    collab = ProjectCollaborator.objects.create(
        project=project,
        user=child,
        pay_split_percent=params.pay_split_percent,
    )
    return {
        "id": collab.id,
        "project_id": project.id,
        "user_id": child.id,
        "pay_split_percent": collab.pay_split_percent,
    }


@tool()
@safe_tool
def remove_collaborator(params: RemoveCollaboratorIn) -> dict[str, Any]:
    """Remove a collaborator from a project (parent-only)."""
    project = _get_project_parent_only(params.project_id)
    deleted, _ = ProjectCollaborator.objects.filter(
        project=project, user_id=params.user_id,
    ).delete()
    if not deleted:
        raise MCPNotFoundError(
            f"User {params.user_id} is not a collaborator on project "
            f"{params.project_id}.",
        )
    return {
        "project_id": project.id,
        "user_id": params.user_id,
        "deleted": True,
    }
