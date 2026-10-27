"""Behavioral checks for forecasting policies, horizons and honest coverage."""

from io import StringIO
from dataclasses import replace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Badge, XP_THRESHOLDS
from apps.movement.services import MovementSessionService
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import DropTable
from apps.rpg.progression import describe_progression, normalize_config, simulate_progression
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import DEFAULTS, Trial, percentile, rules_fingerprint
from apps.rpg.services import StreakService


def alternate_streak_bonus(streak):
    return {"check_in_multiplier": 1.5, "check_in_coins": 7, "drop_bonus": 0.1, "intensity": 0.25}


def alternate_streak_presentation(profile):
    return {"active_today": False}


def quiet_config(**changes):
    return {
        **DEFAULTS,
        "horizon_days": 30,
        "trials": 1,
        "active_days_per_week": 7,
        "reading_minutes": 0,
        "project_minutes": 0,
        "chores_per_day": 0,
        "habits_per_day": 0,
        "movement_sessions_per_day": 0,
        "creations_per_day": 0,
        "journal_per_day": False,
        "expeditions_per_day": 0,
        **changes,
    }


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class ProgressionEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())

    def setUp(self):
        self.catalog = load_catalog()

    def test_config_rejects_unknown_types_and_unbounded_work(self):
        for config in (
            False,
            [],
            "",
            {"trials": 41},
            {"horizon_days": 400},
            {"trials": True},
            {"seed": -1},
            {"journal_per_day": "yes"},
            {"user_id": 5},
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                normalize_config(config)
        with self.assertRaisesMessage(ValueError, "work units"):
            normalize_config({"horizon_days": 365, "trials": 40, "chores_per_day": 10})

    def test_all_editable_presets_fit_the_aggregate_budget(self):
        for preset in describe_progression()["presets"]:
            self.assertEqual(normalize_config(preset["config"]), preset["config"])

    def test_metadata_has_no_household_inputs_and_reports_partial_model(self):
        result = describe_progression()
        self.assertEqual(set(result["defaults"]), set(DEFAULTS))
        self.assertTrue(result["coverage"]["excluded"])
        self.assertEqual(
            result["coverage"]["initial_state"],
            {
                "coins": 0,
                "xp": 0,
                "pets": 0,
                "mounts": 0,
                "inventory": 0,
            },
        )
        self.assertEqual(result["catalog"]["supported_pet_variants"], 35)
        self.assertEqual(len(result["rules_fingerprint"]), 64)

    def test_short_project_facts_cannot_bootstrap_drops_or_expeditions(self):
        goal = QuestDefinition.objects.create(
            name="A saved minute counts",
            description="One factual work session",
            quest_type="collection",
            target_value=1,
            duration_days=7,
            trigger_filter={"allowed_triggers": ["clock_out"]},
            is_system=True,
        )
        loaded = load_catalog()
        catalog = replace(loaded, quests=[q for q in loaded.quests if q.pk == goal.pk], badges=[])
        trial = Trial(quiet_config(project_minutes=1, expeditions_per_day=1), catalog, 3)
        self.assertIn("clock_out", trial._enabled_triggers())
        self.assertNotIn("expedition_returned", trial._enabled_triggers())
        self.assertFalse(any(key.startswith(("pet:", "middle:", "mount:")) for key in trial.finite_keys))
        for day in range(1, 31):
            trial.daily(day)
        self.assertEqual(trial.counters["project_sessions"], 30)
        self.assertEqual(trial.counters["drop_opportunities:clock_out"], 0)
        self.assertEqual(trial.counters["drop_opportunities:quest_complete"], 1)
        self.assertEqual(len(trial.pets), 0)
        self.assertIn(goal.pk, trial.completed_quests)

    def test_zero_weight_direct_rows_cannot_bootstrap_companion_targets(self):
        DropTable.objects.filter(trigger_type="clock_out").update(weight=0)
        catalog = replace(load_catalog(), quests=[], badges=[])
        trial = Trial(quiet_config(project_minutes=10, expeditions_per_day=1), catalog, 3)
        self.assertNotIn("expedition_returned", trial._enabled_triggers())
        self.assertFalse(any(key.startswith(("pet:", "middle:", "mount:")) for key in trial.finite_keys))
        trial.daily(1)
        self.assertEqual(trial.counters["drop_opportunities"], 1)
        self.assertFalse(trial.pets)

    def test_reading_is_one_daily_award_without_daily_bonus_or_automatic_goals(self):
        trial = Trial(quiet_config(reading_minutes=240), self.catalog, 3)
        trial.daily(1)
        self.assertEqual(trial.source_totals["reading"]["xp"], 15)
        self.assertEqual(trial.source_totals["reading"]["coins"], 5)
        self.assertNotIn("daily_bonus", trial.source_totals)
        self.assertFalse(trial.completed_quests)
        self.assertEqual(trial.counters["drop_opportunities"], 1)

    def test_movement_cap_does_not_drop_saved_sources_or_challenge_credit(self):
        trial = Trial(quiet_config(movement_sessions_per_day=6, movement_minutes=20), self.catalog, 3)
        trial.daily(1)
        self.assertEqual(trial.counters["movement_sessions"], 6)
        self.assertEqual(trial.counters["movement_minutes"], 120)
        self.assertEqual(
            trial.source_totals["movement"]["xp"],
            MovementSessionService.DAILY_REWARD_LIMIT * MovementSessionService.compute_xp_pool(20, "medium"),
        )
        self.assertEqual(trial.counters["drop_opportunities:movement_session"], 3)
        self.assertEqual(trial.counters["drop_opportunities"], 3 + len(trial.badges) + trial.counters["quest_completions"])
        self.assertEqual(trial.source_totals["daily_bonus"]["coins"], 10)

    def test_creation_limit_keeps_lifetime_count_but_caps_rewards(self):
        trial = Trial(quiet_config(creations_per_day=4), self.catalog, 3)
        trial.daily(1)
        self.assertEqual(trial.counters["creations"], 4)
        self.assertEqual(trial.source_totals["creations"]["xp"], 20)
        self.assertEqual(trial.counters["drop_opportunities:creation_logged"], 2)
        self.assertEqual(trial.counters["drop_opportunities"], 2 + len(trial.badges) + trial.counters["quest_completions"])
        self.assertEqual(trial.counters["daily_bonus_day"], 0)

    def test_attendance_does_not_earn_completed_time_entry_streak_badge(self):
        trial = Trial(quiet_config(reading_minutes=10), self.catalog, 3)
        for day in range(1, 8):
            trial.daily(day)
        self.assertEqual(trial.streak, 7)
        self.assertFalse(any(b.pk in trial.badges for b in self.catalog.badges if b.criteria_type == "streak_days"))

    def test_finite_pet_badges_include_the_live_care_evaluation_scope(self):
        trial = Trial(quiet_config(habits_per_day=1), self.catalog, 3)
        pet_badges = [b for b in self.catalog.badges if b.criteria_type == "pets_hatched"]
        self.assertTrue(pet_badges)
        first_hatch = next(badge for badge in pet_badges if badge.criteria_value.get("count") == 1)
        self.assertIn(f"badge:{first_hatch.pk}", trial.finite_keys)

    def test_sub_ten_minute_movement_does_not_invent_unscoped_awards(self):
        trial = Trial(quiet_config(movement_sessions_per_day=1, movement_minutes=1), self.catalog, 3)
        trial.daily(1)
        self.assertEqual(trial.counters["movement_sessions"], 1)
        self.assertFalse(
            any(b.pk in trial.badges for b in self.catalog.badges if b.criteria_type == "movement_sessions_logged")
        )

    def test_raw_xp_levels_share_live_curve_and_do_not_stop_credit_at_cap(self):
        trial = Trial(quiet_config(), self.catalog, 3)
        trial.day = 1
        for amount, expected_level in ((100, 1), (200, 2), (300, 3), (400, 4), (500, 5), (1000, 6), (1000, 6)):
            trial.award_xp(amount, trial.tags["reading"], "reading")
            self.assertEqual(trial.level, expected_level)
        self.assertGreater(trial.total_xp, XP_THRESHOLDS[6])

    def test_calendar_visits_preserve_idle_days_and_reset_streak(self):
        trial = Trial(quiet_config(reading_minutes=10, active_days_per_week=3), self.catalog, 3)
        for day in range(1, 9):
            trial.daily(day)
        self.assertEqual(trial.trace[6]["active_days"], 3)
        self.assertEqual(trial.trace[6]["total_xp"], trial.trace[2]["total_xp"])
        self.assertEqual(trial.streak, 1)
        self.assertEqual(trial.trace[-1]["active_days"], 4)

    def test_all_horizons_have_calendar_traces_and_censored_milestones(self):
        for horizon in (30, 90, 180, 365):
            result = simulate_progression(quiet_config(horizon_days=horizon))
            self.assertEqual(len(result["trace"]), horizon)
            self.assertEqual(result["trace"][-1]["day"], horizon)
            milestone = next(m for m in result["milestones"] if m["key"] == "first_pet")
            self.assertEqual(milestone["completion_rate"], 0)
            self.assertIsNone(milestone["p50_days"])

    def test_seeded_journey_is_bounded_and_source_totals_reconcile(self):
        result = simulate_progression({**DEFAULTS, "trials": 1, "horizon_days": 365})
        self.assertLessEqual(len(result["journey"]["events"]), 1000)
        self.assertTrue(result["journey"]["truncated"])
        self.assertEqual(sum(row["coins"] for row in result["flows"]["sources"]), result["summary"]["coins_p50"])
        self.assertEqual(sum(row["xp"] for row in result["flows"]["sources"]), result["summary"]["total_xp_p50"])
        self.assertEqual(sum(result["summary"]["finite_breakdown"].values()), result["summary"]["finite_content_total"])

    def test_badge_evaluation_uses_live_catalog_order(self):
        self.assertEqual(
            [b.pk for b in self.catalog.badges],
            list(Badge.objects.filter(pk__in=[b.pk for b in self.catalog.badges]).values_list("pk", flat=True)),
        )

    def test_rules_fingerprint_tracks_domain_formula_changes(self):
        before = rules_fingerprint()
        with patch.dict(XP_THRESHOLDS, {6: 2700}):
            self.assertNotEqual(before, rules_fingerprint())

    def test_streak_bonus_formula_changes_invalidate_forecast_rules(self):
        before = rules_fingerprint()
        with patch.object(StreakService, "bonus_for_streak", alternate_streak_bonus):
            self.assertNotEqual(before, rules_fingerprint())

    def test_streak_header_presentation_does_not_invalidate_forecast_rules(self):
        before = rules_fingerprint()
        with patch.object(StreakService, "bonus_status", alternate_streak_presentation):
            self.assertEqual(before, rules_fingerprint())

    def test_expired_oneoff_targets_are_reported_without_claiming_consumption(self):
        quest = QuestDefinition.objects.create(
            name="An expedition on the first visit",
            description="A missed window",
            quest_type="collection",
            target_value=1,
            duration_days=1,
            trigger_filter={"allowed_triggers": ["expedition_returned"]},
            is_system=True,
        )
        trial = Trial(quiet_config(chores_per_day=1, expeditions_per_day=1), load_catalog(), 3)
        trial.daily(1)
        trial.daily(2)
        self.assertEqual(trial.trace[-1]["expired_oneoff_challenges"], 1)
        self.assertIn(f"quest:{quest.pk}", trial.finite_keys)
        self.assertNotIn(f"quest:{quest.pk}", trial.completed_finite)

    def test_percentiles_are_conditional_and_use_real_integer_days(self):
        self.assertIsNone(percentile([], 0.5))
        self.assertEqual(percentile([8, 2, 3, 20], 0.5), 3)
        self.assertEqual(percentile([8, 2, 3, 20], 0.9), 20)
