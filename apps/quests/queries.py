"""Shared visibility boundary for global and household quest definitions."""
from django.db.models import Q

from .models import QuestDefinition


def definitions_visible_to(user):
    visible = Q(is_system=True)
    if user.family_id is not None:
        visible |= Q(created_by__family_id=user.family_id)
    # A missing creator must never turn a private promise into global content.
    return QuestDefinition.objects.filter(visible)
