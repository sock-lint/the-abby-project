"""Achievement-related MCP tools (skill categories, skills, tree, badges)."""
from __future__ import annotations

from functools import wraps
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.achievements.models import (
    Badge,
    Skill,
    SkillPrerequisite,
    Subject,
    UserBadge,
)
from apps.achievements.services import SkillService
from apps.achievements.taxonomy import (
    available_categories, available_for_new_choices, available_skills, validate_new_taxonomy_references,
)
from apps.achievements.models import SkillCategory
from apps.rpg.content.authoring import (
    direct_catalog_write, natural_lookup, record_direct_override,
    require_catalog_ownership, validate_catalog_object, validate_skill_prerequisites,
)
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.errors import ContentAuthorPermissionDenied
from apps.rpg.content.taxonomy_deletion import IN_USE_DETAIL, TaxonomyInUse, delete_taxonomy

from ..context import get_current_user, resolve_target_user, require_staff_parent
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
from ..legacy_household import household_context
from ..server import tool
from ..shapes import (
    badge_to_dict,
    skill_category_to_dict,
    skill_to_dict,
    user_badge_to_dict,
)


@tool()
@safe_tool
def list_skill_categories(params: ListSkillCategoriesIn) -> dict[str, Any]:
    """List available top-level categories; include_retired keeps saved identities readable."""
    get_current_user()
    categories = SkillCategory.objects.all().order_by("name")
    if not params.include_retired:
        categories = available_categories(categories)
    return {"categories": [skill_category_to_dict(c) for c in categories]}


@tool()
@safe_tool
def list_skills(params: ListSkillsIn) -> dict[str, Any]:
    """Flat list of skills, optionally filtered by category/subject/name."""
    get_current_user()
    qs = Skill.objects.select_related("category", "subject__category")
    if not params.include_retired:
        qs = available_skills(qs)
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
    target = resolve_target_user(user, params.user_id)
    with household_context(user, target, allow_inactive_target=True) as (user, target):

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
    target = resolve_target_user(user, params.user_id)
    with household_context(user, target, allow_inactive_target=True) as (user, target):

        earned = list(
            UserBadge.objects.select_related("badge").filter(user=target)
            .order_by("-earned_at")
        )
        return {"earned": [user_badge_to_dict(ub) for ub in earned]}


# ---------------------------------------------------------------------------
# Tier 2.1: Skill-tree taxonomy authoring (staff-parent-only writes)
# ---------------------------------------------------------------------------


def _subject_to_dict(subject: Subject) -> dict[str, Any]:
    return {
        "id": subject.id,
        "name": subject.name,
        "category_id": subject.category_id,
        "description": subject.description,
        "icon": subject.icon,
        "order": subject.order,
        "is_retired": subject.is_retired,
        "available_for_new_choices": available_for_new_choices(subject),
    }


# ---- Category ------------------------------------------------------------


def _delete_taxonomy(actor, model, object_id):
    try:
        delete_taxonomy(actor, model, object_id)
    except TaxonomyInUse:
        raise MCPValidationError(IN_USE_DETAIL, code="taxonomy_in_use") from None


def _direct_authoring(function):
    """Give legacy direct tools the same catalog fence and durable ownership."""
    models = {"category": SkillCategory, "subject": Subject, "skill": Skill, "badge": Badge}
    if function.__name__ in {"add_skill_prerequisite", "remove_skill_prerequisite"}:
        kind, creating = "skill", False
    else:
        action, kind = function.__name__.split("_", 1)
        creating = action == "create"
    model = models[kind]

    @wraps(function)
    def wrapped(params):
        actor = require_staff_parent()
        try:
            with direct_catalog_write(actor) as fresh_actor:
                original, before = None, None
                if not creating:
                    original = model.objects.filter(pk=getattr(params, f"{kind}_id")).first()
                    if original is not None:
                        require_catalog_ownership(fresh_actor, original)
                        before = natural_lookup(original)
                result = function(params)
                result_id = result["id"] if creating else original.pk if original is not None else None
                current = model.objects.filter(pk=result_id).first()
                if current is not None:
                    validate_catalog_object(current)
                    if kind == "skill":
                        validate_skill_prerequisites(current)
                    record_direct_override(fresh_actor, current, before or natural_lookup(current))
                return result
        except ContentAuthorPermissionDenied as error:
            raise MCPPermissionDenied(str(error)) from error
        except ContentPackError as error:
            raise MCPValidationError(str(error)) from error
        except IntegrityError as error:
            raise MCPValidationError("The catalog update conflicts with an existing name or prerequisite.") from error

    return wrapped


@tool()
@safe_tool
@_direct_authoring
def create_category(params: CreateCategoryIn) -> dict[str, Any]:
    """Create a new skill category (staff-parent-only)."""
    require_staff_parent()
    if SkillCategory.objects.filter(name=params.name).exists():
        raise MCPValidationError(
            f"A category named {params.name!r} already exists.",
        )
    category = SkillCategory(
        name=params.name,
        icon=params.icon,
        color=params.color,
        description=params.description,
        is_retired=params.is_retired,
    )
    validate_catalog_object(category)
    category.save()
    return skill_category_to_dict(category)


@tool()
@safe_tool
@_direct_authoring
def update_category(params: UpdateCategoryIn) -> dict[str, Any]:
    """Edit a skill category (staff-parent-only)."""
    require_staff_parent()
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
    validate_catalog_object(category)
    category.save()
    return skill_category_to_dict(category)


@tool()
@safe_tool
def delete_category(params: DeleteCategoryIn) -> dict[str, Any]:
    """Delete an unused, unmanaged category; references and saved history block deletion."""
    _delete_taxonomy(require_staff_parent(), SkillCategory, params.category_id)
    return {"category_id": params.category_id, "deleted": True}


# ---- Subject -------------------------------------------------------------


@tool()
@safe_tool
@_direct_authoring
def create_subject(params: CreateSubjectIn) -> dict[str, Any]:
    """Create a subject inside a category (staff-parent-only).

    A subject is the middle layer between Category and Skill. Used to group
    related skills in the skill tree (e.g., "Measuring & Layout" inside
    "Woodworking").
    """
    require_staff_parent()
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
    subject = Subject(
        category=category,
        name=params.name,
        description=params.description,
        icon=params.icon,
        order=params.order,
        is_retired=params.is_retired,
    )
    validate_catalog_object(subject)
    subject.save()
    return _subject_to_dict(subject)


@tool()
@safe_tool
@_direct_authoring
def update_subject(params: UpdateSubjectIn) -> dict[str, Any]:
    """Edit a subject (staff-parent-only)."""
    require_staff_parent()
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
    validate_catalog_object(subject)
    subject.save()
    return _subject_to_dict(subject)


@tool()
@safe_tool
def delete_subject(params: DeleteSubjectIn) -> dict[str, Any]:
    """Delete an unused, unmanaged subject without detaching skills or badges."""
    _delete_taxonomy(require_staff_parent(), Subject, params.subject_id)
    return {"subject_id": params.subject_id, "deleted": True}


# ---- Skill ---------------------------------------------------------------


@tool()
@safe_tool
@_direct_authoring
def create_skill(params: CreateSkillIn) -> dict[str, Any]:
    """Create a skill inside a category/subject (staff-parent-only).

    Optionally pass ``prerequisites`` to wire up SkillPrerequisite rows in
    one call — each entry is ``{required_skill_id, required_level}``.
    """
    require_staff_parent()
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
        skill = Skill(
            category=category,
            subject=subject,
            name=params.name,
            description=params.description,
            icon=params.icon,
            level_names=params.level_names,
            is_locked_by_default=params.is_locked_by_default,
            order=params.order,
            is_retired=params.is_retired,
        )
        validate_catalog_object(skill)
        skill.save()
        if params.prerequisites:
            prereq_ids = [p.required_skill_id for p in params.prerequisites]
            validate_new_taxonomy_references(Skill, prereq_ids)
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
@_direct_authoring
def update_skill(params: UpdateSkillIn) -> dict[str, Any]:
    """Edit a skill (staff-parent-only).

    Pass ``clear_subject=True`` to detach a skill from its current subject
    (keeping its category).
    """
    require_staff_parent()
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
    validate_catalog_object(skill)
    skill.save()
    return skill_to_dict(skill)


@tool()
@safe_tool
def delete_skill(params: DeleteSkillIn) -> dict[str, Any]:
    """Delete an unused, unmanaged skill; progress, tags and saved promises are preserved."""
    _delete_taxonomy(require_staff_parent(), Skill, params.skill_id)
    return {"skill_id": params.skill_id, "deleted": True}


@tool()
@safe_tool
@_direct_authoring
def add_skill_prerequisite(params: AddSkillPrerequisiteIn) -> dict[str, Any]:
    """Add a prerequisite to a skill (staff-parent-only).

    Idempotent: if a row for this (skill, required_skill) already exists,
    the required_level is updated to the new value.
    """
    require_staff_parent()
    if params.skill_id == params.required_skill_id:
        raise MCPValidationError("A skill cannot require itself.")
    if not Skill.objects.filter(pk=params.skill_id).exists():
        raise MCPNotFoundError(f"Skill {params.skill_id} not found.")
    if not Skill.objects.filter(pk=params.required_skill_id).exists():
        raise MCPValidationError(
            f"required_skill_id {params.required_skill_id} not found.",
        )
    validate_new_taxonomy_references(Skill, [params.required_skill_id], retained_ids=SkillPrerequisite.objects.filter(
        skill_id=params.skill_id).values_list("required_skill_id", flat=True))
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
@_direct_authoring
def remove_skill_prerequisite(params: RemoveSkillPrerequisiteIn) -> dict[str, Any]:
    """Remove a prerequisite edge from the skill graph (staff-parent-only)."""
    require_staff_parent()
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
@_direct_authoring
def create_badge(params: CreateBadgeIn) -> dict[str, Any]:
    """Create a badge with a criteria rule (staff-parent-only).

    ``criteria_type`` uses the complete runtime criterion vocabulary.
    ``criteria_value`` is a JSON dict whose
    shape depends on the type (e.g. ``{"count": 5}`` for
    ``projects_completed``, ``{"category_id": 3, "count": 3}`` for
    ``category_projects``).
    """
    require_staff_parent()
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
    badge = Badge(
        name=params.name,
        description=params.description,
        icon=params.icon,
        subject=subject,
        criteria_type=params.criteria_type,
        criteria_value=params.criteria_value,
        xp_bonus=params.xp_bonus,
        rarity=params.rarity,
        award_coins=params.award_coins,
    )
    validate_catalog_object(badge)
    badge.save()
    return badge_to_dict(badge)


@tool()
@safe_tool
@_direct_authoring
def update_badge(params: UpdateBadgeIn) -> dict[str, Any]:
    """Edit a badge (staff-parent-only)."""
    require_staff_parent()
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
    validate_catalog_object(badge)
    badge.save()
    return badge_to_dict(badge)


@tool()
@safe_tool
def delete_badge(params: DeleteBadgeIn) -> dict[str, Any]:
    """Delete an unused, unmanaged badge without removing recognition or quest gates."""
    _delete_taxonomy(require_staff_parent(), Badge, params.badge_id)
    return {"badge_id": params.badge_id, "deleted": True}
