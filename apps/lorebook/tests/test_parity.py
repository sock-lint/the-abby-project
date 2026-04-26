"""Lorebook parity test — keeps explainer entries in lock-step with the app.

The Lorebook describes mechanics that live elsewhere in the codebase. This test
fails when those references drift, so adding a new ``TriggerType`` /
``PaymentLedger.EntryType`` / ``CoinLedger.Reason`` (or removing a setting or
badge criterion that an entry references) cannot ship without an explicit
acknowledgement here.

When a failure points you here, the fix is one of:

1. Add the new value to the relevant ``LOREBOOK_*_COVERAGE`` map AND update the
   matching entry's mechanics text in ``content/lorebook/entries.yaml``.
2. Add it to the matching ``LOREBOOK_*_EXEMPT`` set with a comment explaining
   why the Lorebook intentionally omits it.
"""
from __future__ import annotations

import ast
import inspect

from django.conf import settings as django_settings
from django.test import SimpleTestCase

from apps.achievements.models import Badge
from apps.lorebook import services
from apps.payments.models import PaymentLedger
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType


# --------------------------------------------------------------------------- #
# Coverage maps: every value in the source enum MUST appear here OR in EXEMPT.
# Adding a new value to the enum without adding it here breaks CI.
# --------------------------------------------------------------------------- #

LOREBOOK_TRIGGER_COVERAGE: dict[str, str] = {
    TriggerType.CLOCK_OUT: "ventures",
    TriggerType.CHORE_COMPLETE: "duties",
    TriggerType.HOMEWORK_COMPLETE: "study",
    TriggerType.HOMEWORK_CREATED: "study",
    TriggerType.MILESTONE_COMPLETE: "ventures",
    TriggerType.PROJECT_COMPLETE: "ventures",
    TriggerType.BADGE_EARNED: "badges",
    TriggerType.QUEST_COMPLETE: "quests",
    TriggerType.PERFECT_DAY: "streaks",
    TriggerType.HABIT_LOG: "rituals",
    TriggerType.DAILY_CHECK_IN: "streaks",
    TriggerType.SAVINGS_GOAL_COMPLETE: "money",
    TriggerType.JOURNAL_ENTRY: "journal",
    TriggerType.CREATION_LOGGED: "creations",
}
LOREBOOK_TRIGGER_EXEMPT: set[str] = {
    # MOVEMENT_SESSION feeds the Movement subsystem; there is no Lorebook
    # entry for movement yet. Add one (and remove this exemption) when the
    # feature is ready to surface for kids.
    TriggerType.MOVEMENT_SESSION,
}

LOREBOOK_PAYMENT_ENTRY_COVERAGE: dict[str, str] = {
    PaymentLedger.EntryType.HOURLY: "ventures",
    PaymentLedger.EntryType.PROJECT_BONUS: "ventures",
    PaymentLedger.EntryType.BOUNTY_PAYOUT: "ventures",
    PaymentLedger.EntryType.MILESTONE_BONUS: "ventures",
    PaymentLedger.EntryType.MATERIALS_REIMBURSEMENT: "money",
    PaymentLedger.EntryType.PAYOUT: "money",
    PaymentLedger.EntryType.ADJUSTMENT: "money",
    PaymentLedger.EntryType.CHORE_REWARD: "duties",
    PaymentLedger.EntryType.COIN_EXCHANGE: "money",
}
LOREBOOK_PAYMENT_ENTRY_EXEMPT: set[str] = set()

LOREBOOK_COIN_REASON_COVERAGE: dict[str, str] = {
    CoinLedger.Reason.HOURLY: "ventures",
    CoinLedger.Reason.PROJECT_BONUS: "ventures",
    CoinLedger.Reason.BOUNTY_BONUS: "ventures",
    CoinLedger.Reason.MILESTONE_BONUS: "ventures",
    CoinLedger.Reason.BADGE_BONUS: "badges",
    CoinLedger.Reason.REDEMPTION: "coins",
    CoinLedger.Reason.REFUND: "coins",
    CoinLedger.Reason.ADJUSTMENT: "coins",
    CoinLedger.Reason.CHORE_REWARD: "duties",
    CoinLedger.Reason.EXCHANGE: "coins",
}
LOREBOOK_COIN_REASON_EXEMPT: set[str] = set()


def _mark_slugs() -> set[str]:
    """Statically extract every slug used in compute_lorebook_unlocks().mark() calls."""
    source = inspect.getsource(services.compute_lorebook_unlocks)
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "mark"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
    return found


class LorebookParityTests(SimpleTestCase):
    """Drift guards. Failures here mean either YAML or the maps above are out of date."""

    def setUp(self):
        services.load_lorebook_catalog.cache_clear()
        self.catalog = services.load_lorebook_catalog()
        self.slugs = {entry["slug"] for entry in self.catalog}

    def test_catalog_matches_expected_slugs(self):
        self.assertEqual(self.slugs, services.EXPECTED_ENTRY_SLUGS)

    def test_every_entry_has_an_unlock_mark_call(self):
        marked = _mark_slugs()
        missing = self.slugs - marked
        self.assertFalse(
            missing,
            f"Entries with no mark() call in compute_lorebook_unlocks: {sorted(missing)}. "
            f"Add a mark(slug, condition, reason) call so children can encounter the page.",
        )

    def test_every_unlock_mark_call_has_an_entry(self):
        marked = _mark_slugs()
        orphans = marked - self.slugs
        self.assertFalse(
            orphans,
            f"mark() calls reference unknown slugs: {sorted(orphans)}. "
            f"Either add the slug to entries.yaml or remove the mark() call.",
        )

    def test_every_entry_has_known_trial_template(self):
        for entry in self.catalog:
            with self.subTest(slug=entry["slug"]):
                self.assertIn(entry["trial_template"], services.TRIAL_TEMPLATES)

    def test_every_known_template_has_at_least_one_consumer(self):
        used = {entry["trial_template"] for entry in self.catalog}
        unused = services.TRIAL_TEMPLATES - used
        self.assertFalse(
            unused,
            f"Trial templates with no Lorebook consumer: {sorted(unused)}. "
            f"Either remove from TRIAL_TEMPLATES or assign at least one entry to use it.",
        )

    def test_every_trigger_is_covered_or_exempt(self):
        all_triggers = set(TriggerType.values)
        accounted = set(LOREBOOK_TRIGGER_COVERAGE) | LOREBOOK_TRIGGER_EXEMPT
        missing = all_triggers - accounted
        self.assertFalse(
            missing,
            f"New TriggerType value(s) not surfaced in the Lorebook: {sorted(missing)}. "
            f"Map them to a slug in LOREBOOK_TRIGGER_COVERAGE (and update that entry's "
            f"mechanics text) or add them to LOREBOOK_TRIGGER_EXEMPT with a comment.",
        )
        bad_targets = {
            t: slug for t, slug in LOREBOOK_TRIGGER_COVERAGE.items() if slug not in self.slugs
        }
        self.assertFalse(
            bad_targets,
            f"LOREBOOK_TRIGGER_COVERAGE points at unknown slugs: {bad_targets}",
        )

    def test_every_payment_entry_type_is_covered_or_exempt(self):
        all_entries = set(PaymentLedger.EntryType.values)
        accounted = set(LOREBOOK_PAYMENT_ENTRY_COVERAGE) | LOREBOOK_PAYMENT_ENTRY_EXEMPT
        missing = all_entries - accounted
        self.assertFalse(
            missing,
            f"New PaymentLedger.EntryType value(s) not surfaced in the Lorebook: "
            f"{sorted(missing)}. Map to a slug in LOREBOOK_PAYMENT_ENTRY_COVERAGE or "
            f"explicitly exempt with a reason.",
        )
        bad_targets = {
            t: slug
            for t, slug in LOREBOOK_PAYMENT_ENTRY_COVERAGE.items()
            if slug not in self.slugs
        }
        self.assertFalse(bad_targets, f"Bad coverage targets: {bad_targets}")

    def test_every_coin_reason_is_covered_or_exempt(self):
        all_reasons = set(CoinLedger.Reason.values)
        accounted = set(LOREBOOK_COIN_REASON_COVERAGE) | LOREBOOK_COIN_REASON_EXEMPT
        missing = all_reasons - accounted
        self.assertFalse(
            missing,
            f"New CoinLedger.Reason value(s) not surfaced in the Lorebook: "
            f"{sorted(missing)}. Map to a slug in LOREBOOK_COIN_REASON_COVERAGE or "
            f"explicitly exempt with a reason.",
        )
        bad_targets = {
            t: slug
            for t, slug in LOREBOOK_COIN_REASON_COVERAGE.items()
            if slug not in self.slugs
        }
        self.assertFalse(bad_targets, f"Bad coverage targets: {bad_targets}")

    def test_every_powers_badges_value_is_a_real_criteria_type(self):
        valid = set(Badge.CriteriaType.values)
        for entry in self.catalog:
            knobs = entry.get("parent_knobs") or {}
            for badge in knobs.get("powers_badges") or []:
                with self.subTest(slug=entry["slug"], badge=badge):
                    self.assertIn(
                        badge,
                        valid,
                        f"{entry['slug']}: powers_badges entry {badge!r} is not a valid "
                        f"Badge.CriteriaType. Add it to apps/achievements/models.py or "
                        f"remove from this entry.",
                    )

    def test_every_settings_key_resolves_on_django_settings(self):
        for entry in self.catalog:
            knobs = entry.get("parent_knobs") or {}
            for setting in knobs.get("settings") or []:
                key = setting.get("key")
                if not key:
                    continue
                with self.subTest(slug=entry["slug"], key=key):
                    self.assertTrue(
                        hasattr(django_settings, key),
                        f"{entry['slug']}: parent_knobs.settings[*].key {key!r} is not "
                        f"on django.conf.settings. Add it to config/settings.py or remove "
                        f"from this entry.",
                    )
