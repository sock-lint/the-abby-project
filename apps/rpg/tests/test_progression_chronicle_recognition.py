"""Supporting coverage for Chronicle recognition's existing forecast boundary."""

from unittest.mock import patch

from django.test import TestCase

from apps.achievements.models import Badge
from apps.chronicle.services import ChronicleService
from apps.quests.models import QuestDefinition
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial, coverage
from apps.rpg.tests.test_progression_economy import quiet_config


class ProgressionChronicleRecognitionTests(TestCase):
    def test_unmodeled_chronicle_badges_do_not_fund_rewards_or_unlocks(self):
        chronicle = Badge.objects.create(
            name="Three Chronicle milestones", criteria_type="chronicle_milestones_logged",
            criteria_value={"count": 3}, rarity="rare", xp_bonus=75,
        )
        journal = Badge.objects.create(
            name="First journal", criteria_type="journal_entries_written",
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False,
        )
        meta = Badge.objects.create(
            name="Two earned badges", criteria_type="badges_earned_count",
            criteria_value={"count": 2}, xp_bonus=100,
        )
        quest = QuestDefinition.objects.create(
            name="Chronicle-gated journal goal", quest_type="collection", target_value=1,
            duration_days=7, is_system=True, required_badge=chronicle, coin_reward=100,
            trigger_filter={"allowed_triggers": ["journal_entry"]},
        )
        catalog = load_catalog()
        self.assertEqual(catalog.summary()["excluded_badge_criteria"], {"chronicle_milestones_logged": 1})
        self.assertEqual(coverage(catalog)["excluded_badge_criteria"], {"chronicle_milestones_logged": 1})
        self.assertEqual({badge.pk for badge in catalog.badges}, {journal.pk, meta.pk})

        trial = Trial(quiet_config(journal_per_day=True), catalog, 42)
        with self.assertNumQueries(0), patch.object(
            ChronicleService, "record_first", side_effect=AssertionError("live Chronicle writer"),
        ):
            for day in range(1, 4):
                trial.daily(day)

        self.assertEqual(trial.counters["journal"], 3)
        self.assertEqual(trial.badges, {journal.pk})
        self.assertNotIn(f"badge:{chronicle.pk}", trial.finite_keys)
        self.assertNotIn(f"badge:{meta.pk}", trial.finite_keys)
        self.assertNotIn(f"quest:{quest.pk}", trial.finite_keys)
        self.assertFalse(trial.completed_quests)
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 1)
        self.assertEqual(trial.counters["drop_opportunities:quest_complete"], 0)
        self.assertEqual(trial.source_totals["badges"]["coins"], 0)
        self.assertEqual(trial.source_totals["badges"]["xp"], 0)
        self.assertEqual(trial.source_totals["challenges"]["coins"], 0)
