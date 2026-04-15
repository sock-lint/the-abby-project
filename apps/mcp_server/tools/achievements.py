"""Achievement-related MCP tools (skill categories, skills, tree, badges)."""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Q

from apps.achievements.models import (
    Badge,
    Skill,
    SkillPrerequisite,
    Subject,
    UserBadge,
)
from apps.achievements.services import SkillService
from apps.achievements.models import SkillCategory
from apps.projects.models import User

from ..context import get_current_user, require_parent
from ..errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
    safe_tool,
)
from ..schemas import (
    AddSkillPrerequisiteIn,
    CreateBadgeIn,
    CreateCategoryIn,
    CreateSkillIn,
    CreateSubjectIn,
    DeleteBadgeIn,
    DeleteCategoryIn,
    DeleteSkillIn,
    DeleteSubjectIn,
    GetSkillTreeIn,
    ListBadgesIn,
    ListEarnedBadgesIn,
    ListSkillCategoriesIn,
    ListSkillsIn,
    RemoveSkillPrerequisiteIn,
    UpdateBadgeIn,
    UpdateCategoryIn,
    UpdateSkillIn,
    UpdateSubjectIn,
)
from ..server import tool
from ..shapes import (
    badge_to_dict,
    skill_category_to_dict,
    skill_to_dict,
    to_plain,
    user_badge_to_dict,
)


def _resolve_target(user, requested_id: int | None) -> User:
    if requested_id is None or requested_id == user.id:
        return user
    if user.role != "parent":
        raise MCPPermissionDenied("Children can only view their own achievements.")
    try:
        return User.objects.get(pk=requested_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {requested_id} not found.")


@tool()
@safe_tool
def list_skill_categories(params: ListSkillCategoriesIn) -> dict[str, Any]:
    """List all top-level skill categories."""
    del params  # schema has no fields
    get_current_user()
    categories = list(SkillCategory.objects.all().order_by("name"))
    return {"categories": [skill_category_to_dict(c) for c in categories]}


@tool()
@safe_tool
def list_skills(params: ListSkillsIn) -> dict[str, Any]:
    """Flat list of skills, optionally filtered by category/subject/name."""
    get_current_user()
    qs = Skill.objects.select_related("category", "subject")
    if params.category_id is not None:
        qs = qs.filter(category_id=params.category_id)
    if params.subject_id is not None:
        qs = qs.filter(subject_id=params.subject_id)
    if params.q:
        qs = qs.filter(Q(name__icontains=params.q) | Q(description__icontains=params.q))
    qs = qs.order_by("category__name", "subject__name", "order", "name")[: params.limit]
    return {"skills": [skill_to_dict(s) for s in qs]}


@tool()
@safe_tool
def get_skill_tree(params: GetSkillTreeIn) -> dict[str, Any]:
    """Full nested skill tree for a category with the target user's progress."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    try:
        category = SkillCategory.objects.get(pk=params.category_id)
    except SkillCategory.DoesNotExist:
        raise MCPNotFoundError(f"Category {params.category_id} not found.")

    tree = SkillService.get_skill_tree(target, category)
    return {
        "category": skill_category_to_dict(category),
        "user_id": target.id,
        "subjects": tree,
    }


@tool()
@safe_tool
def list_badges(params: ListBadgesIn) -> dict[str, Any]:
    """List all defined badges, optionally filtered by rarity."""
    get_current_user()
    qs = Badge.objects.all()
    if params.rarity:
        qs = qs.filter(rarity=params.rarity)
    return {"badges": [badge_to_dict(b) for b in qs.order_by("rarity", "name")]}


@tool()
@safe_tool
def list_earned_badges(params: ListEarnedBadgesIn) -> dict[str, Any]:
    """List badges the target user has earned, newest first."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    earned = list(
        UserBadge.objects.select_related("badge").filter(user=target)
        .order_by("-earned_at")
    )
    return {"earned": [user_badge_to_dict(ub) for ub in earned]}


# ---------------------------------------------------------------------------
# Tier 2.1: Skill-tree taxonomy authoring (parent-only writes)
# ---------------------------------------------------------------------------


def _subject_to_dict(subject: Subject) -> dict[str, Any]:
    return {
        "id": subject.id,
        "name": subject.name,
        "category_id": subject.category_id,
        "description": subject.description,
        "icon": subject.icon,
        "order": subject.order,
    }


# ---- Category ------------------------------------------------------------


@tool()
@safe_tool
def create_category(params: CreateCategoryIn) -> dict[str, Any]:
    """Create a new skill category (parent-only)."""
    require_parent()
    if SkillCategory.objects.filter(name=params.name).exists():
        raise MCPValidationError(
            f"A category named {params.name!r} already exists.",
        )
    category = SkillCategory.objects.create(
        name=params.name,
        icon=params.icon,
        color=params.color,
        description=params.description,
    )
    return skill_category_to_dict(category)


@tool()
@safe_tool
def update_category(params: UpdateCategoryIn) -> dict[str, Any]:
    """Edit a skill category (parent-only)."""
    require_parent()
    try:
        category = SkillCategory.objects.get(pk=params.category_id)
    except SkillCategory.DoesNotExist:
        raise MCPNotFoundError(f"Category {params.category_id} not found.")
    data = params.model_dump(exclude={"category_id"}, exclude_unset=True)
    if "name" in data and SkillCategory.objects.filter(
        name=data["name"],
    ).exclude(pk=category.pk).exists():
        raise MCPValidationError(
            f"Another category is already named {data['name']!r}.",
        )
    for field, value in data.items():
        setattr(category, field, value)
    category.save()
    return skill_category_to_dict(category)


@tool()
@safe_tool
def delete_category(params: DeleteCategoryIn) -> dict[str, Any]:
    """Delete a skill category. Cascades to subjects, skills, and dependent rows.

    Parent-only. Use with care — projects tagged to this category will
    have ``category=None`` (SET_NULL on Project.category).
    """
    require_parent()
    try:
        category = SkillCategory.objects.get(pk=params.category_id)
    except SkillCategory.DoesNotExist:
        raise MCPNotFoundError(f"Category {params.category_id} not found.")
    category_id = category.pk
    category.delete()
    return {"category_id": category_id, "deleted": True}


# ---- Subject -------------------------------------------------------------


@tool()
@safe_tool
def create_subject(params: CreateSubjectIn) -> dict[str, Any]:
    """Create a subject inside a category (parent-only).

    A subject is the middle layer between Category and Skill. Used to group
    related skills in the skill tree (e.g., "Measuring & Layout" inside
    "Woodworking").
    """
    require_parent()
    try:
        category = SkillCategory.objects.get(pk=params.category_id)
    except SkillCategory.DoesNotExist:
        raise MCPValidationError(
            f"category_id {params.category_id} does not match any category.",
        )
    if Subject.objects.filter(category=category, name=params.name).exists():
        raise MCPValidationError(
            f"Subject {params.name!r} already exists in this category.",
        )
    subject = Subject.objects.create(
        category=category,
        name=params.name,
        description=params.description,
        icon=params.icon,
        order=params.order,
    )
    return _subject_to_dict(subject)


@tool()
@safe_tool
def update_subject(params: UpdateSubjectIn) -> dict[str, Any]:
    """Edit a subject (parent-only)."""
    require_parent()
    try:
        subject = Subject.objects.get(pk=params.subject_id)
    except Subject.DoesNotExist:
        raise MCPNotFoundError(f"Subject {params.subject_id} not found.")
    data = params.model_dump(exclude={"subject_id"}, exclude_unset=True)
    if "category_id" in data:
        try:
            subject.category = SkillCategory.objects.get(pk=data["category_id"])
        except SkillCategory.DoesNotExist:
            raise MCPValidationError(
                f"category_id {data['category_id']} does not match any category.",
            )
        del data["category_id"]
    for field, value in data.items():
        setattr(subject, field, value)
    subject.save()
    return _subject_to_dict(subject)


@tool()
@safe_tool
def delete_subject(params: DeleteSubjectIn) -> dict[str, Any]:
    """Delete a subject. Skills in it keep their category but lose the subject FK (SET_NULL). Parent-only."""
    require_parent()
    try:
        subject = Subject.objects.get(pk=params.subject_id)
    except Subject.DoesNotExist:
        raise MCPNotFoundError(f"Subject {params.subject_id} not found.")
    subject_id = subject.pk
    subject.delete()
    return {"subject_id": subject_id, "deleted": True}


# ---- Skill ---------------------------------------------------------------


@tool()
@safe_tool
def create_skill(params: CreateSkillIn) -> dict[str, Any]:
    """Create a skill inside a category/subject (parent-only).

    Optionally pass ``prerequisites`` to wire up SkillPrerequisite rows in
    one call — each entry is ``{required_skill_id, required_level}``.
    """
    require_parent()
    try:
        category = SkillCategory.objects.get(pk=params.category_id)
    except SkillCategory.DoesNotExist:
        raise MCPValidationError(
            f"category_id {params.category_id} does not match any category.",
        )
    subject = None
    if params.subject_id is not None:
        try:
            subject = Subject.objects.get(pk=params.subject_id)
        except Subject.DoesNotExist:
            raise MCPValidationError(
                f"subject_id {params.subject_id} does not match any subject.",
            )
    if Skill.objects.filter(category=category, name=params.name).exists():
        raise MCPValidationError(
            f"Skill {params.name!r} already exists in this category.",
        )
    with transaction.atomic():
        skill = Skill.objects.create(
            category=category,
            subject=subject,
            name=params.name,
            description=params.description,
            icon=params.icon,
            level_names=params.level_names,
            is_locked_by_default=params.is_locked_by_default,
            order=params.order,
        )
        if params.prerequisites:
            prereq_ids = [p.required_skill_id for p in params.prerequisites]
            known = set(
                Skill.objects.filter(id__in=prereq_ids).values_list("id", flat=True)
            )
            missing = [pid for pid in prereq_ids if pid not in known]
            if missing:
                raise MCPValidationError(
                    f"Unknown required_skill_id(s): {missing}",
                )
            SkillPrerequisite.objects.bulk_create([
                SkillPrerequisite(
                    skill=skill,
                    required_skill_id=p.required_skill_id,
                    required_level=p.required_level,
                )
                for p in params.prerequisites
            ])
    return skill_to_dict(skill)


@tool()
@safe_tool
def update_skill(params: UpdateSkillIn) -> dict[str, Any]:
    """Edit a skill (parent-only).

    Pass ``clear_subject=True`` to detach a skill from its current subject
    (keeping its category).
    """
    require_parent()
    try:
        skill = Skill.objects.get(pk=params.skill_id)
    except Skill.DoesNotExist:
        raise MCPNotFoundError(f"Skill {params.skill_id} not found.")
    data = params.model_dump(
        exclude={
            "skill_id", "category_id", "subject_id", "clear_subject",
        },
        exclude_unset=True,
    )
    if params.category_id is not None:
        try:
            skill.category = SkillCategory.objects.get(pk=params.category_id)
        except SkillCategory.DoesNotExist:
            raise MCPValidationError(
                f"category_id {params.category_id} does not match any category.",
            )
    if params.clear_subject:
        skill.subject = None
    elif params.subject_id is not None:
        try:
            skill.subject = Subject.objects.get(pk=params.subject_id)
        except Subject.DoesNotExist:
            raise MCPValidationError(
                f"subject_id {params.subject_id} does not match any subject.",
            )
    for field, value in data.items():
        setattr(skill, field, value)
    skill.save()
    return skill_to_dict(skill)


@tool()
@safe_tool
def delete_skill(params: DeleteSkillIn) -> dict[str, Any]:
    """Delete a skill (parent-only). Cascades to SkillPrerequisite + SkillProgress + tags."""
    require_parent()
    try:
        skill = Skill.objects.get(pk=params.skill_id)
    except Skill.DoesNotExist:
        raise MCPNotFoundError(f"Skill {params.skill_id} not found.")
    skill_id = skill.pk
    skill.delete()
    return {"skill_id": skill_id, "deleted": True}


@tool()
@safe_tool
def add_skill_prerequisite(params: AddSkillPrerequisiteIn) -> dict[str, Any]:
    """Add a prerequisite to a skill (parent-only).

    Idempotent: if a row for this (skill, required_skill) already exists,
    the required_level is updated to the new value.
    """
    require_parent()
    if params.skill_id == params.required_skill_id:
        raise MCPValidationError("A skill cannot require itself.")
    if not Skill.objects.filter(pk=params.skill_id).exists():
        raise MCPNotFoundError(f"Skill {params.skill_id} not found.")
    if not Skill.objects.filter(pk=params.required_skill_id).exists():
        raise MCPValidationError(
            f"required_skill_id {params.required_skill_id} not found.",
        )
    obj, created = SkillPrerequisite.objects.update_or_create(
        skill_id=params.skill_id,
        required_skill_id=params.required_skill_id,
        defaults={"required_level": params.required_level},
    )
    return {
        "prerequisite_id": obj.id,
        "skill_id": obj.skill_id,
        "required_skill_id": obj.required_skill_id,
        "required_level": obj.required_level,
        "created": created,
    }


@tool()
@safe_tool
def remove_skill_prerequisite(params: RemoveSkillPrerequisiteIn) -> dict[str, Any]:
    """Remove a prerequisite edge from the skill graph (parent-only)."""
    require_parent()
    deleted, _ = SkillPrerequisite.objects.filter(
        skill_id=params.skill_id,
        required_skill_id=params.required_skill_id,
    ).delete()
    if not deleted:
        raise MCPNotFoundError("Prerequisite edge not found.")
    return {
        "skill_id": params.skill_id,
        "required_skill_id": params.required_skill_id,
        "deleted": True,
    }


# ---- Badge ---------------------------------------------------------------


@tool()
@safe_tool
def create_badge(params: CreateBadgeIn) -> dict[str, Any]:
    """Create a badge with a criteria rule (parent-only).

    ``criteria_type`` is one of the 17 evaluator types — see the
    ``BadgeCriteriaType`` enum. ``criteria_value`` is a JSON dict whose
    shape depends on the type (e.g. ``{"count": 5}`` for
    ``projects_completed``, ``{"category_id": 3, "count": 3}`` for
    ``category_projects``).
    """
    require_parent()
    if Badge.objects.filter(name=params.name).exists():
        raise MCPValidationError(f"A badge named {params.name!r} already exists.")
    subject = None
    if params.subject_id is not None:
        try:
            subject = Subject.objects.get(pk=params.subject_id)
        except Subject.DoesNotExist:
            raise MCPValidationError(
                f"subject_id {params.subject_id} does not match any subject.",
            )
    badge = Badge.objects.create(
        name=params.name,
        description=params.description,
        icon=params.icon,
        subject=subject,
        criteria_type=params.criteria_type,
        criteria_value=params.criteria_value,
        xp_bonus=params.xp_bonus,
        rarity=params.rarity,
    )
    return badge_to_dict(badge)


@tool()
@safe_tool
def update_badge(params: UpdateBadgeIn) -> dict[str, Any]:
    """Edit a badge (parent-only)."""
    require_parent()
    try:
        badge = Badge.objects.get(pk=params.badge_id)
    except Badge.DoesNotExist:
        raise MCPNotFoundError(f"Badge {params.badge_id} not found.")
    data = params.model_dump(
        exclude={"badge_id", "subject_id", "clear_subject"},
        exclude_unset=True,
    )
    if params.clear_subject:
        badge.subject = None
    elif params.subject_id is not None:
        try:
            badge.subject = Subject.objects.get(pk=params.subject_id)
        except Subject.DoesNotExist:
            raise MCPValidationError(
                f"subject_id {params.subject_id} does not match any subject.",
            )
    if "name" in data and Badge.objects.filter(name=data["name"]).exclude(
        pk=badge.pk,
    ).exists():
        raise MCPValidationError(
            f"Another badge is already named {data['name']!r}.",
        )
    for field, value in data.items():
        setattr(badge, field, value)
    badge.save()
    return badge_to_dict(badge)


@tool()
@safe_tool
def delete_badge(params: DeleteBadgeIn) -> dict[str, Any]:
    """Delete a badge definition. UserBadge rows referencing it cascade. Parent-only."""
    require_parent()
    try:
        badge = Badge.objects.get(pk=params.badge_id)
    except Badge.DoesNotExist:
        raise MCPNotFoundError(f"Badge {params.badge_id} not found.")
    badge_id = badge.pk
    badge.delete()
    return {"badge_id": badge_id, "deleted": True}
