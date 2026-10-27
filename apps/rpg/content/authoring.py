"""Validated direct catalog edits with exact, durable source identities.

This module owns no publication permissions. Callers enter the catalog write
transaction with a staff parent, validate their merged candidate, then retain
its original source lookup so ordinary content reloads preserve the edit.
"""
from __future__ import annotations

from contextlib import contextmanager
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Value

from apps.achievements.models import Skill, SkillCategory, SkillPrerequisite, Subject
from apps.achievements.taxonomy import validate_new_taxonomy_references
from apps.families.models import Family
from apps.rpg.models import ContentPackEntry, RPGContentOverride

from .loader import ContentPackError
from .errors import ContentAuthorPermissionDenied
from .publication import _catalog_lock
from .validation import validate_badge_criteria


AUTHORING_MODELS = frozenset({
    "achievements.skillcategory", "achievements.subject", "achievements.skill", "achievements.badge",
})


@contextmanager
def direct_catalog_write(actor):
    """Serialize direct writes with reviewed publication and baseline loads."""
    with transaction.atomic():
        family = Family.objects.select_for_update(no_key=True).filter(pk=actor.family_id).first()
        if family is None:
            raise ContentAuthorPermissionDenied("Direct catalog authoring requires a current active staff parent and family.")
        fresh = get_user_model().objects.select_for_update(no_key=True).filter(
            pk=actor.pk, family_id=actor.family_id, is_active=True, is_staff=True, role="parent",
        ).first()
        if fresh is None or fresh.family_id is None:
            raise ContentAuthorPermissionDenied("Direct catalog authoring requires a current active staff parent and family.")
        _catalog_lock()
        yield fresh


def require_catalog_ownership(actor, obj):
    """Global visibility does not grant another family's pack ownership."""
    identity = {"model_label": obj._meta.label_lower, "object_id": obj.pk}
    if (ContentPackEntry.objects.filter(**identity).exclude(family_id=actor.family_id).exists()
            or RPGContentOverride.objects.filter(**identity).exclude(family_id=actor.family_id).exists()):
        raise ContentAuthorPermissionDenied("This catalog entry is authored by another family and is read-only here.")


def natural_lookup(obj):
    """Names plus the complete owning taxonomy identity, captured pre-edit."""
    lookup = {"name": obj.name}
    if obj._meta.label_lower in {"achievements.subject", "achievements.skill"}:
        lookup["category_id"] = obj.category_id
    return lookup


def _canonical_lookup(model, lookup):
    result = {}
    for name, value in lookup.items():
        field = model._meta.get_field(name)
        result[field.attname] = value.pk if hasattr(value, "_meta") else value
    return result


def _validate_category_alias_reuse(obj):
    # Existing members of a current-name union can keep their namespace. Only
    # a genuinely renamed source reserves a new incoming case-insensitive name.
    current = SkillCategory.objects.filter(name__iexact=obj.name)
    if obj.pk and current.filter(pk=obj.pk).exists():
        return
    sources = RPGContentOverride.objects.filter(
        model_label="achievements.skillcategory",
        source_lookup__name__iexact=obj.name,
        values___authoring={"version": 1, "source": "mcp"},
    ).exclude(object_id=obj.pk).exclude(object_id__in=current.values("pk"))
    for source in sources:
        if (isinstance(source.source_lookup, dict)
                and set(source.source_lookup) == {"name"}
                and isinstance(source.source_lookup["name"], str)
                and SkillCategory.objects.filter(pk=source.object_id).exists()):
            raise ContentPackError("This category name is retained by another renamed entry; choose another name.")


def _validate_direct_category_source(obj, previous):
    """Predict the first source that record_direct_override will preserve."""
    if previous is None:
        return
    source = RPGContentOverride.objects.filter(
        model_label="achievements.skillcategory", object_id=obj.pk,
    ).first()
    lookup = source.source_lookup if source else natural_lookup(previous)
    if not isinstance(lookup, dict) or set(lookup) != {"name"} or not isinstance(lookup["name"], str):
        return
    name = lookup["name"]
    # Let the database apply the same iexact semantics used by native payouts,
    # including backend-specific Unicode comparisons, to the candidate name.
    if SkillCategory.objects.filter(pk=obj.pk).annotate(
        _candidate_name=Value(obj.name),
    ).filter(_candidate_name__iexact=name).exists():
        return
    if not SkillCategory.objects.filter(name__iexact=name).exclude(pk=obj.pk).exists():
        return
    was_retained = not SkillCategory.objects.filter(pk=obj.pk, name__iexact=name).exists()
    was_valid = source and RPGContentOverride.objects.filter(
        pk=source.pk, values___authoring={"version": 1, "source": "mcp"},
    ).exists()
    if was_retained and was_valid:
        # Already-persisted ambiguity keeps the established fail-closed policy;
        # unrelated metadata/retirement edits do not introduce a new conflict.
        return
    raise ContentPackError("This edit would retain a category name used by another current entry; choose another name.")


def validate_source_identity(obj):
    """Keep current names disjoint from another object's retained source name.

    Publication and direct writers hold the shared catalog lock before this
    check and the following save. Draft validation also runs it as a preflight;
    preview/publication repeat validation under that same lock.
    """
    label = obj._meta.label_lower
    if label not in AUTHORING_MODELS | {"quests.questdefinition"}:
        return
    if label == "achievements.skillcategory":
        _validate_category_alias_reuse(obj)
    lookup = natural_lookup(obj)
    sources = RPGContentOverride.objects.filter(model_label=label).exclude(object_id=obj.pk)
    if label == "quests.questdefinition":
        # Retired aliases and private templates do not participate in the
        # loader's global source-name resolution.
        sources = sources.filter(object_id__in=type(obj).objects.filter(
            is_system=True, created_by__isnull=True, superseded_by__isnull=True,
        ).values("pk"))
    for name, value in lookup.items():
        sources = sources.filter(**{f"source_lookup__{name}": value})
    for source in sources:
        if source.source_lookup != lookup:
            continue
        if label in AUTHORING_MODELS and source.values.get("_authoring") != {"version": 1, "source": "mcp"}:
            continue
        raise ContentPackError("This source identity is retained by another authored entry; choose another name.")


def validate_catalog_object(obj):
    """Validate the final candidate, including relationships retained by PATCH."""
    # Request serializers may have resolved relations before the catalog fence.
    # Re-read parents under that fence before comparing their current ancestry.
    obj._state.fields_cache.clear()
    label = obj._meta.label_lower
    validate_source_identity(obj)
    previous = type(obj).objects.filter(pk=obj.pk).first() if obj.pk else None
    if label == "achievements.skillcategory":
        _validate_direct_category_source(obj, previous)
    try:
        if label in {"achievements.skill", "achievements.subject"}:
            validate_new_taxonomy_references(SkillCategory, [obj.category_id],
                retained_ids=[previous.category_id] if previous else ())
        if label in {"achievements.skill", "achievements.badge"} and obj.subject_id:
            validate_new_taxonomy_references(Subject, [obj.subject_id],
                retained_ids=[previous.subject_id] if previous else ())
    except ValidationError as error:
        raise ContentPackError("; ".join(error.messages)) from error
    if label == "achievements.skill":
        if obj.subject_id is not None and obj.subject.category_id != obj.category_id:
            raise ContentPackError("The skill and its subject must belong to the same category; clear or replace the subject first.")
        if not isinstance(obj.level_names, dict) or any(not isinstance(value, str) for value in obj.level_names.values()):
            raise ContentPackError("Skill level_names must map level names to text.")
    if label == "achievements.subject" and obj.pk and Skill.objects.filter(subject_id=obj.pk).exclude(category_id=obj.category_id).exists():
        raise ContentPackError("Move or detach this subject's skills before changing its category.")
    if label == "achievements.badge":
        try:
            validate_badge_criteria(obj.criteria_type, obj.criteria_value)
        except ValidationError as error:
            raise ContentPackError("; ".join(error.messages)) from error
    try:
        # Empty dictionaries are valid runtime rules/names. A blank badge
        # description remains compatible with the existing MCP text contract.
        excluded = ["level_names"] if label == "achievements.skill" else []
        if label == "achievements.badge":
            excluded = ["criteria_value", "description"]
        obj.full_clean(exclude=excluded)
    except ValidationError as error:
        raise ContentPackError("; ".join(error.messages)) from error


def validate_skill_prerequisites(skill):
    """Reject cycles through the changed skill across the complete saved graph.

    No page limit can hide a distant return path. Unrelated historical cycles
    do not prevent incremental repairs to a different part of the graph.
    """
    graph = {}
    for source, target in SkillPrerequisite.objects.values_list("skill_id", "required_skill_id"):
        graph.setdefault(source, []).append(target)
    pending, seen = list(graph.get(skill.pk, ())), set()
    while pending:
        node = pending.pop()
        if node == skill.pk:
            raise ContentPackError("Skill prerequisites cannot contain a cycle.")
        if node not in seen:
            seen.add(node)
            pending.extend(graph.get(node, ()))


def record_direct_override(actor, obj, before_lookup):
    """Keep the first source identity and a versioned canonical value snapshot."""
    require_catalog_ownership(actor, obj)
    identity = {"model_label": obj._meta.label_lower, "object_id": obj.pk}
    previous = RPGContentOverride.objects.filter(**identity).first()
    if previous is None:
        # A renamed source keeps its original identity. Reusing that identity
        # for a second row would make a later bundled reload ambiguous.
        candidates = RPGContentOverride.objects.filter(model_label=obj._meta.label_lower).exclude(object_id=obj.pk)
        for key, value in before_lookup.items():
            candidates = candidates.filter(**{f"source_lookup__{key}": value})
        if any(row.source_lookup == before_lookup and row.values.get("_authoring") == {"version": 1, "source": "mcp"} for row in candidates):
            raise ContentPackError("This source identity is retained by an earlier authored entry; choose another name.")
    values = {field.attname: getattr(obj, field.attname) for field in obj._meta.concrete_fields if not field.primary_key}
    values["_authoring"] = {"version": 1, "source": "mcp"}
    if obj._meta.label_lower == "achievements.skill":
        values["prerequisites"] = list(obj.prerequisites.order_by("required_skill_id").values("required_skill_id", "required_level"))
    RPGContentOverride.objects.update_or_create(**identity, defaults={
        "family": actor.family,
        "source_lookup": previous.source_lookup if previous else before_lookup,
        "values": values,
    })


def _pack_key(model, lookup, entry):
    if model._meta.model_name == "badge" and entry and entry.get("id"):
        return str(entry["id"])
    identity = {}
    for key, value in lookup.items():
        if hasattr(value, "_meta"):
            claim = ContentPackEntry.objects.filter(model_label=value._meta.label_lower, object_id=value.pk).first()
            value = f"{claim.pack}/{claim.kind}/{claim.key}" if claim else value.pk
        identity[key] = value
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def preserved_authoring_entry(model_label, lookup, *, pack_key=None, entry=None):
    """Select an exact source/claim identity; never adopt an object by name alone."""
    if model_label not in AUTHORING_MODELS:
        return None
    model = apps.get_model(model_label)
    overrides = RPGContentOverride.objects.filter(model_label=model_label)
    if pack_key:
        claim = ContentPackEntry.objects.filter(
            pack=pack_key, model_label=model_label, kind=model._meta.model_name,
            key=_pack_key(model, lookup, entry),
        ).first()
        if claim is None:
            return None
        overrides = overrides.filter(object_id=claim.object_id, family_id=claim.family_id)
    canonical = _canonical_lookup(model, lookup)
    if not pack_key:
        sources = overrides
        for key, value in canonical.items():
            sources = sources.filter(**{f"source_lookup__{key}": value})
        # The old source identity wins over the current display name. Only
        # fall back to an exact current model identity when the bundle itself
        # has been updated to the authored spelling.
        exact_sources = [row for row in sources if row.source_lookup == canonical
                         and row.values.get("_authoring") == {"version": 1, "source": "mcp"}]
        if len(exact_sources) > 1:
            raise ContentPackError("More than one authored entry retains this exact source identity.")
        overrides = exact_sources or overrides.filter(object_id__in=model.objects.filter(**canonical).values("pk"))
    for override in overrides:
        if override.values.get("_authoring") != {"version": 1, "source": "mcp"}:
            continue
        obj = model.objects.filter(pk=override.object_id).first()
        if obj is None:
            continue
        if override.source_lookup == canonical or natural_lookup(obj) == canonical or pack_key:
            return override
    return None


def preserves_skill_prerequisites(skill):
    override = RPGContentOverride.objects.filter(model_label="achievements.skill", object_id=skill.pk).first()
    return bool(override and override.values.get("_authoring") == {"version": 1, "source": "mcp"}
                and isinstance(override.values.get("prerequisites"), list))
