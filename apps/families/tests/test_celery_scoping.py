"""Regression tests for family-scoping in Celery tasks and seed commands.

CLAUDE.md forbids ``User.objects.filter(role="parent"|"child")`` without a
family filter. Background tasks that intentionally span every household must
go through ``children_across_families`` / ``parents_across_families`` /
``children_in`` so the family handle is available at the loop boundary —
otherwise any future inner code path picks up rows from other families
silently.

This module pins the helper itself plus a couple of integration-style checks
against the Celery tasks that used to iterate globally.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.families.models import Family
from apps.families.queries import (
    children_across_families,
    children_in,
    parents_across_families,
    parents_in,
)
from config.tests.factories import make_family


class HelperFamilyScopingTests(TestCase):
    """The helper itself yields the right (family, user) pairs."""

    @classmethod
    def setUpTestData(cls):
        cls.f1 = make_family(
            "Alpha",
            parents=[{"username": "p1"}],
            children=[{"username": "c1"}, {"username": "c1b"}],
        )
        cls.f2 = make_family(
            "Beta",
            parents=[{"username": "p2"}],
            children=[{"username": "c2"}],
        )

    def test_children_across_families_yields_pairs(self):
        seen = list(children_across_families())
        # 3 children total across the two families.
        self.assertEqual(len(seen), 3)
        # Every yielded pair carries the right family.
        for family, child in seen:
            self.assertEqual(child.family_id, family.id)
            self.assertEqual(child.role, "child")

    def test_parents_across_families_yields_pairs(self):
        seen = list(parents_across_families())
        self.assertEqual(len(seen), 2)
        for family, parent in seen:
            self.assertEqual(parent.family_id, family.id)
            self.assertEqual(parent.role, "parent")

    def test_extra_filters_applied_per_family(self):
        # date_of_birth filter only matches one of our seeded children.
        from apps.accounts.models import User
        target = self.f1.children[0]
        target.date_of_birth = date(2015, 5, 15)
        target.save(update_fields=["date_of_birth"])

        seen = list(
            children_across_families(date_of_birth__isnull=False)
        )
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][1].id, target.id)
        # Sanity: User.objects.filter(...) without family scope would also
        # return one match here, but the helper confirms it's scoped.
        self.assertEqual(seen[0][0].id, self.f1.family.id)

    def test_inactive_children_excluded_by_default(self):
        target = self.f2.children[0]
        target.is_active = False
        target.save(update_fields=["is_active"])

        active = list(children_across_families())
        self.assertEqual(len(active), 2)  # only f1's two children

        all_including_inactive = list(children_across_families(active_only=False))
        self.assertEqual(len(all_including_inactive), 3)

    def test_children_in_and_parents_in_scope_correctly(self):
        f1_kids = list(children_in(self.f1.family))
        self.assertEqual(len(f1_kids), 2)
        for k in f1_kids:
            self.assertEqual(k.family_id, self.f1.family.id)

        f1_parents = list(parents_in(self.f1.family))
        self.assertEqual(len(f1_parents), 1)
        self.assertEqual(f1_parents[0].family_id, self.f1.family.id)


class TaskFamilyScopingTests(TestCase):
    """End-to-end sanity: Celery tasks iterate every family they should and
    don't accidentally drop one. This is the regression shape that goes hot
    the first day a second family signs up.
    """

    @classmethod
    def setUpTestData(cls):
        cls.f1 = make_family(
            "Alpha",
            parents=[{"username": "alpha-parent"}],
            children=[{"username": "alpha-child"}],
        )
        cls.f2 = make_family(
            "Beta",
            parents=[{"username": "beta-parent"}],
            children=[{"username": "beta-child"}],
        )

    def test_perfect_day_iterates_every_family(self):
        # ``evaluate_perfect_day_task`` returns "Perfect day evaluated:
        # X/Y children awarded." We don't seed any chores, so X=0, but Y
        # MUST equal the total number of active children across all
        # families — proving the iteration didn't stop at one family.
        from apps.rpg.tasks import evaluate_perfect_day_task

        result = evaluate_perfect_day_task()
        self.assertIn("0/2", result)

    def test_decay_habits_iterates_every_family(self):
        from apps.habits.tasks import decay_habit_strength_task

        result = decay_habit_strength_task()
        self.assertIn("across 2 children", result)

    def test_rotate_daily_challenges_iterates_every_family(self):
        from apps.quests.tasks import rotate_daily_challenges_task

        result = rotate_daily_challenges_task()
        # Both children get a challenge on first run.
        self.assertIn("Daily challenges:", result)
        # Two children, so the total of fresh+preserved should be 2.
        # (The exact split depends on idempotency state.)
        # We just assert both families were visited by counting fresh.
        self.assertTrue(
            "2 fresh" in result or "1 fresh, 1 preserved" in result
            or "0 fresh, 2 preserved" in result,
            f"unexpected output: {result}",
        )
