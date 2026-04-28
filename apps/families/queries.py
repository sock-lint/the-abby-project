"""Shared scoping helpers for family-aware querysets."""
from __future__ import annotations


def parents_in(family):
    from apps.accounts.models import User
    return User.objects.filter(family=family, role="parent", is_active=True)


def children_in(family):
    from apps.accounts.models import User
    return User.objects.filter(family=family, role="child", is_active=True)
