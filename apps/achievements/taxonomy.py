"""Taxonomy choice availability; saved progress and reward identity stay intact.

Use the filtered querysets only for new choices. Default model managers, source
identity resolution, history and award services deliberately retain every row.
"""
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Q

from .models import Badge, Skill, SkillCategory, Subject


def available_categories(queryset=None):
    return (SkillCategory.objects.all() if queryset is None else queryset).filter(is_retired=False)


def available_subjects(queryset=None):
    return (Subject.objects.all() if queryset is None else queryset).filter(
        is_retired=False, category__is_retired=False,
    )


def available_skills(queryset=None):
    return (Skill.objects.all() if queryset is None else queryset).filter(
        Q(subject__isnull=True) | Q(subject__is_retired=False, subject__category__is_retired=False),
        is_retired=False, category__is_retired=False,
    )


def available_for_new_choices(obj):
    if isinstance(obj, Badge):
        # Badge goal availability has its own runtime policy; it is not a
        # taxonomy retirement flag and must not inherit its optional subject.
        return True
    if obj.is_retired:
        return False
    if isinstance(obj, (Subject, Skill)) and obj.category.is_retired:
        return False
    if isinstance(obj, Skill) and obj.subject_id:
        return not obj.subject.is_retired and not obj.subject.category.is_retired
    return True


def _share_lock(model, ids):
    """A SHARE row lock conflicts with non-key retirement/reparenting updates."""
    if not ids:
        return
    if connection.vendor == "postgresql":
        table = connection.ops.quote_name(model._meta.db_table)
        key = connection.ops.quote_name(model._meta.pk.column)
        placeholders = ", ".join(["%s"] * len(ids))
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {key} FROM {table} WHERE {key} IN ({placeholders}) ORDER BY {key} FOR SHARE",
                           sorted(ids))
            cursor.fetchall()
    else:
        list(model.objects.select_for_update().filter(pk__in=ids).order_by("pk").values_list("pk", flat=True))


def _ancestry(model, ids):
    fields = ["pk"]
    if model in (Subject, Skill):
        fields.append("category_id")
    if model is Skill:
        fields.append("subject_id")
    return {row["pk"]: row for row in model.objects.filter(pk__in=ids).values(*fields)}


def validate_new_taxonomy_references(model, ids, *, retained_ids=(), lock=True):
    """Validate new references while allowing exact existing saved references.

    Locked callers must already be atomic and hold their usual household/user
    gates. Catalog writers take their catalog-table write admission first, then
    call this helper, avoiding an inverted table/row wait against publication.
    Ancestors lock in category, subject, skill order. A changed ancestry between
    discovery and those locks fails closed rather than checking a stale parent.
    """
    if model not in (SkillCategory, Subject, Skill, Badge):
        raise ValueError("Unsupported taxonomy reference model.")
    requested = set(ids)
    if any(type(pk) is not int or pk < 1 for pk in requested):
        raise ValidationError("Choose existing taxonomy entries.")
    if not requested:
        return
    if model.objects.filter(pk__in=requested).count() != len(requested):
        raise ValidationError("Choose existing taxonomy entries.")
    admitted = requested - set(retained_ids)
    if not admitted:
        return
    if lock and not connection.in_atomic_block:
        raise RuntimeError("Taxonomy reference admission requires an atomic write.")
    initial = _ancestry(model, admitted)
    subject_ids = ({row["subject_id"] for row in initial.values() if row["subject_id"]}
                   if model is Skill else set(admitted) if model is Subject else set())
    subjects = _ancestry(Subject, subject_ids)
    category_ids = ({row["category_id"] for row in initial.values()} if model in (Subject, Skill)
                    else set(admitted) if model is SkillCategory else set())
    category_ids.update(row["category_id"] for row in subjects.values())
    if lock:
        _share_lock(SkillCategory, category_ids)
        _share_lock(Subject, subject_ids)
        if model in (Skill, Badge):
            _share_lock(model, admitted)
    if initial != _ancestry(model, admitted) or subjects != _ancestry(Subject, subject_ids):
        raise ValidationError("The taxonomy changed. Refresh and choose again.")
    queryset = {SkillCategory: available_categories, Subject: available_subjects, Skill: available_skills}.get(model)
    if queryset is not None and queryset().filter(pk__in=admitted).count() != len(admitted):
        raise ValidationError("Retired taxonomy entries cannot be selected for new work. Restore the entry or choose an available one.")
