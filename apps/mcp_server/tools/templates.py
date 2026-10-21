"""Project template MCP tools (Tier 1.2).

Mirrors the ``/api/templates/`` DRF surface. Templates are reusable
project blueprints — parents can spin a new project from a template for
any child in one call (``create_project_from_template``).
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from django.db import transaction

from apps.achievements.models import Skill, SkillCategory
from apps.projects.models import (
    Project, ProjectTemplate, TemplateAuthoringReceipt, TemplateMaterial,
    TemplateMilestone, TemplateMilestoneSkillTag, TemplateResource, TemplateSkillTag,
    TemplateStep, User,
)
from apps.projects.template_services import instantiate_project_template, save_project_template

from ..context import get_current_user, get_in_family, require_parent, resolve_target_user
from ..errors import MCPNotFoundError, MCPValidationError, safe_tool
from ..template_schemas import (
    CreateProjectFromTemplateIn, CreateTemplateIn, DeleteTemplateIn, GetTemplateIn,
    ListTemplatesIn, SaveProjectAsTemplateIn, UpdateTemplateIn,
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

    Parents see their family's templates; children only see their family's
    public templates. Use ``is_public_only=True`` to filter parents down
    to public.

    Empty result on a fresh family is expected — there is no seed pack
    today. The onramp is ``save_project_as_template`` from a completed
    project; ``create_template`` also accepts a from-scratch payload.

    Audit C8: ``ProjectTemplate`` is per-family content. Without scoping,
    parents saw every household's private templates and children could see
    public templates authored in other families. Both paths now scope by
    ``ProjectTemplate.family``.
    """
    user = get_current_user()
    family_id = getattr(user, "family_id", None)
    if family_id is None:
        return {"templates": [], "count": 0}
    qs = ProjectTemplate.objects.select_related("category", "created_by").filter(
        family_id=family_id,
    )
    if user.role != "parent" or params.is_public_only:
        qs = qs.filter(is_public=True)
    qs = qs.order_by("-created_at")[: params.limit]
    items = [_template_to_dict(t) for t in qs]
    return {"templates": items, "count": len(items)}


@tool()
@safe_tool
def get_template(params: GetTemplateIn) -> dict[str, Any]:
    """Return one template with its milestones, materials, steps, resources.

    Audit C8: scope by ``ProjectTemplate.family``. Children additionally
    require ``is_public=True`` to match the previous semantics.
    """
    user = get_current_user()
    family_id = getattr(user, "family_id", None)
    if family_id is None:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    qs = ProjectTemplate.objects.filter(family_id=family_id)
    if user.role != "parent":
        qs = qs.filter(is_public=True)
    try:
        template = qs.get(pk=params.template_id)
    except ProjectTemplate.DoesNotExist:
        raise MCPNotFoundError(f"Template {params.template_id} not found.")
    return _template_to_dict(template)


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def _validate_content(params, *, template=None):
    """Validate every external reference before changing any saved rows."""
    if params.category_id is not None and not SkillCategory.objects.filter(pk=params.category_id).exists():
        raise MCPValidationError(f"category_id {params.category_id} does not match any category.")
    from apps.rpg.taxonomy_references import admit_references
    admit_references(SkillCategory, [params.category_id] if params.category_id else [],
                     retained_ids=[template.category_id] if template else [])
    all_tags = [params.skill_tags or []]
    if params.milestones is not None:
        all_tags.extend(milestone.skill_tags for milestone in params.milestones)
    for tags in all_tags:
        ids = [tag.skill_id for tag in tags]
        if len(ids) != len(set(ids)):
            raise MCPValidationError("A skill may appear only once in each skill_tags list.")
        missing = set(ids) - set(Skill.objects.filter(pk__in=ids).values_list("pk", flat=True))
        if missing:
            raise MCPValidationError(f"Unknown skill IDs: {sorted(missing)}")
        # Root tags retain their exact saved identities. Replaced nested rows
        # are new plan entries, so their choices must still be available.
        retained = template.skill_tags.values_list("skill_id", flat=True) if template and tags is all_tags[0] else ()
        admit_references(Skill, ids, retained_ids=retained)
    if params.steps is None:
        return
    for index, step in enumerate(params.steps):
        if step.order < 0 or (step.milestone_index is not None and not 0 <= step.milestone_index < len(params.milestones)):
            raise MCPValidationError(f"steps[{index}].milestone_index or order out of range.")
    for index, resource in enumerate(params.resources):
        if resource.order < 0 or (resource.step_index is not None and not 0 <= resource.step_index < len(params.steps)):
            raise MCPValidationError(f"resources[{index}].step_index or order out of range.")
    if any(milestone.order < 0 for milestone in params.milestones):
        raise MCPValidationError("Milestone order cannot be negative.")


def _replace_skill_tags(template, tags):
    template.skill_tags.all().delete()
    TemplateSkillTag.objects.bulk_create([
        TemplateSkillTag(template=template, **tag.model_dump()) for tag in tags
    ])


def _write_structure(template, params):
    milestones = []
    for entry in params.milestones:
        milestone = TemplateMilestone.objects.create(template=template, **entry.model_dump(exclude={"skill_tags"}))
        milestones.append(milestone)
        TemplateMilestoneSkillTag.objects.bulk_create([
            TemplateMilestoneSkillTag(milestone=milestone, **tag.model_dump()) for tag in entry.skill_tags
        ])
    for entry in params.materials:
        TemplateMaterial.objects.create(template=template, **entry.model_dump())
    steps = []
    for entry in params.steps:
        steps.append(TemplateStep.objects.create(
            template=template,
            milestone=milestones[entry.milestone_index] if entry.milestone_index is not None else None,
            **entry.model_dump(exclude={"milestone_index"}),
        ))
    for entry in params.resources:
        TemplateResource.objects.create(
            template=template,
            step=steps[entry.step_index] if entry.step_index is not None else None,
            **entry.model_dump(exclude={"step_index"}),
        )


def _create_once(parent, params, operation, create):
    """Serialize actor retries, retaining immutable responses even after deletion."""
    payload = params.model_dump(mode="json", exclude={"request_id"})
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with transaction.atomic():
        User.objects.select_for_update().get(pk=parent.pk)
        if params.request_id is not None:
            receipt = TemplateAuthoringReceipt.objects.filter(
                actor=parent, operation=operation, request_id=params.request_id,
            ).first()
            if receipt:
                if receipt.family_id != parent.family_id or receipt.fingerprint != fingerprint:
                    raise MCPValidationError("request_id was already used with different inputs or family.")
                return copy.deepcopy(receipt.response)
        response = create()
        if params.request_id is not None:
            TemplateAuthoringReceipt.objects.create(
                actor=parent, family=parent.family, operation=operation,
                request_id=params.request_id, fingerprint=fingerprint, response=response,
            )
        return response


@tool()
@safe_tool
def create_template(params: CreateTemplateIn) -> dict[str, Any]:
    """Create a family template with skill wiring and linked nested content.

    Supply a stable request_id for duplicate-safe retries. Step milestone_index
    and resource step_index refer to zero-based positions in this payload.
    """
    params = CreateTemplateIn.model_validate(params.model_dump())
    parent = require_parent()
    if parent.family_id is None:
        raise MCPValidationError("Calling parent has no family attached.")

    def create():
        _validate_content(params)
        template = ProjectTemplate.objects.create(
            **params.model_dump(exclude={"request_id", "skill_tags", "milestones", "materials", "steps", "resources"}),
            family=parent.family, created_by=parent,
        )
        _replace_skill_tags(template, params.skill_tags)
        _write_structure(template, params)
        return _template_to_dict(template)
    return _create_once(parent, params, "create_template", create)


@tool()
@safe_tool
def update_template(params: UpdateTemplateIn) -> dict[str, Any]:
    """Edit template metadata and skill wiring or atomically replace its plan.

    For structural edits provide all four arrays (milestones, materials, steps,
    resources); [] explicitly clears a section. Omitted metadata is preserved.
    Only this template changes; previously instantiated projects are unchanged.
    """
    params = UpdateTemplateIn.model_validate(params.model_dump(exclude_unset=True))
    parent = require_parent()
    with transaction.atomic():
        User.objects.select_for_update().get(pk=parent.pk)
        template = get_in_family(ProjectTemplate, params.template_id, actor=parent, family_path="family")
        template = ProjectTemplate.objects.select_for_update().get(pk=template.pk, family_id=parent.family_id)
        _validate_content(params, template=template)
        data = params.model_dump(exclude={"template_id", "skill_tags", "milestones", "materials", "steps", "resources"}, exclude_unset=True)
        for field, value in data.items():
            setattr(template, field, value)
        template.save()
        if params.skill_tags is not None:
            _replace_skill_tags(template, params.skill_tags)
        if params.milestones is not None:
            template.resources.all().delete()
            template.steps.all().delete()
            template.milestones.all().delete()
            template.materials.all().delete()
            _write_structure(template, params)
        return _template_to_dict(template)


@tool()
@safe_tool
def delete_template(params: DeleteTemplateIn) -> dict[str, Any]:
    """Delete a family template and its nested rows (parent-only)."""
    parent = require_parent()
    template = get_in_family(ProjectTemplate, params.template_id, actor=parent, family_path="family")
    template_id = template.pk
    template.delete()
    return {"template_id": template_id, "deleted": True}


@tool()
@safe_tool
def save_project_as_template(params: SaveProjectAsTemplateIn) -> dict[str, Any]:
    """Save a family project as a reusable template, preserving all skill tags.

    Homework plans cannot become paid project templates. A stable request_id
    makes retries return the original saved response without another template.
    """
    params = SaveProjectAsTemplateIn.model_validate(params.model_dump())
    parent = require_parent()
    if parent.family_id is None:
        raise MCPValidationError("Calling parent has no family attached.")

    def create():
        project = get_in_family(Project, params.project_id, actor=parent, family_path="assigned_to__family")
        if project.is_homework:
            raise MCPValidationError("Homework plans cannot become paid project templates.")
        return _template_to_dict(save_project_template(project, parent=parent, is_public=params.is_public))
    return _create_once(parent, params, "save_project_as_template", create)


@tool()
@safe_tool
def create_project_from_template(params: CreateProjectFromTemplateIn) -> dict[str, Any]:
    """Instantiate a family template for a child, with skill wiring preserved.

    status=draft supports review before starting; the compatible default remains
    in_progress. A stable request_id prevents duplicate projects on retries.
    """
    params = CreateProjectFromTemplateIn.model_validate(params.model_dump())
    parent = require_parent()

    def create():
        template = get_in_family(ProjectTemplate, params.template_id, actor=parent, family_path="family")
        assignee = resolve_target_user(parent, params.assigned_to_id)
        if assignee.role != "child":
            raise MCPValidationError("assigned_to_id must identify a child in your family.")
        project = instantiate_project_template(
            template, parent=parent, assignee=assignee,
            title=params.title_override, status=params.status,
        )
        return project_detail_to_dict(project)
    return _create_once(parent, params, "create_project_from_template", create)
