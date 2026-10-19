"""Observed accounting is family scoped and cannot validate an undeployed policy."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.families.models import LiveTestFamily
from apps.rewards.models import CoinLedger
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

    def test_empty_new_user_cohort_is_insufficient_not_a_passing_experiment(self):
        User.objects.filter(pk=self.child.pk).update(date_joined=self.now - timedelta(days=100))
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
        self.assertEqual(result["activity"], {"ledger_active_children": 1, "ledger_active_child_days": 1})
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

    def test_staff_inactive_old_and_provisioned_test_children_are_excluded(self):
        User.objects.filter(pk=self.child.pk).update(is_staff=True)
        self.entry(50, source="coin_pouch")
        self.assertEqual(self.observe()["cohort"]["eligible_children"], 0)
        User.objects.filter(pk=self.child.pk).update(is_staff=False, is_active=False)
        self.assertEqual(self.observe()["cohort"]["eligible_children"], 0)
        User.objects.filter(pk=self.child.pk).update(is_active=True)
        LiveTestFamily.objects.create(
            namespace="abby-live-checks-v1", family=self.family.family, parent=self.parent, child=self.child,
        )
        result = self.observe()
        self.assertTrue(result["cohort"]["observer_family_excluded"])
        self.assertEqual(result["cohort"]["eligible_children"], 0)

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
