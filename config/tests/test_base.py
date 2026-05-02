"""Tests for the family-scoped TestCase base class."""
from __future__ import annotations

from .base import BaseFamilyTestCase


class BaseFamilyTestCaseSeedingTests(BaseFamilyTestCase):
    """Subclasses set declarative ``family_parents`` / ``family_children``."""

    family_name = "Smiths"
    family_parents = [{"username": "smith-mom"}]
    family_children = [
        {"username": "smith-kid-a"},
        {"username": "smith-kid-b", "display_name": "Younger"},
    ]

    def test_family_seeded(self):
        self.assertEqual(self.family.name, "Smiths")
        self.assertEqual(self.family.primary_parent, self.parents[0])

    def test_users_attached_to_family(self):
        self.assertEqual(len(self.parents), 1)
        self.assertEqual(len(self.children), 2)
        for user in (*self.parents, *self.children):
            self.assertEqual(user.family_id, self.family.id)

    def test_children_kwargs_flow_through(self):
        self.assertEqual(self.children[1].display_name, "Younger")


class BaseFamilyTestCaseEmptyTests(BaseFamilyTestCase):
    """Empty defaults — no users seeded unless declared."""

    def test_no_family_attached(self):
        self.assertFalse(hasattr(self, "family"))
