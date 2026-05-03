"""Audit H8: BadgeService.evaluate_badges scope filter.

Pre-fix, every grant scanned all ~57 unearned badges and ran each
criterion checker. Now hot callers pass ``scopes=`` to skip checkers
whose data couldn't possibly have changed since the last grant.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.achievements.criteria import (
    _CRITERIA_SCOPES,
    criteria_types_for_scopes,
)
from apps.achievements.models import Badge
from apps.achievements.services import BadgeService
from apps.projects.models import User


class CriteriaTypesForScopesTests(TestCase):
    """Direct tests for the helper that resolves scopes → criterion ids."""

    def test_empty_scopes_returns_empty(self):
        self.assertEqual(criteria_types_for_scopes(set()), set())
        self.assertEqual(criteria_types_for_scopes(None), set())

    def test_known_scope_returns_only_matching_criteria(self):
        result = criteria_types_for_scopes({"time"})
        # Spot-check: time criteria are present.
        self.assertIn(Badge.CriteriaType.HOURS_WORKED, result)
        self.assertIn(Badge.CriteriaType.STREAK_DAYS, result)
        self.assertIn(Badge.CriteriaType.PERFECT_TIMECARD, result)
        # And criteria from unrelated scopes are absent.
        self.assertNotIn(Badge.CriteriaType.CHORE_COMPLETIONS, result)
        self.assertNotIn(Badge.CriteriaType.QUEST_COMPLETED, result)

    def test_multiple_scopes_union(self):
        result = criteria_types_for_scopes({"chore", "habit"})
        self.assertIn(Badge.CriteriaType.CHORE_COMPLETIONS, result)
        self.assertIn(Badge.CriteriaType.HABIT_TAPS_LIFETIME, result)
        self.assertIn(Badge.CriteriaType.HABIT_MAX_STRENGTH, result)
        self.assertNotIn(Badge.CriteriaType.HOURS_WORKED, result)

    def test_unknown_scope_includes_only_untagged_criteria(self):
        # With every criterion currently tagged, an unknown scope
        # surfaces nothing. If a future criterion lands without a scopes
        # tag, it'll show up here as a defensive "always relevant" entry.
        result = criteria_types_for_scopes({"never-used-scope"})
        # Filter to only currently-known criteria — the result is the set
        # of untagged ones (currently empty, but guard regression).
        untagged = {
            ctype for ctype in Badge.CriteriaType.values
            if ctype not in _CRITERIA_SCOPES
        }
        self.assertEqual(result & set(Badge.CriteriaType.values), untagged)

    def test_every_active_criterion_is_tagged(self):
        # Regression guard: if someone adds a new @criterion without
        # ``scopes=``, this asserts they made a deliberate choice
        # (untagged → always-relevant). The test fails hard so it's
        # caught in code review rather than as a silent perf regression.
        from apps.achievements.criteria import _CRITERIA_CHECKERS
        untagged = {
            ctype for ctype in _CRITERIA_CHECKERS
            if ctype not in _CRITERIA_SCOPES
        }
        self.assertEqual(
            untagged, set(),
            "All current criteria should declare scopes=. New untagged "
            "criteria are treated as always-relevant — fine if "
            "intentional; remove this assertion or add scopes=.",
        )


class EvaluateBadgesScopeFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="u", password="pw", role="child",
        )
        # Two badges in different scopes — assertions verify only the
        # right-scoped one is even considered when scopes= is set.
        self.chore_badge = Badge.objects.create(
            name="First chore", description="d",
            criteria_type=Badge.CriteriaType.CHORE_COMPLETIONS,
            criteria_value={"count": 1},
        )
        self.time_badge = Badge.objects.create(
            name="First clock", description="d",
            criteria_type=Badge.CriteriaType.FIRST_CLOCK_IN,
            criteria_value={},
        )

    def test_scopes_filter_excludes_unrelated_criteria(self):
        # Pass scopes={"chore"}: only chore-scoped criteria are
        # checked. The time-scoped FIRST_CLOCK_IN checker should never
        # be invoked even though FIRST_CLOCK_IN is unearned.
        with patch(
            "apps.achievements.criteria._CRITERIA_CHECKERS",
            new={
                Badge.CriteriaType.CHORE_COMPLETIONS:
                    lambda u, c: True,  # would award if checked
                Badge.CriteriaType.FIRST_CLOCK_IN:
                    lambda u, c: (_ for _ in ()).throw(
                        AssertionError("FIRST_CLOCK_IN checker must not run when scopes={'chore'}"),
                    ),
            },
        ):
            newly = BadgeService.evaluate_badges(self.user, scopes={"chore"})
        self.assertEqual({b.name for b in newly}, {"First chore"})

    def test_no_scopes_evaluates_everything_default_behaviour(self):
        # scopes=None preserves the pre-PR scan-everything behaviour.
        with patch(
            "apps.achievements.criteria._CRITERIA_CHECKERS",
            new={
                Badge.CriteriaType.CHORE_COMPLETIONS: lambda u, c: True,
                Badge.CriteriaType.FIRST_CLOCK_IN: lambda u, c: True,
            },
        ):
            newly = BadgeService.evaluate_badges(self.user)
        names = {b.name for b in newly}
        self.assertEqual(names, {"First chore", "First clock"})

    def test_scopes_filter_uses_or_semantics(self):
        # scopes={"chore","time"} should reach both badges.
        with patch(
            "apps.achievements.criteria._CRITERIA_CHECKERS",
            new={
                Badge.CriteriaType.CHORE_COMPLETIONS: lambda u, c: True,
                Badge.CriteriaType.FIRST_CLOCK_IN: lambda u, c: True,
            },
        ):
            newly = BadgeService.evaluate_badges(
                self.user, scopes={"chore", "time"},
            )
        self.assertEqual(
            {b.name for b in newly}, {"First chore", "First clock"},
        )
