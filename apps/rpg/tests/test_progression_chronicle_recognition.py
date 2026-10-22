"""Modeled first-event checks preserve scoped recognition and its exclusions."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Badge, UserBadge
from apps.achievements.services import BadgeService
from apps.chronicle import firsts, recognition
from apps.chronicle.services import ChronicleService
from apps.payments.models import PaymentLedger
from apps.quests.goals import ingest_activity
from apps.quests.models import QuestDefinition
from apps.rewards.models import ExchangeRequest
from apps.rewards.services import ExchangeService
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial, coverage, rules_fingerprint
from apps.rpg.models import DropTable, ItemDefinition
from apps.rpg.services import GameLoopService
from apps.rpg.tests.test_progression_economy import quiet_config
from config.tests.factories import make_family


def alternate_recognition(*args, **kwargs):
    return []


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


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProgressionFirstBoundaryParityTests(TestCase):
    def setUp(self):
        self.family = make_family("First forecast", parents=[{"username": "first-forecast-parent"}],
                                  children=[{"username": "first-forecast-child"}])
        self.child = self.family.children[0]

    def badge(self, name, kind, criterion, **changes):
        return Badge.objects.create(name=name, criteria_type=kind, criteria_value=criterion,
                                    xp_bonus=0, award_coins=False, **changes)

    def trial(self, **changes):
        trial = Trial(quiet_config(**changes), load_catalog(), 42)
        trial.day = 1
        return trial

    def assert_badges(self, trial, expected, *, child=None):
        actual = set(UserBadge.objects.filter(user=child or self.child).values_list("badge_id", flat=True))
        self.assertEqual(actual, {badge.pk for badge in expected})
        self.assertEqual(trial.badges, actual)

    def test_first_automatic_quest_rechecks_meta_after_its_own_badge_and_loot(self):
        quest = QuestDefinition.objects.create(name="One factual habit", quest_type="collection",
            target_value=1, duration_days=7, is_system=True, trigger_filter={"allowed_triggers": ["habit_log"]})
        earlier = self.badge("00 earlier collector", "badges_earned_count", {"count": 1})
        completed = self.badge("Z first challenge", "quest_completed", {"quest_name": quest.name})
        trial = self.trial(habits_per_day=1, habit_xp=0)

        ingest_activity(self.child, "test_habit", "one", "habit_log")
        with self.assertNumQueries(0):
            trial.advance_challenges("habit_log", {})

        self.assert_badges(trial, [earlier, completed])
        self.assertEqual(trial.counters["drop_opportunities:quest_complete"], 1)
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 2)
        before = trial.event_count
        trial.advance_challenges("habit_log", {})
        self.assertEqual(trial.event_count, before)

    def test_first_legendary_rechecks_meta_after_the_ordered_badge_pass(self):
        earlier = self.badge("00 earlier collector", "badges_earned_count", {"count": 1})
        legendary = self.badge("Z legendary habit", "habit_taps_lifetime", {"count": 0}, rarity="legendary")
        trial = self.trial()

        BadgeService.evaluate_badges(self.child, scopes={"habit", "badges"})
        with self.assertNumQueries(0):
            trial.evaluate_badges(scopes={"habit", "badges"})

        self.assert_badges(trial, [earlier, legendary])
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 2)
        self.assertEqual((trial.streak, trial.coins, trial.total_xp), (0, 0, 0))
        self.assertEqual(trial.counters["quest_completions"], 0)

    def test_legendary_recognition_waits_for_queued_inventory_badge_awards(self):
        frame = ItemDefinition.objects.create(slug="first-legendary-frame", name="First frame", item_type="cosmetic_frame")
        DropTable.objects.create(trigger_type="badge_earned", item=frame)
        earlier = self.badge("00 earlier collector", "badges_earned_count", {"count": 2})
        collection = self.badge("A inventory collector", "cosmetic_set_owned", {"slugs": [frame.slug]})
        legendary = self.badge("Z legendary habit", "habit_taps_lifetime", {"count": 0}, rarity="legendary")
        trial = self.trial()

        BadgeService.evaluate_badges(self.child, scopes={"habit", "badges"})
        with self.assertNumQueries(0):
            trial.evaluate_badges(scopes={"habit", "badges"})

        self.assert_badges(trial, [earlier, collection, legendary])
        self.assertEqual(trial.counters["drop_opportunities:badge_earned"], 3)

    def test_streak_firsts_recheck_once_at_the_end_of_a_modeled_event(self):
        seed = self.badge("Saved recognition", "habit_taps_lifetime", {"count": 99})
        later = self.badge("00 before collector", "badges_earned_count", {"count": 2})
        earlier = self.badge("Z collector", "badges_earned_count", {"count": 1})
        for streak in (30, 60, 100):
            with self.subTest(streak=streak):
                child = make_family(f"Streak forecast {streak}", children=[{"username": f"streak-forecast-{streak}"}]).children[0]
                UserBadge.objects.create(user=child, badge=seed)
                trial = self.trial()
                trial.badges.add(seed.pk)
                trial.streak, trial.last_active = streak, 1

                GameLoopService._record_chronicle_firsts(child, "habit_log", {"streak": streak})
                with self.assertNumQueries(0):
                    trial.event("habit_log", drops=False, evaluate_source_badges=False)
                self.assert_badges(trial, [seed, earlier], child=child)

                GameLoopService._record_chronicle_firsts(child, "habit_log", {"streak": streak})
                with self.assertNumQueries(0):
                    trial.event("habit_log", drops=False, evaluate_source_badges=False)
                self.assert_badges(trial, [seed, earlier], child=child)
                self.assertNotIn(later.pk, trial.badges)

    def test_first_exchange_rechecks_meta_after_credit_but_later_exchanges_do_not(self):
        seed = self.badge("Saved recognition", "habit_taps_lifetime", {"count": 99})
        later = self.badge("00 before collector", "badges_earned_count", {"count": 2})
        earlier = self.badge("Z collector", "badges_earned_count", {"count": 1})
        UserBadge.objects.create(user=self.child, badge=seed)
        PaymentLedger.objects.create(user=self.child, amount=10, entry_type="adjustment")
        trial = self.trial()
        trial.badges.add(seed.pk)

        for _ in range(2):
            exchange = ExchangeRequest.objects.create(user=self.child, dollar_amount=1, coin_amount=10, exchange_rate=10)
            ExchangeService.approve(exchange, self.family.parents[0])
            with self.assertNumQueries(0):
                trial.coin_award(10, "money_exchange")
            self.assert_badges(trial, [seed, earlier])
        self.assertNotIn(later.pk, trial.badges)
        self.assertEqual(trial.coins, 20)

    def test_recognition_scope_and_mapping_changes_invalidate_forecast_rules(self):
        before = rules_fingerprint()
        for owner, name in ((ChronicleService, "record_first"), (recognition, "record_firsts"),
                            (firsts, "slugs_for")):
            with self.subTest(hook=name), patch.object(owner, name, alternate_recognition):
                self.assertNotEqual(before, rules_fingerprint())
