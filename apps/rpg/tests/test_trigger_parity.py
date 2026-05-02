"""Parity gates for the three RPG trigger tables.

``TriggerType`` (apps/rpg/constants.py) is the canonical vocabulary;
``BASE_DROP_RATES`` (apps/rpg/services.py) and ``TRIGGER_DAMAGE``
(apps/quests/services.py) are independent dicts keyed by it. Without
these tests, adding a new ``TriggerType`` member silently leaves stale
gaps in either table — which means a new trigger drops nothing and
deals zero damage until somebody notices.

Each table declares an explicit "exempt" set for triggers that
intentionally don't participate. Adding a new trigger forces the
author to either populate the table OR add it to the exempt set with a
comment justifying why.
"""
from __future__ import annotations

from django.test import TestCase

from apps.quests.services import TRIGGER_DAMAGE
from apps.rpg.constants import TriggerType
from apps.rpg.services import BASE_DROP_RATES


# Triggers that intentionally don't deal boss-quest damage. Adding here
# requires a one-line comment explaining why — the absence of damage is a
# design choice, not a missing entry.
TRIGGER_DAMAGE_EXEMPT = {
    # Quest completion is itself a reward — completing a quest shouldn't
    # damage another active boss quest.
    TriggerType.QUEST_COMPLETE,
    # Perfect day is celebratory; doesn't make sense as a damage source.
    TriggerType.PERFECT_DAY,
    # Daily check-in fires on every login; coin/companion bonus is the
    # reward, no damage so a streaky child doesn't auto-shred bosses.
    TriggerType.DAILY_CHECK_IN,
    # Creations are child-authored entries; design intent is no boss damage.
    TriggerType.CREATION_LOGGED,
}


# Triggers that intentionally have no drop-rate entry. Empty today — every
# trigger has a rate, including DAILY_CHECK_IN at 0.0 so ``.get()`` returns
# a sensible default. Kept here so future drift can opt out explicitly
# rather than via missing-key fallthrough.
BASE_DROP_RATES_EXEMPT: set[str] = set()


class TriggerTableParityTests(TestCase):
    def test_every_trigger_has_a_drop_rate(self):
        missing = []
        for value, _label in TriggerType.choices:
            if value in BASE_DROP_RATES_EXEMPT:
                continue
            if value not in BASE_DROP_RATES:
                missing.append(value)
        self.assertFalse(
            missing,
            f"TriggerType members missing from BASE_DROP_RATES: {missing}. "
            f"Add a rate (use 0.0 if no drop is intended) or add the value "
            f"to BASE_DROP_RATES_EXEMPT in this file with a comment.",
        )

    def test_every_trigger_has_damage_or_is_exempt(self):
        missing = []
        for value, _label in TriggerType.choices:
            if value in TRIGGER_DAMAGE_EXEMPT:
                continue
            if value not in TRIGGER_DAMAGE:
                missing.append(value)
        self.assertFalse(
            missing,
            f"TriggerType members missing from TRIGGER_DAMAGE: {missing}. "
            f"Add a damage value or add the trigger to "
            f"TRIGGER_DAMAGE_EXEMPT in this file with a comment.",
        )

    def test_no_stale_keys_in_drop_rates(self):
        valid = {value for value, _label in TriggerType.choices}
        stale = set(BASE_DROP_RATES) - valid
        self.assertFalse(
            stale,
            f"BASE_DROP_RATES has keys that aren't in TriggerType: {stale}. "
            f"Did the trigger get renamed or removed?",
        )

    def test_no_stale_keys_in_trigger_damage(self):
        valid = {value for value, _label in TriggerType.choices}
        stale = set(TRIGGER_DAMAGE) - valid
        self.assertFalse(
            stale,
            f"TRIGGER_DAMAGE has keys that aren't in TriggerType: {stale}. "
            f"Did the trigger get renamed or removed?",
        )

    def test_drop_rates_in_valid_range(self):
        for trigger, rate in BASE_DROP_RATES.items():
            self.assertGreaterEqual(rate, 0.0, f"{trigger} has negative drop rate")
            self.assertLessEqual(rate, 1.0, f"{trigger} drop rate exceeds 1.0")

    def test_damage_values_non_negative(self):
        for trigger, dmg in TRIGGER_DAMAGE.items():
            self.assertGreaterEqual(dmg, 0, f"{trigger} has negative damage")
