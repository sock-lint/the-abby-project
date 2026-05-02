"""Shared scoping helpers for family-aware querysets."""
from __future__ import annotations


def parents_in(family):
    from apps.accounts.models import User
    return User.objects.filter(family=family, role="parent", is_active=True)


def children_in(family):
    from apps.accounts.models import User
    return User.objects.filter(family=family, role="child", is_active=True)


def children_across_families(*, active_only=True, **extra_filters):
    """Yield every child across every family, family-scoped at the loop boundary.

    The chokepoint for Celery tasks and management commands that intentionally
    span all families. Wrapping the iteration here keeps the leakage shape
    forbidden by the doctrine ("never write ``User.objects.filter(role='child')``
    without a family filter") confined to this single helper, and gives any
    future inner code path a Family handle to scope further lookups against.
    """
    from apps.accounts.models import User
    from apps.families.models import Family

    for family in Family.objects.all():
        qs = User.objects.filter(family=family, role="child")
        if active_only:
            qs = qs.filter(is_active=True)
        if extra_filters:
            qs = qs.filter(**extra_filters)
        for child in qs:
            yield family, child


def parents_across_families(*, active_only=True, **extra_filters):
    """Yield every parent across every family, family-scoped at the loop boundary."""
    from apps.accounts.models import User
    from apps.families.models import Family

    for family in Family.objects.all():
        qs = User.objects.filter(family=family, role="parent")
        if active_only:
            qs = qs.filter(is_active=True)
        if extra_filters:
            qs = qs.filter(**extra_filters)
        for parent in qs:
            yield family, parent
