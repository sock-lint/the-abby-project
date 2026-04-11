"""Project-related MCP tools.

Wraps the existing Project, ProjectMilestone, MaterialItem models and the
achievements skill-tag tables so Claude can browse, create, and transition
projects without duplicating any business logic.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
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
    ProjectMilestone,
    ProjectResource,
    ProjectStep,
    SkillCategory,
    User,
)
from apps.rewards.models import CoinLedger

from ..context import get_current_user, require_parent
from ..errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError, safe_tool
from ..schemas import (
    CompleteMilestoneIn,
    CreateProjectIn,
    GetProjectIn,
    ListProjectsIn,
    MarkMaterialPurchasedIn,
    SetProjectSkillTagsIn,
    UpdateProjectStatusIn,
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
    """Fetch a project respecting role-based visibility."""
    qs = Project.objects.all()
    if user.role != "parent":
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

    if user.role != "parent":
        qs = qs.filter(assigned_to=user)
    elif params.assigned_to_id is not None:
        qs = qs.filter(assigned_to_id=params.assigned_to_id)

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

    try:
        assignee = User.objects.get(pk=params.assigned_to_id)
    except User.DoesNotExist:
        raise MCPValidationError(
            f"assigned_to_id {params.assigned_to_id} does not match any user.",
        )

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
    require_parent()
    try:
        project = Project.objects.get(pk=params.project_id)
    except Project.DoesNotExist:
        raise MCPNotFoundError(f"Project {params.project_id} not found.")

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
    try:
        material = MaterialItem.objects.select_related("project").get(
            pk=params.material_id,
        )
    except MaterialItem.DoesNotExist:
        raise MCPNotFoundError(f"Material {params.material_id} not found.")

    if user.role != "parent" and material.project.assigned_to_id != user.id:
        raise MCPPermissionDenied("Material is not on your project.")

    material.is_purchased = True
    material.purchased_at = timezone.now()
    if params.actual_cost is not None:
        material.actual_cost = params.actual_cost
    elif material.actual_cost is None:
        material.actual_cost = material.estimated_cost
    material.save()
    return material_to_dict(material)
