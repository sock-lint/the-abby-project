"""Resolve installed reward destinations independently of catalog display names."""
from django.db.models import Q

from .models import Skill, SkillCategory


def resolve_source_identity(model, lookup):
    """Return one current or explicitly retained source identity, never a tie.

    Exact versioned authoring provenance lets a renamed or reparented row keep
    its original identity. Current canonical rows without that provenance remain
    compatible with older catalogs. Retirement hides new choices, rather than
    changing an installed reward destination; normal award eligibility still
    applies after resolution.
    """
    from apps.rpg.models import RPGContentOverride

    retained = RPGContentOverride.objects.filter(
        model_label=model._meta.label_lower, source_lookup=lookup,
        values___authoring={"version": 1, "source": "mcp"},
    ).values("object_id")
    matches = list(model.objects.filter(Q(**lookup) | Q(pk__in=retained)).order_by("pk")[:2])
    return matches[0] if len(matches) == 1 else None


def resolve_fixed_skill(category_name, skill_name):
    """Resolve the full original category/skill identity, without name fallback."""
    category = resolve_source_identity(SkillCategory, {"name": category_name})
    if category is None:
        return None
    return resolve_source_identity(Skill, {"name": skill_name, "category_id": category.pk})
