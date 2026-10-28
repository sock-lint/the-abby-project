"""Shared household activity visibility, before filters or serialization."""
from django.db.models import Q

from .models import ActivityEvent
from .services import PRIVATE_CHALLENGE_DOMAINS


def visible_activity_events(observer):
    family_id = getattr(observer, "family_id", None)
    if family_id is None or getattr(observer, "role", None) != "parent":
        return ActivityEvent.objects.none()
    queryset = ActivityEvent.objects.select_related("actor", "subject", "target_ct").filter(
        Q(subject__family_id=family_id) | Q(actor__family_id=family_id),
    )
    # New parent challenge payouts retain their identity through generic
    # coin/XP/badge/drop emissions. Keep the original owner even after a
    # role or household change; deleting the source cannot expose its name.
    private = Q(context__has_key="private_challenge") & Q(
        context__private_challenge__domain__in=PRIVATE_CHALLENGE_DOMAINS,
    )
    own = Q(context__private_challenge__owner_id=observer.pk)
    queryset = queryset.exclude(private & ~own)
    # Older legacy lifecycle events already had a typed Quest target. Unlike
    # generic historical awards, they can be scoped without guessing text.
    parent_challenge = Q(
        target_ct__app_label="quests", target_ct__model__in=["quest", "challengeoccurrence"],
        subject__role="parent",
    )
    return queryset.exclude(parent_challenge & ~Q(subject_id=observer.pk))
