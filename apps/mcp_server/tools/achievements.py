"""Achievement-related MCP tools (skill categories, skills, tree, badges)."""
from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.achievements.models import Badge, Skill, UserBadge
from apps.achievements.services import SkillService
from apps.projects.models import SkillCategory, User

from ..context import get_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    GetSkillTreeIn,
    ListBadgesIn,
    ListEarnedBadgesIn,
    ListSkillCategoriesIn,
    ListSkillsIn,
)
from ..server import tool
from ..shapes import (
    badge_to_dict,
    skill_category_to_dict,
    skill_to_dict,
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
