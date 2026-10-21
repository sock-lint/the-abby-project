"""Adapt taxonomy admission errors to each consumer's existing error contract."""
from django.core.exceptions import ValidationError

from apps.achievements.taxonomy import validate_new_taxonomy_references


def admit_references(model, ids, *, retained_ids=(), error_type=ValueError):
    """Call inside the writer's atomic block, before persisting new references."""
    try:
        validate_new_taxonomy_references(model, ids, retained_ids=retained_ids)
    except ValidationError as exc:
        raise error_type(" ".join(exc.messages)) from exc
