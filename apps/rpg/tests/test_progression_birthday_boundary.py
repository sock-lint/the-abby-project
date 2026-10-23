"""Birthday rewards require real annual celebrations, outside anonymous forecasts."""

from unittest.mock import patch

from django.test import TestCase

from apps.achievements.models import Badge
from apps.chronicle.services import ChronicleService
from apps.quests.models import QuestDefinition
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial, coverage
from apps.rpg.tests.test_progression_economy import quiet_config


class ProgressionBirthdayBoundaryTests(TestCase):
    def test_full_year_does_not_invent_birthday_badges_gift_or_dependent_rewards(self):
        birthdays = [
            Badge.objects.create(
                name=f"{count} birthdays", criteria_type="birthdays_logged",
                criteria_value={"count": count}, rarity="rare", xp_bonus=75,
            )
            for count in (1, 3, 5, 10)
        ]
        journal = Badge.objects.create(
            name="First journal", criteria_type="journal_entries_written",
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False,
        )
        meta = Badge.objects.create(
            name="Two earned badges", criteria_type="badges_earned_count",
            criteria_value={"count": 2}, xp_bonus=100,
        )
        quest = QuestDefinition.objects.create(
            name="Birthday-gated journal goal", quest_type="collection", target_value=1,
            duration_days=7, is_system=True, required_badge=birthdays[0], coin_reward=100,
            trigger_filter={"allowed_triggers": ["journal_entry"]},
        )
        catalog = load_catalog()
        expected_exclusions = {"birthdays_logged": 4}
        self.assertEqual(catalog.summary()["excluded_badge_criteria"], expected_exclusions)
        self.assertEqual(coverage(catalog)["excluded_badge_criteria"], expected_exclusions)
        self.assertTrue(any("birthdays" in line for line in coverage(catalog)["excluded"]))
        self.assertEqual({badge.pk for badge in catalog.badges}, {journal.pk, meta.pk})

        trial = Trial(quiet_config(horizon_days=365, journal_per_day=True), catalog, 42)
        with self.assertNumQueries(0), patch.object(
            ChronicleService, "record_birthday", side_effect=AssertionError("live birthday writer"),
        ):
            for day in range(1, 366):
                trial.daily(day)

        self.assertEqual(trial.counters["journal"], 365)
        self.assertEqual(trial.badges, {journal.pk})
        for badge in [*birthdays, meta]:
            self.assertNotIn(f"badge:{badge.pk}", trial.finite_keys)
        self.assertNotIn(f"quest:{quest.pk}", trial.finite_keys)
        self.assertFalse(trial.completed_quests)
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 1)
        self.assertEqual(trial.counters["drop_opportunities:quest_complete"], 0)
        self.assertEqual(trial.source_totals["badges"]["coins"], 0)
        self.assertEqual(trial.source_totals["badges"]["xp"], 0)
        self.assertEqual(trial.source_totals["challenges"]["coins"], 0)
        self.assertEqual(
            {source for source, totals in trial.source_totals.items() if totals["coins"] > 0},
            {"journal", "check_in"},
        )
