"""Family-aware base TestCase classes.

Use these instead of ``TestCase`` whenever a test needs more than one
user. They guarantee every user is attached to a real ``Family`` so the
six family-scoping chokepoints (see CLAUDE.md) actually fire — bare
``User.objects.create_user(...)`` lands everyone in the auto-attached
"Default Family" and silently masks cross-family bugs.

Subclass options:
- :class:`BaseFamilyTestCase` — no users by default. Override
  :attr:`family_parents` / :attr:`family_children` (lists of dicts with
  at least ``username``) to seed users at ``setUpTestData`` time. The
  resulting ``Family`` and lists are exposed as ``cls.family`` /
  ``cls.parents`` / ``cls.children``.

- For more complex graphs (multiple families to test cross-family
  scoping), call ``make_family`` directly inside the test body —
  this base case is for the common single-family setup.
"""
from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APITestCase

from .factories import make_family


class _FamilyMixin:
    """Shared seed logic for both Django and DRF TestCase variants."""

    family_name: str = "Test Family"
    family_parents: list[dict] = []  # noqa: RUF012
    family_children: list[dict] = []  # noqa: RUF012

    @classmethod
    def setUpTestData(cls) -> None:
        super_setup = getattr(super(), "setUpTestData", None)
        if super_setup:
            super_setup()
        if cls.family_parents or cls.family_children:
            ns = make_family(
                cls.family_name,
                parents=cls.family_parents,
                children=cls.family_children,
            )
            cls.family = ns.family
            cls.parents = ns.parents
            cls.children = ns.children


class BaseFamilyTestCase(_FamilyMixin, TestCase):
    """Django ``TestCase`` with family-scoped user seeding."""


class BaseFamilyAPITestCase(_FamilyMixin, APITestCase):
    """DRF ``APITestCase`` with family-scoped user seeding."""
