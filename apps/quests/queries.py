"""Shared visibility boundary for global and household quest definitions."""
from django.db.models import Count, Q, Subquery

from .models import QuestDefinition


def active_system_definitions():
    """Canonical global offers; unresolved duplicate names require reconciliation.

    Saved campaigns and goal snapshots deliberately keep using their original
    definitions. This query governs only new acceptance and catalog projections.
    """
    active = QuestDefinition.objects.filter(is_system=True, superseded_by__isnull=True)
    conflicts = active.order_by().values("name").annotate(count=Count("pk")).filter(count__gt=1).values("name")
    return active.exclude(name__in=Subquery(conflicts))


def equivalent_definition_ids(definition):
    """The durable canonical identity and its retained history aliases."""
    canonical_id = definition.superseded_by_id or definition.pk
    return list(QuestDefinition.objects.filter(
        Q(pk=canonical_id) | Q(superseded_by_id=canonical_id),
    ).values_list("pk", flat=True))


def definitions_visible_to(user):
    visible = Q(pk__in=active_system_definitions().values("pk"))
    if user.family_id is not None:
        visible |= Q(is_system=False, created_by__family_id=user.family_id)
    # A missing creator must never turn a private promise into global content.
    return QuestDefinition.objects.filter(visible, superseded_by__isnull=True)
