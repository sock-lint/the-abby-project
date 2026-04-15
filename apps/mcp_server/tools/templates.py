"""Project template MCP tools (Tier 1.2).

Mirrors the ``/api/templates/`` DRF surface. Templates are reusable
project blueprints — parents can spin a new project from a template for
any child in one call (``create_project_from_template``).
"""
from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.projects.models import (
    MaterialItem,
    Project,
    ProjectMilestone,
    ProjectResource,
    ProjectStep,
    ProjectTemplate,
    TemplateMaterial,
    TemplateMilestone,
    TemplateResource,
    TemplateStep,
    User,
)
from apps.achievements.models import SkillCategory

from ..context import get_current_user, require_parent
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..schemas import (
    CreateProjectFromTemplateIn,
    CreateTemplateIn,
    DeleteTemplateIn,
    GetTemplateIn,
    ListTemplatesIn,
    SaveProjectAsTemplateIn,
    UpdateTemplateIn,
)
from ..server import tool
from ..shapes import project_detail_to_dict


# ---------------------------------------------------------------------------
# Serializer helpers (local — shapes.py doesn't have template shapes today)
# ---------------------------------------------------------------------------


def _template_to_dict(template: ProjectTemplate) -> dict[str, Any]:
    from apps.projects.serializers import ProjectTemplateSerializer
    from ..shapes import to_plain

    return to_plain(ProjectTemplateSerializer(template).data)


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def list_templates(params: ListTemplatesIn) -> dict[str, Any]:
    """List project templates visible to the current user.

    Parents see all templates; children only see public ones. Use
    ``is_public_only=True`` to filter even parents down to public.
    """
    user = get_current_user()
    qs = ProjectTemplate.objects.select_related("category", "created_by")
    if user.role != "parent" or params.is_public_only:
        qs = qs.filter(is_public=True)
    qs = qs.order_by("-created_at")[: params.limit]
    items = [_template_to_dict(t) for t in qs]
    return {"templates": items, "count": len(items)}


@tool()
@safe_tool
def get_template(params: GetTemplateIn) -> dict[str, Any]:
    """Return one template with its milestones, materials, steps, resources."""
    user = get_current_user()
    try:
        template = ProjectTemplate.objects.get(pk=params.template_id)
    except ProjectTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    if user.role != "parent" and not template.is_public:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    return _template_to_dict(template)


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


@tool()
@safe_tool
def create_template(params: CreateTemplateIn) -> dict[str, Any]:
    """Create a new project template from scratch (parent-only).

    Pass inline ``milestones``, ``materials``, ``steps`` (with optional
    ``milestone_index``), and ``resources`` (with optional ``step_index``)
    to author a full template in one call. Indexes are resolved to FKs
    after the parent rows are inserted.
    """
    parent = require_parent()

    category = None
    if params.category_id is not None:
        try:
            category = SkillCategory.objects.get(pk=params.category_id)
        except SkillCategory.DoesNotExist:
            raise MCPValidationError(
                f"category_id {params.category_id} does not match any category.",
            )

    # Pre-validate indexes before writes.
    step_count = len(params.steps)
    milestone_count = len(params.milestones)
    for idx, step in enumerate(params.steps):
        if step.milestone_index is not None and not (
            0 <= step.milestone_index < milestone_count
        ):
            raise MCPValidationError(
                f"steps[{idx}].milestone_index out of range.",
            )
    for idx, res in enumerate(params.resources):
        if res.step_index is not None and not (
            0 <= res.step_index < step_count
        ):
            raise MCPValidationError(
                f"resources[{idx}].step_index out of range.",
            )

    with transaction.atomic():
        template = ProjectTemplate.objects.create(
            title=params.title,
            description=params.description,
            instructables_url=params.instructables_url,
            difficulty=params.difficulty,
            category=category,
            bonus_amount=params.bonus_amount,
            materials_budget=params.materials_budget,
            created_by=parent,
            is_public=params.is_public,
        )
        created_milestones: list[TemplateMilestone] = []
        for ms in params.milestones:
            created_milestones.append(TemplateMilestone.objects.create(
                template=template,
                title=ms.title,
                description=ms.description,
                order=ms.order,
                bonus_amount=ms.bonus_amount,
            ))
        for mat in params.materials:
            TemplateMaterial.objects.create(
                template=template,
                name=mat.name,
                description=mat.description,
                estimated_cost=mat.estimated_cost,
            )
        created_steps: list[TemplateStep] = []
        for step in params.steps:
            ms = (
                created_milestones[step.milestone_index]
                if step.milestone_index is not None
                else None
            )
            created_steps.append(TemplateStep.objects.create(
                template=template,
                milestone=ms,
                title=step.title,
                description=step.description,
                order=step.order,
            ))
        for res in params.resources:
            step_fk = (
                created_steps[res.step_index]
                if res.step_index is not None
                else None
            )
            TemplateResource.objects.create(
                template=template,
                step=step_fk,
                title=res.title,
                url=res.url,
                resource_type=res.resource_type,
                order=res.order,
            )
    template.refresh_from_db()
    return _template_to_dict(template)


@tool()
@safe_tool
def update_template(params: UpdateTemplateIn) -> dict[str, Any]:
    """Edit top-level template fields (parent-only).

    This tool does NOT edit nested milestones/steps/materials/resources —
    delete and recreate the template for structural changes, or edit the
    source project and call ``save_project_as_template`` again.
    """
    require_parent()
    try:
        template = ProjectTemplate.objects.get(pk=params.template_id)
    except ProjectTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    data = params.model_dump(exclude={"template_id"}, exclude_unset=True)
    if "category_id" in data and data["category_id"] is not None:
        try:
            SkillCategory.objects.get(pk=data["category_id"])
        except SkillCategory.DoesNotExist:
            raise MCPValidationError(
                f"category_id {data['category_id']} does not match any category.",
            )
    for field, value in data.items():
        setattr(template, field, value)
    template.save()
    return _template_to_dict(template)


@tool()
@safe_tool
def delete_template(params: DeleteTemplateIn) -> dict[str, Any]:
    """Delete a template and all its nested rows (parent-only)."""
    require_parent()
    try:
        template = ProjectTemplate.objects.get(pk=params.template_id)
    except ProjectTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    template_id = template.pk
    template.delete()
    return {"template_id": template_id, "deleted": True}


@tool()
@safe_tool
def save_project_as_template(params: SaveProjectAsTemplateIn) -> dict[str, Any]:
    """Clone an existing project into a new reusable template (parent-only).

    Copies milestones, materials, steps, and resources verbatim, preserving
    the step→milestone linkage via an internal ID map.
    """
    parent = require_parent()
    try:
        project = Project.objects.get(pk=params.project_id)
    except Project.DoesNotExist:
        raise MCPNotFoundError(f"Project {params.project_id} not found.")

    with transaction.atomic():
        template = ProjectTemplate.objects.create(
            title=project.title,
            description=project.description,
            instructables_url=project.instructables_url,
            difficulty=project.difficulty,
            category=project.category,
            bonus_amount=project.bonus_amount,
            materials_budget=project.materials_budget,
            source_project=project,
            created_by=parent,
            is_public=params.is_public,
        )
        ms_id_map: dict[int, TemplateMilestone] = {}
        for ms in project.milestones.all():
            ms_id_map[ms.id] = TemplateMilestone.objects.create(
                template=template,
                title=ms.title,
                description=ms.description,
                order=ms.order,
                bonus_amount=ms.bonus_amount,
            )
        for mat in project.materials.all():
            TemplateMaterial.objects.create(
                template=template,
                name=mat.name,
                description=mat.description,
                estimated_cost=mat.estimated_cost,
            )
        step_id_map: dict[int, TemplateStep] = {}
        for ps in project.steps.all():
            step_id_map[ps.id] = TemplateStep.objects.create(
                template=template,
                milestone=ms_id_map.get(ps.milestone_id) if ps.milestone_id else None,
                title=ps.title,
                description=ps.description,
                order=ps.order,
            )
        for pr in project.resources.all():
            TemplateResource.objects.create(
                template=template,
                step=step_id_map.get(pr.step_id) if pr.step_id else None,
                title=pr.title,
                url=pr.url,
                resource_type=pr.resource_type,
                order=pr.order,
            )

    return _template_to_dict(template)


@tool()
@safe_tool
def create_project_from_template(
    params: CreateProjectFromTemplateIn,
) -> dict[str, Any]:
    """Spawn a new Project for a child from this template (parent-only).

    The new project starts in ``in_progress`` status. Pass ``title_override``
    to rename the instance (e.g. "Birdhouse (Abby's)").
    """
    parent = require_parent()
    try:
        template = ProjectTemplate.objects.get(pk=params.template_id)
    except ProjectTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    try:
        assignee = User.objects.get(pk=params.assigned_to_id)
    except User.DoesNotExist:
        raise MCPValidationError(
            f"assigned_to_id {params.assigned_to_id} does not match any user.",
        )

    with transaction.atomic():
        project = Project.objects.create(
            title=params.title_override or template.title,
            description=template.description,
            instructables_url=template.instructables_url,
            difficulty=template.difficulty,
            category=template.category,
            bonus_amount=template.bonus_amount,
            materials_budget=template.materials_budget,
            created_by=parent,
            assigned_to=assignee,
            status="in_progress",
        )
        ms_id_map: dict[int, ProjectMilestone] = {}
        for ms in template.milestones.all():
            ms_id_map[ms.id] = ProjectMilestone.objects.create(
                project=project,
                title=ms.title,
                description=ms.description,
                order=ms.order,
                bonus_amount=ms.bonus_amount,
            )
        for mat in template.materials.all():
            MaterialItem.objects.create(
                project=project,
                name=mat.name,
                description=mat.description,
                estimated_cost=mat.estimated_cost,
            )
        step_id_map: dict[int, ProjectStep] = {}
        for ts in template.steps.all():
            step_id_map[ts.id] = ProjectStep.objects.create(
                project=project,
                title=ts.title,
                description=ts.description,
                order=ts.order,
                milestone=ms_id_map.get(ts.milestone_id) if ts.milestone_id else None,
            )
        for tr in template.resources.all():
            ProjectResource.objects.create(
                project=project,
                step=step_id_map.get(tr.step_id) if tr.step_id else None,
                title=tr.title,
                url=tr.url,
                resource_type=tr.resource_type,
                order=tr.order,
            )

    project.refresh_from_db()
    return project_detail_to_dict(project)
