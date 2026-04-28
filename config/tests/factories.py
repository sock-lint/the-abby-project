"""Test factories for family-aware setUp blocks.

Use ``make_family(parents=[...], children=[...])`` instead of inlining
``User.objects.create_user(...)`` per test, so every user winds up in
exactly one family and family-scoping assertions work without ceremony.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable, Mapping


def make_family(
    name: str = "Test Family",
    *,
    parents: Iterable[Mapping] = (),
    children: Iterable[Mapping] = (),
):
    """Create a Family with attached parents and children.

    Each ``parents`` / ``children`` entry is a dict with at least
    ``username`` (other keys flow through as ``create_user`` kwargs —
    ``display_name``, ``hourly_rate``, ``date_of_birth`` etc.). The first
    parent (if any) is set as ``primary_parent``.

    Returns ``SimpleNamespace(family=Family, parents=[User], children=[User])``.
    """
    from django.contrib.auth import get_user_model
    from apps.families.models import Family

    User = get_user_model()
    family = Family.objects.create(name=name)
    parent_objs = []
    for p in parents:
        kwargs = {"password": "pw", "role": "parent", "family": family, **dict(p)}
        parent_objs.append(User.objects.create_user(**kwargs))
    if parent_objs and family.primary_parent_id is None:
        family.primary_parent = parent_objs[0]
        family.save(update_fields=["primary_parent"])
    child_objs = []
    for c in children:
        kwargs = {"password": "pw", "role": "child", "family": family, **dict(c)}
        child_objs.append(User.objects.create_user(**kwargs))
    return SimpleNamespace(family=family, parents=parent_objs, children=child_objs)
