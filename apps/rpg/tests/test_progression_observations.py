"""Observed accounting is family scoped and cannot validate an undeployed policy."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory
from apps.chores.models import Chore, ChoreCompletion
from apps.creations.models import Creation
from apps.families.models import LiveTestFamily
from apps.habits.models import Habit, HabitLog
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.movement.models import MovementSession, MovementType
from apps.projects.models import Project
from apps.reading.models import ReadingBook, ReadingSession
from apps.rewards.models import CoinLedger, Reward
from apps.rpg.models import ItemDefinition
from apps.timecards.models import TimeEntry
from config.tests.factories import make_family


class ProgressionObservationsTests(TestCase):
    def setUp(self):
        self.family = make_family(
            parents=[{"username": "observer-parent", "is_staff": True}],
            children=[{"username": "new-child", "display_name": "Private name"}],
        )
        self.parent = self.family.parents[0]
        self.child = self.family.children[0]
        self.other = make_family(children=[{"username": "other-child"}]).children[0]
        self.now = datetime(2026, 10, 18, 20, tzinfo=dt_timezone.utc)
        User.objects.filter(pk__in=[self.child.pk, self.other.pk]).update(date_joined=self.now - timedelta(days=20))

    def observe(self, **kwargs):
        from apps.rpg.progression.observations import economy_observations
        with patch("apps.rpg.progression.observations.timezone.now", return_value=self.now):
            return economy_observations(self.parent, **kwargs)

    def entry(self, amount, reason="adjustment", source="", *, child=None, when=None):
        entry = CoinLedger.objects.create(user=child or self.child, amount=amount, reason=reason, source=source)
        CoinLedger.objects.filter(pk=entry.pk).update(created_at=when or self.now - timedelta(days=1))
        return entry

    def reading(self, *, child=None, day=None, minutes=1):
        child = child or self.child
        book = ReadingBook.objects.create(
            user=child, title="Synthetic reading", client_request_id=uuid4(), create_payload={},
        )
        return ReadingSession.objects.create(
            user=child, book=book, occurred_on=day or (self.now - timedelta(days=1)).date(),
            duration_minutes=minutes, reflection="Private reading reflection", client_request_id=uuid4(),
            create_payload={},
        )

    def test_non_earning_saved_reading_establishes_a_meaningful_day(self):
        self.reading(minutes=0)
        result = self.observe()
        self.assertEqual(result["activity"]["meaningful_active_child_days"], 1)
        self.assertEqual(result["activity"]["meaningful_active_children"], 1)
        self.assertEqual(result["activity"]["ledger_active_child_days"], 0)
        self.assertEqual(result["status"], "observations_available")
        self.assertEqual(result["earning_pace"]["status"], "insufficient_evidence")
        self.assertIsNone(result["earning_pace"]["coins_per_active_day"])

    def test_empty_active_cohort_is_insufficient_not_a_passing_experiment(self):
        User.objects.filter(pk=self.child.pk).update(is_active=False)
        result = self.observe()
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["cohort"]["eligible_children"], 0)
        self.assertEqual(result["activity"]["ledger_active_children"], 0)
        self.assertIsNone(result["policy"]["installed_daily_automatic_coin_cap"])
        self.assertFalse(result["policy"]["is_live_experiment"])

    def test_attributed_sources_reconcile_ledger_without_inference_or_family_leak(self):
        self.entry(150, "expedition", "expedition")
        self.entry(250, source="expedition_salvage")
        self.entry(500, source="coin_pouch")
        unknown = self.entry(23)
        CoinLedger.objects.filter(pk=unknown.pk).update(description="Opened coin pouch: looks authoritative")
        self.entry(10, "reading")
        self.entry(-50, "redemption")
        self.entry(10000, source="coin_pouch", child=self.other)
        result = self.observe()
        self.assertEqual(result["status"], "observations_available")
        self.assertEqual(result["ledger"]["credits"], 933)
        self.assertEqual(result["ledger"]["debits"], 50)
        self.assertEqual(result["ledger"]["net_change"], 883)
        self.assertEqual(result["automatic_sources"]["coins"], 900)
        self.assertEqual(result["automatic_sources"]["unattributed_positive_adjustments"], 23)
        self.assertFalse(result["automatic_sources"]["attribution_complete"])
        self.assertEqual(result["automatic_sources"]["child_days_over_100"], 1)
        self.assertEqual(result["activity"], {"ledger_active_children": 1, "ledger_active_child_days": 1,
                                              "meaningful_active_children": 0, "meaningful_active_child_days": 0})
        rendered = str(result)
        for private in ["Private name", "new-child", "other-child", "observer-parent"]:
            self.assertNotIn(private, rendered)

    def test_local_days_and_opening_balance_use_family_timezone(self):
        self.family.family.timezone = "America/New_York"
        self.family.family.save(update_fields=["timezone"])
        User.objects.filter(pk=self.child.pk).update(date_joined=datetime(2026, 2, 20, tzinfo=dt_timezone.utc))
        self.now = datetime(2026, 3, 9, 20, tzinfo=dt_timezone.utc)
        before = datetime(2026, 3, 8, 4, 59, 59, tzinfo=dt_timezone.utc)
        self.entry(40, when=before)
        self.entry(50, source="coin_pouch", when=before + timedelta(seconds=1))
        self.entry(1000, source="coin_pouch", when=datetime(2026, 3, 9, 4, tzinfo=dt_timezone.utc))
        result = self.observe(since=date(2026, 3, 8), until=date(2026, 3, 8))
        self.assertEqual(result["period"]["timezone"], "America/New_York")
        self.assertEqual(result["ledger"]["opening_balance"], 40)
        self.assertEqual(result["ledger"]["credits"], 50)
        self.assertEqual(result["ledger"]["closing_balance"], 90)
        self.assertEqual(result["cohort"]["eligible_child_days"], 1)

    def test_staff_inactive_and_provisioned_test_children_are_excluded(self):
        User.objects.filter(pk=self.child.pk).update(is_staff=True)
        self.entry(50, source="coin_pouch")
        self.assertEqual(self.observe()["cohort"]["eligible_children"], 0)
        User.objects.filter(pk=self.child.pk).update(is_staff=False, is_active=False)
        self.assertEqual(self.observe()["cohort"]["eligible_children"], 0)
        User.objects.filter(pk=self.child.pk).update(is_active=True)
        Reward.objects.create(family=self.family.family, name="Observer-only offer", cost_coins=10)
        LiveTestFamily.objects.create(
            namespace="abby-live-checks-v1", family=self.family.family, parent=self.parent, child=self.child,
        )
        result = self.observe()
        self.assertTrue(result["cohort"]["observer_family_excluded"])
        self.assertEqual(result["cohort"]["eligible_children"], 0)
        self.assertEqual(result["shop_rewards"], [])

    def test_current_authorization_is_checked_again_by_service(self):
        from apps.rpg.progression.observations import economy_observations
        for changes in [{"is_staff": False}, {"is_active": False}, {"role": "child"}]:
            User.objects.filter(pk=self.parent.pk).update(**changes)
            with self.subTest(changes=changes), self.assertRaises(PermissionDenied):
                economy_observations(self.parent)
            User.objects.filter(pk=self.parent.pk).update(is_staff=True, is_active=True, role="parent")

    def test_oversized_and_future_periods_fail_before_ledger_read(self):
        for kwargs in [
            {"since": date(2026, 9, 1), "until": date(2026, 10, 18)},
            {"since": date(2026, 10, 18), "until": date(2026, 10, 17)},
            {"until": date(2026, 10, 19)},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.observe(**kwargs)

    def test_summary_is_read_only_and_has_explicit_non_engagement_denominators(self):
        self.entry(5, "reading")
        def only_reads(execute, sql, params, many, context):
            self.assertTrue(sql.lstrip().upper().startswith("SELECT"), sql)
            return execute(sql, params, many, context)
        with connection.execute_wrapper(only_reads):
            result = self.observe()
        self.assertEqual(result["cohort"]["eligible_child_days"], 21)
        self.assertIn("not an engagement", " ".join(result["notes"]))

    def test_registered_children_without_transactions_are_insufficient(self):
        result = self.observe()
        self.assertEqual(result["cohort"]["eligible_children"], 1)
        self.assertEqual(result["cohort"]["eligible_child_days"], 21)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["automatic_sources"]["attribution_complete"])

    def test_capacity_failures_report_no_partial_or_zero_amounts(self):
        self.entry(80, source="coin_pouch")
        with patch("apps.rpg.progression.observations.MAX_COHORT_CHILDREN", 0):
            result = self.observe()
        self.assertEqual(result["status"], "cohort_limit_exceeded")
        self.assertIsNone(result["ledger"]["credits"])
        self.assertIsNone(result["automatic_sources"]["coins"])
        self.assertTrue(result["cohort"]["truncated"])
        with patch("apps.rpg.progression.observations.MAX_LEDGER_ROWS", 0):
            result = self.observe()
        self.assertEqual(result["status"], "ledger_limit_exceeded")
        self.assertIsNone(result["activity"]["ledger_active_children"])

    def test_older_active_children_are_included_and_pre_registration_work_is_not(self):
        User.objects.filter(pk=self.child.pk).update(date_joined=self.now - timedelta(days=400))
        self.reading()
        self.entry(20, "reading")
        result = self.observe()
        self.assertEqual(result["cohort"]["eligible_children"], 1)
        self.assertIsNone(result["cohort"]["registered_within_days"])
        self.assertEqual(result["cohort"]["scope"], "active_family_children")
        self.assertEqual(result["cohort"]["eligible_child_days"], 30)
        self.assertEqual(result["activity"]["meaningful_active_child_days"], 1)
        User.objects.filter(pk=self.child.pk).update(date_joined=self.now)
        self.assertEqual(self.observe()["activity"]["meaningful_active_child_days"], 0)

    def test_unrewarded_sources_deduplicate_work_days_and_exclude_negative_or_voided_work(self):
        first = self.now - timedelta(days=1)
        second = self.now - timedelta(days=2)
        self.reading(day=first.date())
        self.reading(day=first.date(), minutes=0)
        movement_type = MovementType.objects.create(name="Synthetic movement", slug="synthetic-observation")
        MovementSession.objects.create(user=self.child, movement_type=movement_type, duration_minutes=1,
                                       intensity="low", occurred_on=first.date(), xp_awarded=0)
        skill = Skill.objects.create(name="Synthetic making", category=SkillCategory.objects.create(name="Synthetic craft"))
        Creation.objects.create(user=self.child, image="synthetic-not-written.png", occurred_on=second.date(),
                                primary_skill=skill, xp_awarded=0)
        habit = Habit.objects.create(user=self.child, created_by=self.parent, name="Synthetic habit")
        positive = HabitLog.objects.create(user=self.child, habit=habit, direction=1)
        negative = HabitLog.objects.create(user=self.child, habit=habit, direction=-1)
        HabitLog.objects.filter(pk=positive.pk).update(created_at=second)
        HabitLog.objects.filter(pk=negative.pk).update(created_at=self.now - timedelta(days=6))
        project = Project.objects.create(title="Synthetic work", assigned_to=self.child, created_by=self.parent)
        for days_ago, status, minutes in [(3, "completed", 1), (7, "voided", 30), (8, "completed", 0)]:
            at = self.now - timedelta(days=days_ago)
            TimeEntry.objects.create(user=self.child, project=project, clock_in=at - timedelta(minutes=minutes),
                                     clock_out=at, status=status)
        assignment = HomeworkAssignment.objects.create(title="Synthetic homework", subject="reading",
                                                         due_date=self.now.date(), assigned_to=self.child, created_by=self.parent)
        submission = HomeworkSubmission.objects.create(user=self.child, assignment=assignment, status="pending", timeliness="on_time")
        HomeworkSubmission.objects.filter(pk=submission.pk).update(created_at=self.now - timedelta(days=4))
        chore = Chore.objects.create(family=self.family.family, created_by=self.parent, title="Synthetic chore")
        completion = ChoreCompletion.objects.create(user=self.child, chore=chore, completed_date=(self.now - timedelta(days=10)).date(),
                                                    reward_amount_snapshot=0, coin_reward_snapshot=0, status="approved")
        ChoreCompletion.objects.filter(pk=completion.pk).update(created_at=self.now - timedelta(days=5))
        self.assertEqual(self.observe()["activity"]["meaningful_active_child_days"], 5)
        HomeworkSubmission.objects.filter(pk=submission.pk).update(status="rejected")
        ChoreCompletion.objects.filter(pk=completion.pk).update(status="rejected")
        Creation.objects.filter(user=self.child).update(status="rejected")
        HabitLog.objects.filter(pk=positive.pk).delete()
        self.assertEqual(self.observe()["activity"]["meaningful_active_child_days"], 2)

    def test_reading_corrections_and_deletion_do_not_rewrite_earned_coins_or_count_receipts(self):
        from apps.quests.models import ChallengeActivity
        from apps.reading.models import ReadingDailyReward

        first = self.reading(day=(self.now - timedelta(days=1)).date())
        second = self.reading(day=(self.now - timedelta(days=2)).date())
        receipt = ReadingDailyReward.objects.create(user=self.child, day=first.occurred_on, awarded_at=self.now,
                                                    source_session=first, coins_awarded=5)
        ChallengeActivity.objects.create(user=self.child, source_type="reading_logged", source_id=str(receipt.pk),
                                           trigger_type="reading_logged", occurred_on=first.occurred_on, occurred_at=self.now)
        self.entry(5, "reading")
        self.assertEqual(self.observe()["activity"]["meaningful_active_child_days"], 2)
        ReadingSession.objects.filter(pk=first.pk).update(occurred_on=second.occurred_on)
        self.assertEqual(self.observe()["activity"]["meaningful_active_child_days"], 1)
        first.delete()
        second.delete()
        result = self.observe()
        receipt.refresh_from_db()
        self.assertEqual(result["activity"]["meaningful_active_child_days"], 0)
        self.assertEqual(result["ledger"]["credits"], 5)
        self.assertEqual(receipt.coins_awarded, 5)
        self.assertIsNone(receipt.source_session_id)

    def test_ledger_receipts_private_writing_and_assignment_setup_are_not_activity(self):
        from apps.chronicle.models import ChronicleEntry
        from apps.quests.models import ChallengeActivity
        for amount, reason, source in [(10, "exchange", ""), (2, "refund", ""), (20, "adjustment", "manual_grant"),
                                       (15, "expedition", "expedition"), (25, "adjustment", "coin_pouch")]:
            self.entry(amount, reason, source)
        HomeworkAssignment.objects.create(title="Parent setup", subject="reading", due_date=self.now.date(),
                                           assigned_to=self.child, created_by=self.parent)
        HomeworkAssignment.objects.create(title="Child setup", subject="reading", due_date=self.now.date(),
                                           assigned_to=self.child, created_by=self.child)
        ChronicleEntry.objects.create(user=self.child, kind="journal", occurred_on=self.now.date(),
                                       chapter_year=2026, title="Synthetic private journal", summary="Secret prose", is_private=True)
        for trigger in ["journal_entry", "savings_goal_complete", "expedition_returned"]:
            ChallengeActivity.objects.create(user=self.child, source_type=trigger, source_id="synthetic",
                                               trigger_type=trigger, occurred_on=self.now.date(), occurred_at=self.now)
        with CaptureQueriesContext(connection) as queries:
            result = self.observe()
        self.assertEqual(result["activity"]["meaningful_active_child_days"], 0)
        for sql in [query["sql"].lower() for query in queries]:
            self.assertNotIn("chronicle_chronicleentry", sql)
            self.assertNotIn("quests_challengeactivity", sql)
            self.assertNotIn('"reflection"', sql)
            self.assertNotIn('"notes"', sql)
            self.assertNotIn('"description"', sql)
        self.assertNotIn("Secret prose", str(result))

    def test_meaningful_work_uses_household_midnight_and_dst_not_approval_or_week_start(self):
        self.family.family.timezone = "America/New_York"
        self.family.family.save(update_fields=["timezone"])
        User.objects.filter(pk=self.child.pk).update(date_joined=datetime(2026, 2, 20, tzinfo=dt_timezone.utc))
        self.now = datetime(2026, 3, 9, 20, tzinfo=dt_timezone.utc)
        habit = Habit.objects.create(user=self.child, created_by=self.parent, name="Local habit")
        for when in [datetime(2026, 3, 8, 4, 59, 59, tzinfo=dt_timezone.utc),
                     datetime(2026, 3, 8, 5, tzinfo=dt_timezone.utc),
                     datetime(2026, 3, 9, 3, 59, 59, tzinfo=dt_timezone.utc),
                     datetime(2026, 3, 9, 4, tzinfo=dt_timezone.utc)]:
            log = HabitLog.objects.create(user=self.child, habit=habit, direction=1)
            HabitLog.objects.filter(pk=log.pk).update(created_at=when)
        result = self.observe(since=date(2026, 3, 8), until=date(2026, 3, 8))
        self.assertEqual(result["activity"]["meaningful_active_child_days"], 1)

    def test_other_household_work_and_mismatched_related_owners_are_not_counted(self):
        other_reading = self.reading(child=self.other)
        ReadingSession.objects.filter(pk=other_reading.pk).update(user=self.child)
        other_habit = Habit.objects.create(user=self.other, created_by=self.other, name="Other habit")
        log = HabitLog.objects.create(user=self.child, habit=other_habit, direction=1)
        HabitLog.objects.filter(pk=log.pk).update(created_at=self.now)
        self.assertEqual(self.observe()["activity"]["meaningful_active_child_days"], 0)

    def test_earning_sources_reconcile_credits_and_pace_ignores_windfalls_and_existing_wealth(self):
        self.reading(day=(self.now - timedelta(days=1)).date())
        self.reading(day=(self.now - timedelta(days=2)).date())
        # Reliable credits can arrive on another day: an approval must not
        # erase earned income simply because the child did no work that day.
        self.entry(7, "hourly", when=self.now)
        self.entry(4, "reading")
        self.entry(3, source="daily_check_in")
        self.entry(6, "expedition", "expedition")
        self.entry(2, source="coin_pouch")
        for amount, reason, source in [(100, "badge_bonus", ""), (200, "adjustment", "birthday"),
                                       (300, "adjustment", "automatic_challenge"), (400, "adjustment", "manual_grant"),
                                       (500, "exchange", ""), (50, "refund", ""), (17, "adjustment", ""),
                                       (13, "expedition", ""), (19, "reading", "coin_pouch")]:
            self.entry(amount, reason, source)
        self.entry(10000, "adjustment", "manual_grant", when=self.now - timedelta(days=40))
        self.entry(-10, "redemption")
        reward = Reward.objects.create(family=self.family.family, name="Synthetic treat", cost_coins=34, stock=0)
        Reward.objects.create(family=self.family.family, name="Inactive treat", cost_coins=1, is_active=False)
        Reward.objects.create(family=self.other.family, name="Other treat", cost_coins=1)
        result = self.observe()
        self.assertEqual(sum(row["coins"] for row in result["earning_sources"]), result["ledger"]["credits"])
        sources = {row["key"]: row for row in result["earning_sources"]}
        self.assertEqual(sources["unattributed"]["coins"], 49)
        self.assertEqual(sources["manual_grant"]["kind"], "manual")
        self.assertEqual(sources["exchange"]["kind"], "transfer")
        self.assertEqual(sources["refund"]["kind"], "refund")
        self.assertEqual(sources["automatic_challenge"]["kind"], "occasional")
        self.assertEqual(result["earning_pace"]["recurring_coins"], 22)
        self.assertEqual(result["earning_pace"]["active_child_days"], 2)
        self.assertEqual(result["earning_pace"]["coins_per_active_day"], 11)
        self.assertFalse(result["earning_pace"]["attribution_complete"])
        self.assertTrue(result["earning_pace"]["provisional"])
        self.assertEqual(result["shop_rewards"], [{"reward_id": reward.pk, "name": reward.name, "cost_coins": 34,
                                                   "stock": 0, "catalog_available": True, "days_to_earn": 4}])
        self.assertEqual(result["policy"]["coins_per_dollar"], 10)
        self.assertEqual(result["ledger"]["opening_balance"], 10000)

    def test_valid_typed_adjustments_remain_distinct_and_no_longer_look_unattributed(self):
        recurring = ["daily_check_in", "perfect_day", "writing", "cosmetic_salvage", "consumable_salvage"]
        occasional = ["automatic_challenge", "legacy_quest", "savings", "birthday"]
        self.reading()
        for source in recurring + occasional + ["manual_grant"]:
            self.entry(3, source=source)
        result = self.observe()
        self.assertEqual(result["automatic_sources"]["unattributed_positive_adjustments"], 0)
        self.assertTrue(result["earning_pace"]["attribution_complete"])
        self.assertEqual(result["earning_pace"]["recurring_coins"], 3 * len(recurring))
        sources = {row["key"]: row for row in result["earning_sources"]}
        self.assertEqual(set(sources), set(["daily_activity", "cosmetic_salvage", "consumable_salvage"] + occasional + ["manual_grant"]))
        for source in occasional:
            self.assertEqual(sources[source]["kind"], "occasional")

    def test_private_writing_and_other_daily_bonuses_share_one_coarse_accounting_bucket(self):
        for source in ["writing", "daily_check_in", "perfect_day"]:
            self.entry(3, source=source)
        self.entry(7, "daily_challenge")
        result = self.observe()
        self.assertEqual(result["earning_sources"], [{"key": "daily_activity", "label": "Daily activity bonuses",
                                                    "coins": 16, "entries": 4, "kind": "recurring"}])
        self.assertEqual(result["activity"]["meaningful_active_child_days"], 0)
        self.assertIsNone(result["earning_pace"]["coins_per_active_day"])
        for private in ["writing", "daily_check_in", "perfect_day", "user_id", "day", "source_id"]:
            self.assertNotIn(private, str(result["earning_sources"]))

    def test_small_and_zero_earning_samples_never_invent_a_rate_or_free_reward(self):
        reward = Reward.objects.create(family=self.family.family, name="Free choice", cost_coins=0)
        self.entry(7, "reading")
        result = self.observe()
        self.assertIsNone(result["earning_pace"]["coins_per_active_day"])
        self.assertIsNone(result["shop_rewards"][0]["days_to_earn"])
        for days_ago in range(1, 8):
            self.reading(day=(self.now - timedelta(days=days_ago)).date())
        result = self.observe()
        self.assertEqual(result["earning_pace"]["coins_per_active_day"], 1)
        self.assertFalse(result["earning_pace"]["provisional"])
        self.assertEqual(result["shop_rewards"][0]["days_to_earn"], 0)
        self.assertEqual(result["shop_rewards"][0]["reward_id"], reward.pk)

    def test_unavailable_digital_offers_are_labeled_without_an_earning_promise(self):
        self.reading()
        self.entry(10, "reading")
        item = ItemDefinition.objects.create(slug="synthetic-unavailable-accessory", name="Unavailable", item_type="cosmetic_pet_accessory")
        Reward.objects.create(family=self.family.family, name="Unsupported offer", cost_coins=100,
                              fulfillment_kind="digital_item", item_definition=item)
        result = self.observe()
        self.assertEqual(result["shop_rewards"][0]["catalog_available"], False)
        self.assertIsNone(result["shop_rewards"][0]["days_to_earn"])

    def test_shop_catalog_preloads_legacy_availability_without_per_offer_queries(self):
        from apps.pets.models import PetSpecies

        species = PetSpecies.objects.create(name="Friendly Synthetic Fox", slug="synthetic-observation-fox", sprite_key="synthetic-fox")
        item = ItemDefinition.objects.create(slug="synthetic-legacy-egg", name="Synthetic legacy egg", item_type="egg",
                                              metadata={"species": "fRIENDLY sYNTHETIC fOX"})
        policy = {"schema_version": 1, "pets": [{"species_slug": species.slug, "sprite_key": species.sprite_key,
                  "potion_slugs": ["base"]}], "potion_slugs": ["base"]}
        Reward.objects.create(family=self.family.family, name="First legacy egg", cost_coins=100,
                              fulfillment_kind="digital_item", item_definition=item)
        with override_settings(RPG_ASSET_SUPPORT_POLICY=policy), CaptureQueriesContext(connection) as first_queries:
            first = self.observe()
        Reward.objects.create(family=self.family.family, name="Second legacy egg", cost_coins=200,
                              fulfillment_kind="digital_item", item_definition=item)
        with override_settings(RPG_ASSET_SUPPORT_POLICY=policy), CaptureQueriesContext(connection) as second_queries:
            second = self.observe()
        self.assertEqual(len(first_queries), len(second_queries))
        self.assertTrue(first["shop_rewards"][0]["catalog_available"])
        self.assertTrue(all(row["catalog_available"] for row in second["shop_rewards"]))
        for sql in [query["sql"].lower() for query in second_queries]:
            self.assertNotIn('"description"', sql)

    def test_a_shared_calendar_day_counts_separately_for_each_active_child(self):
        second = User.objects.create_user(username="second-synthetic-child", role="child", family=self.family.family)
        User.objects.filter(pk=second.pk).update(date_joined=self.now - timedelta(days=10))
        self.reading()
        self.reading(child=second)
        self.entry(100, "reading")
        Reward.objects.create(family=self.family.family, name="Two days each", cost_coins=100)
        result = self.observe()
        self.assertEqual(result["activity"]["meaningful_active_children"], 2)
        self.assertEqual(result["activity"]["meaningful_active_child_days"], 2)
        self.assertEqual(result["earning_pace"]["coins_per_active_day"], 50)
        self.assertEqual(result["shop_rewards"][0]["days_to_earn"], 2)

    def test_new_source_and_shop_capacity_failures_suppress_partial_conclusions(self):
        self.entry(10, "reading")
        self.reading()
        self.reading()
        Reward.objects.create(family=self.family.family, name="First offer", cost_coins=100)
        for constant, expected in [("MAX_ACTIVITY_ROWS", "activity_limit_exceeded"), ("MAX_SHOP_REWARDS", "shop_limit_exceeded")]:
            with self.subTest(constant=constant), patch(f"apps.rpg.progression.observations.{constant}", 0):
                result = self.observe()
            self.assertEqual(result["status"], expected)
            self.assertIsNone(result["ledger"]["credits"])
            self.assertIsNone(result["activity"]["meaningful_active_child_days"])
            self.assertEqual(result["earning_pace"]["status"], "capacity_exceeded")
            self.assertEqual(result["earning_sources"], [])
            self.assertEqual(result["shop_rewards"], [])

    def test_cohort_growth_after_initial_count_cannot_materialize_an_unbounded_sample(self):
        from django.db.models.query import QuerySet

        second = User.objects.create_user(username="joined-after-count", role="child", family=self.family.family)
        User.objects.filter(pk=second.pk).update(date_joined=self.now - timedelta(days=1))
        original_count = QuerySet.count
        def earlier_count(query):
            return 1 if query.model is User else original_count(query)
        with patch("apps.rpg.progression.observations.MAX_COHORT_CHILDREN", 1), patch.object(QuerySet, "count", earlier_count):
            result = self.observe()
        self.assertEqual(result["status"], "cohort_limit_exceeded")
        self.assertEqual(result["earning_pace"]["status"], "capacity_exceeded")

    def test_select_only_report_preserves_prices_balances_redemptions_and_exchange_rate(self):
        from apps.rewards.models import RewardRedemption

        reward = Reward.objects.create(family=self.family.family, name="Saved offer", cost_coins=100)
        redemption = RewardRedemption.objects.create(user=self.child, reward=reward, coin_cost_snapshot=70)
        self.entry(100, "reading")
        self.reading()
        before_ledger = list(CoinLedger.objects.values())
        before_redemptions = list(RewardRedemption.objects.values())
        before_rewards = list(Reward.objects.values())
        def only_reads(execute, sql, params, many, context):
            self.assertTrue(sql.lstrip().upper().startswith("SELECT"), sql)
            return execute(sql, params, many, context)
        with connection.execute_wrapper(only_reads), override_settings(COINS_PER_DOLLAR=10):
            result = self.observe()
        self.assertEqual(list(CoinLedger.objects.values()), before_ledger)
        self.assertEqual(list(RewardRedemption.objects.values()), before_redemptions)
        self.assertEqual(list(Reward.objects.values()), before_rewards)
        redemption.refresh_from_db()
        self.assertEqual(redemption.coin_cost_snapshot, 70)
        self.assertEqual(result["policy"]["coins_per_dollar"], 10)

    def test_daily_counts_deduplicate_transactions_and_keep_source_coverage_gaps(self):
        self.entry(60, "expedition", "expedition", when=self.now - timedelta(days=1, seconds=1))
        self.entry(50, source="coin_pouch", when=self.now - timedelta(days=1))
        self.entry(15, "expedition", when=self.now - timedelta(days=2))
        self.entry(-20, "redemption", when=self.now - timedelta(days=1))
        self.entry(20, "refund", when=self.now - timedelta(days=1))
        self.entry(40, "exchange", when=self.now - timedelta(days=1))
        result = self.observe()
        self.assertEqual(result["activity"]["ledger_active_child_days"], 2)
        self.assertEqual(result["automatic_sources"]["child_days_over_100"], 1)
        self.assertEqual(result["automatic_sources"]["coins"], 110)
        self.assertEqual(result["automatic_sources"]["unattributed_expedition_coins"], 15)
        self.assertFalse(result["automatic_sources"]["attribution_complete"])
        self.assertEqual(result["ledger"]["by_reason"]["refund"]["credits"], 20)
        self.assertEqual(result["ledger"]["by_reason"]["exchange"]["credits"], 40)
        self.assertEqual(result["ledger"]["closing_balance"], 165)

    def test_same_family_pointer_on_stale_actor_cannot_follow_a_household_move(self):
        from apps.rpg.progression.observations import economy_observations
        User.objects.filter(pk=self.parent.pk).update(family_id=self.other.family_id)
        with self.assertRaises(PermissionDenied):
            economy_observations(self.parent)
