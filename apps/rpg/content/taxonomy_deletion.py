"""Delete only unused taxonomy leaves, under the shared catalog write fence."""
from functools import lru_cache
from pathlib import Path

import yaml
from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.deletion import ProtectedError, RestrictedError
from rest_framework.exceptions import APIException, NotFound, PermissionDenied

from apps.achievements.models import Badge, SkillCategory
from apps.homework.models import HomeworkTemplate
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, ChallengeSchedule, QuestDefinition
from apps.rpg.models import ContentPackEntry, RPGContentOverride

from .authoring import AUTHORING_MODELS, direct_catalog_write
from .loader import ContentPackError


IN_USE_DETAIL = "This taxonomy entry is in use and cannot be deleted."
READ_ONLY_DETAIL = "This taxonomy entry is read-only here."
_DIRECT_MARKER = {"version": 1, "source": "mcp"}
# These are installed, immutable local sources, never caller-selected paths.
# A new registered pack must be classified here before deletes are enabled.
_BUNDLED_TAXONOMY_FILES = {
    "content/rpg/initial": ("skill_tree.yaml", "badges.yaml"),
    "content/rpg/bundled/reading-adventures": (),
    "content/rpg/bundled/collector-reading-2026": ("badges.yaml",),
}


class TaxonomyInUse(APIException):
    status_code = 409
    default_code = "taxonomy_in_use"
    default_detail = {"detail": IN_USE_DETAIL, "code": "taxonomy_in_use"}


@lru_cache(maxsize=1)
def _bundled_identities():
    """Bounded source index; unavailable or changed manifests fail closed."""
    from apps.rpg.management.commands.loadrpgcontent import BUNDLED_PACKS

    registered = {path for path, _ in BUNDLED_PACKS}
    if registered != set(_BUNDLED_TAXONOMY_FILES):
        raise TaxonomyInUse()
    result = {label: set() for label in AUTHORING_MODELS}
    try:
        for directory, filenames in _BUNDLED_TAXONOMY_FILES.items():
            root = Path(settings.BASE_DIR) / directory
            if not root.is_dir():
                raise TaxonomyInUse()
            # Registered packs may gain taxonomy files in a later release.
            # Preserve mandatory sources and inspect only these two trusted
            # filenames, without walking authored/user-controlled pack paths.
            discovered = {name for name in ("skill_tree.yaml", "badges.yaml") if (root / name).exists()}
            for filename in sorted(set(filenames) | discovered):
                path = root / filename
                if path.stat().st_size > 1024 * 1024:
                    raise TaxonomyInUse()
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise TaxonomyInUse()
                kinds = {"categories": "skillcategory", "subjects": "subject", "skills": "skill"} if filename == "skill_tree.yaml" else {"badges": "badge"}
                for key, kind in kinds.items():
                    rows = data.get(key, [])
                    if not isinstance(rows, list) or len(rows) > 10000:
                        raise TaxonomyInUse()
                    for row in rows:
                        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                            raise TaxonomyInUse()
                        identity = (row["name"],)
                        if kind in {"skill", "subject"}:
                            if not isinstance(row.get("category"), str):
                                raise TaxonomyInUse()
                            identity = (row["category"], row["name"])
                        result[f"achievements.{kind}"].add(identity)
    except (OSError, UnicodeError, yaml.YAMLError):
        raise TaxonomyInUse() from None
    return result


def _category_names(category_id):
    category = SkillCategory.objects.filter(pk=category_id).first()
    if category is None:
        # A dangling retained source is not evidence that deletion is safe.
        raise TaxonomyInUse()
    names = {category.name}
    for source in RPGContentOverride.objects.filter(model_label="achievements.skillcategory", object_id=category_id).values_list("source_lookup", flat=True):
        if isinstance(source, dict) and isinstance(source.get("name"), str):
            names.add(source["name"])
    return names


def _is_bundled(obj, override):
    names = {obj.name}
    source = override.source_lookup if override is not None else {}
    if not isinstance(source, dict):
        raise TaxonomyInUse()
    if override is not None and (not isinstance(source.get("name"), str) or not source["name"]):
        raise TaxonomyInUse()
    if "category_id" in source and (type(source["category_id"]) is not int or source["category_id"] < 1):
        raise TaxonomyInUse()
    if isinstance(source.get("name"), str):
        names.add(source["name"])
    if obj._meta.model_name in {"skill", "subject"}:
        identities = {(name, obj.name) for name in _category_names(obj.category_id)}
        if "name" in source:
            identities.update((name, source["name"]) for name in _category_names(source.get("category_id", obj.category_id)))
    else:
        identities = {(name,) for name in names}
    return bool(identities & _bundled_identities()[obj._meta.label_lower])


def _has_incoming_relation(obj):
    """Include hidden reverse FKs and automatic many-to-many through tables."""
    for model in apps.get_models(include_auto_created=True):
        for field in model._meta.local_fields:
            if (isinstance(field, (models.ForeignKey, models.OneToOneField))
                    and field.remote_field.model._meta.concrete_model is obj._meta.concrete_model
                    and model._base_manager.filter(**{field.attname: obj.pk}).exists()):
                return True
    return False


def _same_id(value, object_id):
    return type(value) in {int, str} and str(value) == str(object_id)


def _tagged(rows, object_id, key="skill_id"):
    return isinstance(rows, list) and any(isinstance(row, dict) and _same_id(row.get(key), object_id) for row in rows)


def _named_category_rule(criteria_type, criteria, names):
    if not isinstance(criteria, dict) or not isinstance(criteria.get("category"), str):
        return False
    if criteria_type == "category_mastery":
        return criteria["category"] in names
    if criteria_type == "category_projects" and not criteria.get("categories"):
        # The plural field is a count across categories, not a list of names.
        return criteria["category"].casefold() in {name.casefold() for name in names}
    return False


def _has_source_dependency(obj):
    kind = obj._meta.model_name
    names = _category_names(obj.pk) if kind == "skillcategory" else set()
    overrides = RPGContentOverride.objects.exclude(model_label=obj._meta.label_lower, object_id=obj.pk)
    for label, source, values in overrides.values_list("model_label", "source_lookup", "values").iterator(chunk_size=256):
        source = source if isinstance(source, dict) else {}
        values = values if isinstance(values, dict) else {}
        if kind == "skillcategory" and label in {"achievements.skill", "achievements.subject"}:
            if _same_id(source.get("category_id"), obj.pk) or _same_id(values.get("category_id"), obj.pk):
                return True
        if kind == "skillcategory" and label == "quests.questdefinition":
            filters = values.get("trigger_filter")
            if isinstance(filters, dict) and _same_id(filters.get("skill_category_id"), obj.pk):
                return True
        if kind == "skillcategory" and label == "achievements.badge" and _named_category_rule(
            values.get("criteria_type"), values.get("criteria_value"), names,
        ):
            return True
        if kind == "subject" and label in {"achievements.skill", "achievements.badge"} and _same_id(values.get("subject_id"), obj.pk):
            return True
        if kind == "skill":
            if label == "achievements.skill" and _tagged(values.get("prerequisites"), obj.pk, "required_skill_id"):
                return True
            if label == "quests.questdefinition" and (
                _same_id(values.get("required_skill"), obj.pk) or _same_id(values.get("required_skill_id"), obj.pk)
                or _tagged(values.get("skill_tags"), obj.pk)
            ):
                return True
        if kind == "badge" and label == "quests.questdefinition" and (
            _same_id(values.get("required_badge"), obj.pk) or _same_id(values.get("required_badge_id"), obj.pk)
        ):
            return True
    if kind == "skillcategory":
        return any(_named_category_rule(criteria_type, criteria, names) for criteria_type, criteria in
                   Badge.objects.filter(criteria_type__in=["category_mastery", "category_projects"])
                   .values_list("criteria_type", "criteria_value").iterator(chunk_size=256))
    return False


def _has_saved_promise(obj):
    kind = obj._meta.model_name
    if kind == "skillcategory":
        for model, path in ((QuestDefinition, "trigger_filter__skill_category_id"),
                            (ChallengeGoal, "trigger_filter__skill_category_id"),
                            (ChallengeOccurrence, "snapshot__filter__skill_category_id"),
                            (ChallengeSchedule, "snapshot__filter__skill_category_id")):
            if model.objects.filter(Q(**{path: obj.pk}) | Q(**{path: str(obj.pk)})).exists():
                return True
        return False
    if kind not in {"skill", "badge"}:
        return False
    gate_key = "required_skill_id" if kind == "skill" else "required_badge_id"
    for model, gate_path in (
        (ChallengeGoal, f"catalog_gate_snapshot__{gate_key}"),
        (ChallengeOccurrence, f"snapshot__catalog_gate__{gate_key}"),
        (ChallengeSchedule, f"snapshot__catalog_gate__{gate_key}"),
    ):
        if model.objects.filter(Q(**{gate_path: obj.pk}) | Q(**{gate_path: str(obj.pk)})).exists():
            return True
    if kind == "badge":
        return False
    # Stream only the tag arrays, never private goal prose or whole snapshots.
    # SQLite lacks JSON array containment; iteration is bounded in memory and
    # intentionally has no page limit that could hide a distant saved promise.
    for model, path in ((ChallengeGoal, "skill_tags"), (ChallengeOccurrence, "snapshot__skill_tags"),
                        (ChallengeSchedule, "snapshot__skill_tags"), (HomeworkTemplate, "skill_tags")):
        for tags in model.objects.values_list(path, flat=True).iterator(chunk_size=256):
            if _tagged(tags, obj.pk):
                return True
    return False


def delete_taxonomy(actor, model, object_id):
    """Preserve every referenced identity; return only the deleted target ID."""
    if model._meta.label_lower not in AUTHORING_MODELS:
        raise ValueError("Unsupported taxonomy model.")
    try:
        with direct_catalog_write(actor) as actor:
            # FOR UPDATE conflicts with FK KEY SHARE. no_key=True would allow
            # a new incoming FK to appear between the checks and hard delete.
            obj = model.objects.select_for_update(of=("self",)).filter(pk=object_id).first()
            if obj is None:
                raise NotFound("Taxonomy entry not found.")
            identity = {"model_label": model._meta.label_lower, "object_id": obj.pk}
            claims = ContentPackEntry.objects.filter(**identity)
            override = RPGContentOverride.objects.filter(**identity).first()
            if claims.exclude(family_id=actor.family_id).exists() or (override and override.family_id != actor.family_id):
                raise PermissionDenied(READ_ONLY_DETAIL)
            if claims.exists():
                raise TaxonomyInUse()
            if override and (not isinstance(override.values, dict) or override.values.get("_authoring") != _DIRECT_MARKER
                             or override.publication_id is not None):
                raise TaxonomyInUse()
            if (_has_incoming_relation(obj) or _has_source_dependency(obj) or _has_saved_promise(obj)
                    or _is_bundled(obj, override)):
                raise TaxonomyInUse()
            if override:
                override.delete()
            obj.delete()
            return object_id
    except ContentPackError:
        raise PermissionDenied(READ_ONLY_DETAIL) from None
    except (ProtectedError, RestrictedError):
        raise TaxonomyInUse() from None
