"""Atomic reusable-plan cloning shared by REST and MCP."""
from django.db import transaction
from django.db.models import Q

from apps.achievements.models import MilestoneSkillTag, ProjectSkillTag, Skill, SkillCategory
from apps.rpg.taxonomy_references import admit_references
from .models import (
    MaterialItem, Project, ProjectMilestone, ProjectResource, ProjectStep,
    ProjectTemplate, TemplateMaterial, TemplateMilestone, TemplateMilestoneSkillTag,
    TemplateResource, TemplateSkillTag, TemplateStep,
)


@transaction.atomic
def save_project_template(project, *, parent, is_public=False):
    project = Project.objects.select_for_update(of=("self",)).filter(
        Q(assigned_to__family_id=parent.family_id)
        | Q(assigned_to__isnull=True, created_by__family_id=parent.family_id),
    ).get(pk=project.pk)
    if project.is_homework:
        raise ValueError("Homework plans cannot become paid project templates.")
    _admit_template_choices(project)
    template = ProjectTemplate.objects.create(
        **{field: getattr(project, field) for field in (
            "title", "description", "instructables_url", "difficulty", "category",
            "bonus_amount", "materials_budget",
        )},
        source_project=project, created_by=parent, family=parent.family, is_public=is_public,
    )
    TemplateSkillTag.objects.bulk_create([
        TemplateSkillTag(template=template, skill_id=tag.skill_id, xp_weight=tag.xp_weight)
        for tag in project.skill_tags.all()
    ])
    milestones = {}
    for original in project.milestones.prefetch_related("skill_tags"):
        milestone = TemplateMilestone.objects.create(
            template=template,
            **{field: getattr(original, field) for field in ("title", "description", "order", "bonus_amount")},
        )
        milestones[original.pk] = milestone
        TemplateMilestoneSkillTag.objects.bulk_create([
            TemplateMilestoneSkillTag(milestone=milestone, skill_id=tag.skill_id, xp_amount=tag.xp_amount)
            for tag in original.skill_tags.all()
        ])
    for material in project.materials.all():
        TemplateMaterial.objects.create(
            template=template,
            **{field: getattr(material, field) for field in ("name", "description", "estimated_cost")},
        )
    steps = {}
    for original in project.steps.all():
        steps[original.pk] = TemplateStep.objects.create(
            template=template, milestone=milestones.get(original.milestone_id),
            **{field: getattr(original, field) for field in ("title", "description", "order")},
        )
    for resource in project.resources.all():
        TemplateResource.objects.create(
            template=template, step=steps.get(resource.step_id),
            **{field: getattr(resource, field) for field in ("title", "url", "resource_type", "order")},
        )
    return template


@transaction.atomic
def instantiate_project_template(template, *, parent, assignee, title=None, status="in_progress", allow_public=False):
    visible = Q(family_id=parent.family_id)
    if allow_public:
        visible |= Q(is_public=True)
    template = ProjectTemplate.objects.select_for_update().filter(visible).get(pk=template.pk)
    _admit_template_choices(template)
    project = Project.objects.create(
        **{field: getattr(template, field) for field in (
            "description", "instructables_url", "difficulty", "category", "bonus_amount", "materials_budget",
        )},
        title=title or template.title, assigned_to=assignee, created_by=parent, status=status,
    )
    ProjectSkillTag.objects.bulk_create([
        ProjectSkillTag(project=project, skill_id=tag.skill_id, xp_weight=tag.xp_weight)
        for tag in template.skill_tags.all()
    ])
    milestones = {}
    for original in template.milestones.prefetch_related("skill_tags"):
        milestone = ProjectMilestone.objects.create(
            project=project,
            **{field: getattr(original, field) for field in ("title", "description", "order", "bonus_amount")},
        )
        milestones[original.pk] = milestone
        MilestoneSkillTag.objects.bulk_create([
            MilestoneSkillTag(milestone=milestone, skill_id=tag.skill_id, xp_amount=tag.xp_amount)
            for tag in original.skill_tags.all()
        ])
    for material in template.materials.all():
        MaterialItem.objects.create(
            project=project,
            **{field: getattr(material, field) for field in ("name", "description", "estimated_cost")},
        )
    steps = {}
    for original in template.steps.all():
        steps[original.pk] = ProjectStep.objects.create(
            project=project, milestone=milestones.get(original.milestone_id),
            **{field: getattr(original, field) for field in ("title", "description", "order")},
        )
    for resource in template.resources.all():
        ProjectResource.objects.create(
            project=project, step=steps.get(resource.step_id),
            **{field: getattr(resource, field) for field in ("title", "url", "resource_type", "order")},
        )
    return project


def _admit_template_choices(source):
    """A copied plan creates new references; the saved source stays readable."""
    admit_references(SkillCategory, [source.category_id] if source.category_id else [])
    skill_ids = set(source.skill_tags.values_list("skill_id", flat=True))
    for milestone in source.milestones.all():
        skill_ids.update(milestone.skill_tags.values_list("skill_id", flat=True))
    admit_references(Skill, skill_ids)
