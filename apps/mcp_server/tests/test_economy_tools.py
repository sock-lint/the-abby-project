"""Persisted accounting, bounded cursors and mutation-free anonymous projections."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pydantic import ValidationError

from apps.achievements.models import Skill, SkillCategory
from apps.activity.models import ActivityEvent
from apps.mcp_server.context import override_user
from apps.mcp_server.economy_schemas import (
    EconomyScenario, GetEconomyAuditIn, GetEconomyRulesIn, ListCoinLedgerIn,
    PreviewEconomyScenarioIn,
)
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.tools.economy import (
    get_economy_audit, get_economy_rules, list_coin_ledger, preview_economy_scenario,
)
from apps.reading.models import ReadingDailyReward
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.models import CharacterProfile, DropTable, ItemDefinition
from config.tests.factories import make_family

UTC = dt_timezone.utc


class EconomyTestCase(TestCase):
    def setUp(self):
        self.a = make_family("Economy A", parents=[{"username": "economy-a", "is_staff": True}], children=[{"username": "kid-a"}])
        self.b = make_family("Economy B", parents=[{"username": "economy-b", "is_staff": True}], children=[{"username": "kid-b"}])
        self.parent, self.child = self.a.parents[0], self.a.children[0]
        self.a.family.timezone = "America/New_York"
        self.a.family.save(update_fields=["timezone"])
        # Resolve the same timezone on the separate instance retained by User.
        self.child.family = self.a.family
        self.parent.family = self.a.family

    def entry(self, amount, reason, when, user=None):
        entry = CoinLedger.objects.create(user=user or self.child, amount=amount, reason=reason)
        CoinLedger.objects.filter(pk=entry.pk).update(created_at=when)
        entry.created_at = when
        return entry

    def query_tool(self, function, params):
        with override_user(self.parent):
            return function(params)


class CoinLedgerAuditTests(EconomyTestCase):
    def test_family_local_bounds_include_dst_day_and_exact_boosted_saved_amounts(self):
        # DST starts March 8: the local day is 23 hours, 05:00Z to 04:00Z.
        start = datetime(2026, 3, 8, 5, tzinfo=UTC)
        end = datetime(2026, 3, 9, 4, tzinfo=UTC)
        self.entry(100, "adjustment", start - timedelta(microseconds=1))
        profile = CharacterProfile.objects.get(user=self.child)
        profile.coin_boost_expires_at = timezone.now() + timedelta(days=1)
        profile.save(update_fields=["coin_boost_expires_at"])
        boosted = CoinService.award_coins(self.child, 7, "reading")
        CoinLedger.objects.filter(pk=boosted.pk).update(created_at=start)
        self.entry(-4, "redemption", start + timedelta(hours=1))
        self.entry(4, "refund", end - timedelta(microseconds=1))
        self.entry(20, "exchange", start + timedelta(hours=2))
        self.entry(5, "adjustment", start + timedelta(hours=3))
        self.entry(-2, "adjustment", start + timedelta(hours=4))
        self.entry(999, "reading", end)
        self.entry(9999, "reading", start, self.b.children[0])
        ActivityEvent.objects.create(category="award", event_type="award.coins", summary="Deliberately wrong diagnostic delta", subject=self.child, coins_delta=7000)
        audit = self.query_tool(get_economy_audit, GetEconomyAuditIn(user_id=self.child.pk, since=date(2026, 3, 8), until=date(2026, 3, 8)))
        self.assertEqual(audit["period"]["timezone"], "America/New_York")
        self.assertEqual(audit["ledger"]["opening_balance"], 100)
        self.assertEqual(audit["ledger"]["earned_coins"], 14)
        self.assertEqual(audit["ledger"]["credits"], 43)
        self.assertEqual(audit["ledger"]["debits"], 6)
        self.assertEqual(audit["ledger"]["closing_balance"], 137)
        self.assertEqual(audit["ledger"]["refund_credits"], 4)
        self.assertEqual(audit["ledger"]["exchange_credits"], 20)
        self.assertEqual(audit["ledger"]["adjustment_credits"], 5)
        self.assertEqual(audit["ledger"]["adjustment_debits"], 2)

    def test_signed_cursor_ties_are_stable_and_exclude_new_rows(self):
        when = timezone.now()
        rows = [self.entry(n, "reading", when) for n in (1, 2, 3, 4)]
        first = self.query_tool(list_coin_ledger, ListCoinLedgerIn(user_id=self.child.pk, limit=2))
        self.assertEqual([e["id"] for e in first["entries"]], [rows[3].pk, rows[2].pk])
        new = self.entry(10, "reading", when - timedelta(hours=1))
        second = self.query_tool(list_coin_ledger, ListCoinLedgerIn(user_id=self.child.pk, limit=2, cursor=first["next_cursor"]))
        self.assertEqual([e["id"] for e in second["entries"]], [rows[1].pk, rows[0].pk])
        self.assertIsNone(second["next_cursor"])
        self.assertNotIn(new.pk, [e["id"] for e in second["entries"]])
        self.assertNotIn("description", first["entries"][0])

    def test_cursor_rejects_tampering_or_changed_scope_filters_timezone_and_expiry(self):
        for amount in (1, 2):
            self.entry(amount, "reading", timezone.now())
        first = self.query_tool(list_coin_ledger, ListCoinLedgerIn(user_id=self.child.pk, limit=1))
        token = first["next_cursor"]
        for kwargs in ({"cursor": token + "tamper"}, {"cursor": token, "reason": "reading"}, {"cursor": token, "since": date(2026, 1, 1)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(MCPValidationError):
                self.query_tool(list_coin_ledger, ListCoinLedgerIn(user_id=self.child.pk, **kwargs))
        with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 86402):
            with self.assertRaises(MCPValidationError):
                self.query_tool(list_coin_ledger, ListCoinLedgerIn(user_id=self.child.pk, cursor=token))
        self.a.family.timezone = "UTC"
        self.a.family.save(update_fields=["timezone"])
        with self.assertRaises(MCPValidationError):
            self.query_tool(list_coin_ledger, ListCoinLedgerIn(user_id=self.child.pk, cursor=token))

    def test_family_and_child_boundaries_are_enforced_for_both_tools(self):
        for function, schema in ((list_coin_ledger, ListCoinLedgerIn), (get_economy_audit, GetEconomyAuditIn)):
            with self.subTest(tool=function.__name__), override_user(self.parent), self.assertRaises(MCPNotFoundError):
                function(schema(user_id=self.b.children[0].pk))
            with self.subTest(tool=function.__name__), override_user(self.child), self.assertRaises(MCPPermissionDenied):
                function(schema(user_id=self.b.children[0].pk))
            with override_user(self.child):
                self.assertEqual(function(schema())["user_id"], self.child.pk)

    def test_unknown_reason_and_excessive_or_reversed_periods_are_rejected(self):
        for function, params in (
            (list_coin_ledger, ListCoinLedgerIn(reason="unrecognized")),
            (get_economy_audit, GetEconomyAuditIn(since=date(2025, 1, 1), until=date(2026, 1, 2))),
            (get_economy_audit, GetEconomyAuditIn(since=date(2026, 1, 2), until=date(2026, 1, 1))),
            (get_economy_audit, GetEconomyAuditIn(until=date.max)),
        ):
            with self.subTest(params=params), self.assertRaises(MCPValidationError):
                self.query_tool(function, params)
        with self.assertRaises(ValidationError):
            ListCoinLedgerIn(limit=201)

    def test_receipts_are_reported_separately_without_adding_or_reconstructing_awards(self):
        from apps.projects.models import Project, ProjectCompletionRewardReceipt
        from apps.quests.models import ChallengeGoal, ChallengeOccurrence, DailyBonus
        when = timezone.now()
        today = timezone.localdate(timezone=ZoneInfo("America/New_York"))
        self.entry(10, "reading", when)
        ReadingDailyReward.objects.create(user=self.child, day=today, awarded_at=when, minutes_credited=10, xp_awarded=30, coins_awarded=10)
        ReadingDailyReward.objects.create(user=self.b.children[0], day=today, awarded_at=when, minutes_credited=10, xp_awarded=300, coins_awarded=100)
        DailyBonus.objects.create(user=self.child, date=today, awarded_at=when, coins_awarded=10, xp_awarded=20)
        goal = ChallengeGoal.objects.create(user=self.child, name="Private goal", family=self.a.family, metric="count", target=1, unit="actions", timezone_name="America/New_York", starts_at=when, ends_at=when + timedelta(days=1))
        ChallengeOccurrence.objects.create(goal=goal, starts_at=when, ends_at=when + timedelta(days=1), awarded_at=when, reward_receipt={"coins": 9, "xp": 18, "items": []})
        project = Project.objects.create(title="Historic guard", assigned_to=self.child, created_by=self.parent)
        ProjectCompletionRewardReceipt.objects.create(project=project, user=self.child, historical=True)
        audit = self.query_tool(get_economy_audit, GetEconomyAuditIn(user_id=self.child.pk, since=today, until=today))
        self.assertEqual(audit["ledger"]["earned_coins"], 10)
        self.assertEqual(audit["receipts"]["reading"], {"count": 1, "coins_recorded": 10, "xp_recorded": 30})
        self.assertEqual(audit["receipts"]["automatic_goals"]["coins_recorded"], 9)
        self.assertEqual(audit["receipts"]["project_completion_guards"], {"new_guards": 0, "historical_guards_recorded": 1})
        self.assertNotIn("Private goal", str(audit))
        with patch("apps.mcp_server.economy.MAX_GOAL_RECEIPTS", 0):
            capped = self.query_tool(get_economy_audit, GetEconomyAuditIn(user_id=self.child.pk, since=today, until=today))
        self.assertTrue(capped["receipts"]["automatic_goals"]["incomplete"])
        self.assertIsNone(capped["receipts"]["automatic_goals"]["coins_recorded"])


class AnonymousPreviewTests(EconomyTestCase):
    def setUp(self):
        super().setUp()
        category = SkillCategory.objects.create(name="Language Arts")
        Skill.objects.create(category=category, name="Reading Comprehension")
        self.item = ItemDefinition.objects.create(slug="audit-food", name="Food", item_type="food", coin_value=4)
        DropTable.objects.create(trigger_type="reading_logged", item=self.item, weight=1)

    def preview(self, **scenario):
        params = PreviewEconomyScenarioIn(scenarios=[EconomyScenario(**scenario)])
        return self.query_tool(preview_economy_scenario, params)["scenarios"][0]

    def test_rules_reflect_runtime_settings_and_constants(self):
        original = self.query_tool(get_economy_rules, GetEconomyRulesIn())
        with override_settings(COINS_PER_HOUR=13), patch("apps.rpg.services.BASE_CHECK_IN_COINS", 9):
            updated = self.query_tool(get_economy_rules, GetEconomyRulesIn())
        self.assertEqual(updated["coins_per_hour"], 13)
        self.assertEqual(updated["check_in"]["base_coins"], 9)
        self.assertNotEqual(original["rules_fingerprint"], updated["rules_fingerprint"])
        self.assertNotIn("family", str(updated).lower())

    def test_reading_boosts_rounding_and_streak_checkin_stack_exactly_once(self):
        normal = self.preview(days=1, reading_minutes_per_day=10, target_cost_coins=16)
        boosted = self.preview(days=1, reading_minutes_per_day=10, coin_boost=True, xp_boost=True, drop_boost=True, target_cost_coins=16)
        self.assertEqual(normal["total_projected_coins"], 10)  # 5 reading + int(5 * 1.1)
        self.assertEqual(boosted["total_projected_coins"], 15)  # 10 reading + unchanged 5 check-in
        self.assertEqual(normal["total_distributed_xp"], 15)
        self.assertEqual(boosted["total_distributed_xp"], 30)
        self.assertAlmostEqual(normal["drop_expected_value"]["expected_item_units"], 0.25)
        self.assertAlmostEqual(boosted["drop_expected_value"]["expected_item_units"], 0.45)
        self.assertIsNone(boosted["time_to_afford"]["day"])
        self.assertEqual(self.preview(days=2, reading_minutes_per_day=10, target_cost_coins=16)["time_to_afford"]["day"], 2)

    def test_weekly_subtotals_cover_partial_week_and_catalog_fingerprint_tracks_pool_changes(self):
        scenario = self.preview(days=8, reading_minutes_per_day=10)
        self.assertEqual([(week["starts_day"], week["ends_day"]) for week in scenario["weekly_totals"]], [(1, 7), (8, 8)])
        self.assertEqual(sum(week["coins"] for week in scenario["weekly_totals"]), scenario["total_projected_coins"])
        self.assertEqual(sum(week["distributed_xp"] for week in scenario["weekly_totals"]), scenario["total_distributed_xp"])
        second = ItemDefinition.objects.create(slug="other-food", name="Another food", item_type="food")
        DropTable.objects.create(trigger_type="reading_logged", item=second, weight=1)
        changed = self.preview(days=8, reading_minutes_per_day=10)
        self.assertNotEqual(scenario["catalog_fingerprint"], changed["catalog_fingerprint"])
        self.assertIsNone(changed["time_to_afford"]["within_horizon"])

    def test_reading_requires_threshold_and_existing_skill_but_not_more_rewards_for_more_minutes(self):
        self.assertEqual(self.preview(days=1, reading_minutes_per_day=9)["total_projected_coins"], 0)
        self.assertEqual(self.preview(days=1, reading_minutes_per_day=600)["total_distributed_xp"], 15)
        Skill.objects.filter(name="Reading Comprehension").delete()
        no_skill = self.preview(days=1, reading_minutes_per_day=10)
        self.assertEqual(no_skill["total_distributed_xp"], 0)
        self.assertEqual(no_skill["total_projected_coins"], 10)

    def test_source_daily_caps_duration_clamp_and_tag_rounding_reuse_actual_pure_calculation(self):
        scenario = self.preview(days=1, creations_per_day=8, creation_secondary_skill=True, movement_sessions_per_day=[{"duration_minutes": 1440, "intensity": "high", "xp_weights": [1]}] * 5, chores_per_day=[{"count": 2, "coin_reward": 7, "xp_reward": 1, "xp_weights": [1, 1]}], coin_boost=True, xp_boost=True)
        # Three movement awards at 180 base -> 360 boosted each, two creations
        # at 20 distributed XP, and two 2-XP chores split exactly 1+1 each.
        self.assertEqual(scenario["total_distributed_xp"], 1080 + 40 + 4)
        self.assertEqual(scenario["total_projected_coins"], 28 + 5)
        self.assertEqual(scenario["caps"]["movement_skipped"], 2)
        self.assertEqual(scenario["caps"]["creations_skipped"], 6)
        unboosted = self.preview(days=1, chores_per_day=[{"xp_reward": 1, "xp_weights": [1, 1]}])
        self.assertEqual(unboosted["total_distributed_xp"], 0)  # round(0.5) twice, as real distribution
        no_tags = self.preview(days=1, movement_sessions_per_day=[{"duration_minutes": 30}])
        self.assertEqual(no_tags["total_distributed_xp"], 0)
        self.assertEqual(no_tags["total_projected_coins"], 5)

    def test_drop_ev_excludes_unsupported_and_high_level_rows_and_caps_effective_rate(self):
        unsupported = ItemDefinition.objects.create(slug="unfitted-accessory", name="No fitted art", item_type="cosmetic_pet_accessory")
        high_level = ItemDefinition.objects.create(slug="level-food", name="Later food", item_type="food")
        DropTable.objects.create(trigger_type="reading_logged", item=unsupported, weight=999)
        DropTable.objects.create(trigger_type="reading_logged", item=high_level, weight=999, min_level=6)
        scenario = self.preview(days=1, reading_minutes_per_day=10, starting_streak=9999, drop_boost=True)
        self.assertEqual(scenario["daily"][0]["check_in_coins"], 15)
        self.assertEqual(scenario["drop_expected_value"]["expected_item_units"], 0.9)
        self.assertEqual(scenario["drop_expected_value"]["by_trigger"][0]["unsupported_rows_excluded"], 1)
        self.assertEqual(scenario["drop_expected_value"]["by_item"], [{"trigger": "reading_logged", "item_slug": "audit-food", "expected_units": 0.9}])
        with patch.dict("apps.rpg.services.BASE_DROP_RATES", {"reading_logged": 0.9}):
            capped = self.preview(days=1, reading_minutes_per_day=10, starting_streak=9999, drop_boost=True)
        self.assertEqual(capped["drop_expected_value"]["expected_item_units"], 1.0)
        with patch("apps.mcp_server.economy.MAX_DROP_ROWS", 0), self.assertRaises(MCPValidationError):
            self.preview(days=1, reading_minutes_per_day=10)

    def test_invalid_zero_weight_catalog_is_reported_instead_of_a_false_successful_projection(self):
        DropTable.objects.filter(trigger_type="reading_logged").update(weight=0)
        with self.assertRaisesRegex(MCPValidationError, "positive effective selection weight"):
            self.preview(days=1, reading_minutes_per_day=10)

    def test_one_project_and_its_conditional_goal_stack_rewards_without_an_extra_source_event(self):
        DropTable.objects.create(trigger_type="project_complete", item=self.item, weight=1)
        scenario = self.preview(days=2, coin_boost=True, xp_boost=True, target_cost_coins=70, one_off_awards=[
            {"kind": "project", "source_key": "project-a", "day": 1, "coin_reward": 30, "xp_reward": 50, "xp_weights": [1]},
            {"kind": "automatic_challenge", "source_key": "goal-a", "qualifying_source_key": "project-a", "day": 1, "coin_reward": 10, "xp_reward": 20, "xp_weights": [1]},
        ])
        # Project is boostable; automatic goals use adjustment (not boostable).
        self.assertEqual(scenario["total_projected_coins"], 60 + 10 + 5)
        self.assertEqual(scenario["total_distributed_xp"], 100 + 40)
        self.assertEqual(scenario["daily"][0]["game_loop_activity_count"], 1)
        self.assertEqual(scenario["daily"][0]["one_off_award_count"], 2)
        self.assertEqual(scenario["daily"][1]["check_in_coins"], 0)
        self.assertEqual(scenario["time_to_afford"]["day"], 1)
        self.assertEqual(scenario["drop_expected_value"]["expected_item_units"], 1)
        self.assertEqual(scenario["drop_expected_value"]["by_trigger"][0]["roll_opportunities"], 1)

    def test_once_only_replays_gap_streaks_and_milestone_direct_xp_are_not_boosted_twice(self):
        replay = self.preview(days=1, starting_streak=10, one_off_awards=[
            {"kind": "project", "source_key": "paid", "day": 1, "coin_reward": 100, "xp_reward": 100, "xp_weights": [1], "already_rewarded": True},
        ])
        self.assertEqual(replay["total_projected_coins"], 0)
        self.assertEqual(replay["total_distributed_xp"], 0)
        self.assertEqual(replay["daily"][0]["game_loop_activity_count"], 0)
        gap = self.preview(days=3, starting_streak=10, coin_boost=True, xp_boost=True, one_off_awards=[
            {"kind": "project", "source_key": "p", "day": 1},
            {"kind": "milestone", "source_key": "m", "day": 3, "coin_reward": 20, "xp_reward": 15},
        ])
        self.assertEqual([row["resulting_streak"] for row in gap["daily"]], [11, 11, 1])
        self.assertEqual(gap["daily"][1]["check_in_coins"], 0)
        self.assertEqual(gap["total_distributed_xp"], 15)
        self.assertEqual(gap["daily"][2]["direct_coins"], 40)

    def test_tracked_work_splits_share_one_daily_drop_opportunity_after_ten_new_minutes(self):
        DropTable.objects.create(trigger_type="clock_out", item=self.item, weight=1)
        split = self.preview(days=1, one_off_awards=[
            {"kind": "tracked_work", "source_key": "first", "day": 1, "duration_minutes": 5, "coin_reward": 1},
            {"kind": "tracked_work", "source_key": "second", "day": 1, "duration_minutes": 5, "coin_reward": 1},
            {"kind": "tracked_work", "source_key": "third", "day": 1, "duration_minutes": 60, "coin_reward": 5},
        ])
        self.assertEqual(split["daily"][0]["game_loop_activity_count"], 3)
        self.assertEqual(split["drop_expected_value"]["by_trigger"][0]["roll_opportunities"], 1)
        self.assertEqual(split["total_projected_coins"], 7 + 5)
        short = self.preview(days=1, one_off_awards=[{"kind": "tracked_work", "source_key": "short", "day": 1, "duration_minutes": 9}])
        self.assertEqual(short["drop_expected_value"]["expected_item_units"], 0)
        self.assertEqual(short["daily"][0]["check_in_coins"], 5)

    def test_one_off_sources_have_bounded_unique_valid_receipts(self):
        invalid = [
            {"days": 1, "one_off_awards": [{"kind": "project", "source_key": "p", "day": 2}]},
            {"one_off_awards": [{"kind": "project", "source_key": "p", "day": 1}] * 2},
            {"one_off_awards": [{"kind": "tracked_work", "source_key": "t", "day": 1}]},
            {"one_off_awards": [{"kind": "milestone", "source_key": "m", "day": 1, "xp_weights": [1]}]},
            {"one_off_awards": [{"kind": "automatic_challenge", "source_key": "g", "day": 1, "qualifying_source_key": "unknown"}]},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                EconomyScenario(**payload)

    def test_no_eligible_drop_pool_returns_zero_and_empty_plan_does_not_invent_checkin(self):
        DropTable.objects.all().delete()
        self.assertEqual(self.preview(days=1, reading_minutes_per_day=10)["drop_expected_value"]["expected_item_units"], 0)
        empty = self.preview(days=31, initial_coins=7, target_cost_coins=7)
        self.assertEqual(empty["total_projected_coins"], 0)
        self.assertEqual(empty["time_to_afford"]["day"], 0)
        self.assertEqual(empty["daily"][0]["resulting_streak"], 0)

    def test_inputs_are_bounded_and_private_targeting_is_not_accepted(self):
        for payload in ({"days": 32}, {"character_level": 7}, {"days": True}, {"user_id": self.child.pk}, {"movement_sessions_per_day": [{"duration_minutes": 20}] * 13}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                EconomyScenario(**payload)
        for weights in ([-1], [0], [True], [10001]):
            with self.subTest(weights=weights), self.assertRaises((MCPValidationError, ValidationError)):
                self.preview(chores_per_day=[{"xp_weights": weights}])
        with self.assertRaises(ValidationError):
            PreviewEconomyScenarioIn(scenarios=[EconomyScenario()] * 5)

    def test_comparisons_and_all_audit_tools_are_read_only_and_preview_never_rolls_rng(self):
        params = PreviewEconomyScenarioIn(scenarios=[EconomyScenario(label="Normal", days=1, reading_minutes_per_day=10), EconomyScenario(label="Boosted", days=1, reading_minutes_per_day=10, coin_boost=True)])
        with CaptureQueriesContext(connection) as queries, patch("apps.rpg.services.random.random", side_effect=AssertionError("RNG must not run")), patch("apps.achievements.services.AwardService.grant", side_effect=AssertionError("No grants")):
            result = self.query_tool(preview_economy_scenario, params)
            repeated = self.query_tool(preview_economy_scenario, params)
            self.query_tool(get_economy_rules, GetEconomyRulesIn())
            self.query_tool(list_coin_ledger, ListCoinLedgerIn(user_id=self.child.pk))
            self.query_tool(get_economy_audit, GetEconomyAuditIn(user_id=self.child.pk))
        self.assertEqual(result, repeated)
        self.assertEqual(result["comparison"]["differences_from_first"][0]["coins"], 5)
        self.assertTrue(result["conditional_rewards_excluded"])
        writes = [row["sql"] for row in queries if row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE"))]
        self.assertEqual(writes, [])
