"""Resolve installed reward destinations independently of catalog display names."""
from typing import NamedTuple

from django.db.models import Q, QuerySet

from .models import Skill, SkillCategory


def source_identity_matches(model, lookup):
    """Return at most two actual exact matches, preserving missing versus tied."""
    from apps.rpg.models import RPGContentOverride

    retained = RPGContentOverride.objects.filter(
        model_label=model._meta.label_lower, source_lookup=lookup,
        values___authoring={"version": 1, "source": "mcp"},
    ).values("object_id")
    return list(model.objects.filter(Q(**lookup) | Q(pk__in=retained)).order_by("pk")[:2])


def resolve_source_identity(model, lookup):
    """Return one current or explicitly retained source identity, never a tie.

    Exact versioned authoring provenance lets a renamed or reparented row keep
    its original identity. Current canonical rows without that provenance remain
    compatible with older catalogs. Retirement hides new choices, rather than
    changing an installed reward destination; normal award eligibility still
    applies after resolution.
    """
    matches = source_identity_matches(model, lookup)
    return matches[0] if len(matches) == 1 else None


class ProjectCategoryResolution(NamedTuple):
    category_ids: QuerySet | tuple[int, ...]
    ambiguous: bool = False


def project_category_resolution(name):
    """Preserve current-name unions and identify competing renamed sources."""
    from apps.rpg.models import RPGContentOverride

    if not isinstance(name, str):
        # Keep native ORM coercion for saved legacy current-name selectors.
        # Their original values do not become retained source aliases.
        return ProjectCategoryResolution(SkillCategory.objects.filter(
            name__iexact=name).values_list("pk", flat=True))
    current = SkillCategory.objects.filter(name__iexact=name)
    # A current category's own override is not a competing historical identity.
    # Only genuinely renamed rows need the bounded ambiguity check.
    sources = list(RPGContentOverride.objects.filter(
        model_label="achievements.skillcategory", source_lookup__name__iexact=name,
        values___authoring={"version": 1, "source": "mcp"},
    ).exclude(object_id__in=current.values("pk"))
        .order_by("pk").values_list("object_id", "source_lookup")[:1001])
    if len(sources) > 1000:
        return ProjectCategoryResolution((), ambiguous=True)
    retained_ids = [object_id for object_id, lookup in sources
                    if isinstance(lookup, dict) and set(lookup) == {"name"}
                    and isinstance(lookup["name"], str)]
    retained = tuple(SkillCategory.objects.filter(pk__in=retained_ids)
                     .order_by("pk").values_list("pk", flat=True)[:2])
    if retained:
        if len(retained) == 1 and not current.exists():
            return ProjectCategoryResolution(retained)
        return ProjectCategoryResolution((), ambiguous=True)
    return ProjectCategoryResolution(current.values_list("pk", flat=True))


def resolve_fixed_skill(category_name, skill_name):
    """Resolve the full original category/skill identity, without name fallback."""
    category = resolve_source_identity(SkillCategory, {"name": category_name})
    if category is None:
        return None
    return resolve_source_identity(Skill, {"name": skill_name, "category_id": category.pk})
