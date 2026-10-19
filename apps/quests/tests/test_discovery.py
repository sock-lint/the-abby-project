"""Detail presentation evidence is separate from contributions and rewards."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db.models.query import QuerySet
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import SkillProgress, UserBadge
from apps.families.models import LiveTestFamily
from apps.quests.goals import ingest_activity, list_goals, occurrence_payload
from apps.quests.models import (
    ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal,
    ChallengeOccurrence, ChallengePin, QuestDefinition,
)
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, UserInventory
from config.tests.factories import make_family


class DiscoveryFixture(TestCase):
    def setUp(self):
        household = make_family(
            "Discovery household", parents=[{"username": "discover-parent", "is_staff": True}],
            children=[{"username": "discover-child"}, {"username": "discover-sibling"}],
        )
        self.family = household.family
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        other = make_family("Other discovery", parents=[{"username": "other-discover-parent"}],
                            children=[{"username": "other-discover-child"}])
        self.other = other.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        self.now = timezone.now()

    def occurrence(self, *, user=None, catalog=True, repeat_days=0, status="active", **changes):
        user = user or self.child
        goal = ChallengeGoal.objects.create(
            user=user, family=user.family, is_catalog=catalog,
            name="Shared harmless title", description="Public authored description.",
            metric="count", target=3, unit="actions", trigger_filter={"allowed_triggers": ["chore_complete"]},
            timezone_name="America/Phoenix", starts_at=self.now - timedelta(days=1),
            ends_at=self.now + timedelta(days=6), repeat_days=repeat_days,
        )
        data = {"goal": goal, "starts_at": goal.starts_at, "ends_at": goal.ends_at,
                "status": status, "snapshot": {"name": goal.name, "description": goal.description,
                    "metric": "count", "target": "3", "unit": "actions", "filter": goal.trigger_filter,
                    "coins": 0, "xp": 0, "items": [], "skill_tags": []}}
        data.update(changes)
        return ChallengeOccurrence.objects.create(**data)

    def open(self, row, data=None, suffix=""):
        return self.client.post(f"/api/challenges/goal:{row.pk}/opened/{suffix}", {} if data is None else data, format="json")

    def reward_state(self):
        return {model._meta.label: list(model.objects.order_by("pk").values()) for model in (
            CharacterProfile, CoinLedger, SkillProgress, UserInventory, UserBadge,
            ChallengeActivity, ChallengeContribution, ChallengeGoal, ChallengePin,
        )}


class ChallengeOpeningTests(DiscoveryFixture):
    def test_self_opening_is_idempotent_and_changes_no_reward_or_occurrence_state(self):
        row = self.occurrence()
        before = self.reward_state()
        saved = ChallengeOccurrence.objects.values().get(pk=row.pk)
        with patch("django.utils.timezone.now", return_value=self.now):
            first = self.open(row)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data, {"id": f"goal:{row.pk}", "first_details_opened_at": self.now.isoformat()})
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
            self.assertEqual(self.open(row).data, first.data)
        current = ChallengeOccurrence.objects.values().get(pk=row.pk)
        self.assertEqual(current.pop("first_details_opened_at"), self.now)
        saved.pop("first_details_opened_at")
        self.assertEqual(current, saved)
        self.assertEqual(self.reward_state(), before)
        self.assertFalse(ChallengeEnrollment.objects.exists(), "opening must not materialize enrollment")

    def test_completed_expired_and_repeat_catalog_details_can_record_an_opening(self):
        for status, repeat in [("completed", 0), ("expired", 0), ("active", 7)]:
            with self.subTest(status=status, repeat=repeat):
                row = self.occurrence(status=status, repeat_days=repeat)
                self.assertEqual(self.open(row).status_code, 200)
        self.assertFalse(CoinLedger.objects.exists())

    def test_owner_and_family_origin_and_upcoming_are_enforced(self):
        rows = [self.occurrence(user=self.sibling), self.occurrence(user=self.other),
                self.occurrence(catalog=False), self.occurrence(starts_at=self.now + timedelta(days=1))]
        own = self.occurrence()
        ChallengeGoal.objects.filter(pk=own.goal_id).update(family=self.other.family)
        rows.append(own)
        for row in rows:
            with self.subTest(row=row.pk):
                self.assertEqual(self.open(row).status_code, 404)
        self.assertFalse(ChallengeOccurrence.objects.filter(first_details_opened_at__isnull=False).exists())

    def test_parent_and_anonymous_cannot_record_child_openings(self):
        row = self.occurrence()
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.open(row).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.open(row).status_code, [401, 403])

    def test_opening_rejects_selectors_and_nonempty_or_nondict_bodies(self):
        row = self.occurrence()
        for body in [{"user_id": self.child.pk}, {"first_details_opened_at": self.now.isoformat()}, [], None]:
            with self.subTest(body=body):
                # Explicit null differs from the helper's omitted-body default.
                response = self.client.post(f"/api/challenges/goal:{row.pk}/opened/", body, format="json")
                if body is None:
                    # APIClient sends an empty body for None; empty and {} are equivalent.
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assertEqual(response.status_code, 400)
        self.assertEqual(self.open(row, suffix="?user_id=1").status_code, 400)
        for identity in ["legacy:1", "goal:0", "goal:-1", "goal:999999999999999999999999999", "bad"]:
            self.assertEqual(self.client.post(f"/api/challenges/{identity}/opened/", {}, format="json").status_code, 404)

    def test_service_revalidates_stale_role_activity_and_family(self):
        from apps.quests.discovery import record_details_opened
        from rest_framework.exceptions import PermissionDenied
        row = self.occurrence()
        for changes in [{"is_active": False}, {"role": "parent"}, {"family_id": self.other.family_id}]:
            with self.subTest(changes=changes):
                type(self.child).objects.filter(pk=self.child.pk).update(**changes)
                with self.assertRaises(PermissionDenied):
                    record_details_opened(self.child, f"goal:{row.pk}")
                type(self.child).objects.filter(pk=self.child.pk).update(is_active=True, role="child", family=self.family)

    def test_payload_uses_saved_origin_and_repeat_policy_without_guessing_from_name(self):
        repeated = self.occurrence(repeat_days=7)
        self.assertTrue(occurrence_payload(repeated)["catalog_repeatable"])
        self.assertIsNone(occurrence_payload(repeated)["first_details_opened_at"])
        parent = self.occurrence(catalog=False, repeat_days=7)
        self.assertFalse(occurrence_payload(parent)["catalog_repeatable"])
        self.assertIsNone(occurrence_payload(parent)["first_details_opened_at"])

    def test_only_new_enrollment_is_marked_and_backdated_work_does_not_backdate_marker(self):
        old = ChallengeEnrollment.objects.create(user=self.sibling, starts_at=self.now - timedelta(days=20))
        self.assertIsNone(old.discovery_tracking_started_at)
        with patch("django.utils.timezone.now", return_value=self.now):
            ingest_activity(self.child, "chore_complete", "fresh", "chore_complete", occurred_at=self.now - timedelta(days=2))
            list_goals(self.sibling)
        tracked = ChallengeEnrollment.objects.get(user=self.child)
        self.assertEqual(tracked.discovery_tracking_started_at, self.now)
        self.assertEqual(tracked.starts_at, self.now - timedelta(days=2))
        old.refresh_from_db()
        self.assertIsNone(old.discovery_tracking_started_at)

    def test_first_list_creates_tracking_once_without_source_rewards(self):
        with patch("django.utils.timezone.now", return_value=self.now):
            list_goals(self.child)
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
            list_goals(self.child)
        self.assertEqual(ChallengeEnrollment.objects.get(user=self.child).discovery_tracking_started_at, self.now)
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(ChallengeActivity.objects.exists())

    def test_listing_and_parent_preview_do_not_record_openings(self):
        self.occurrence()
        for actor, suffix in [(self.child, ""), (self.parent, f"?user_id={self.child.pk}")]:
            self.client.force_authenticate(actor)
            response = self.client.get(f"/api/challenges/{suffix}")
            self.assertEqual(response.status_code, 200)
        self.assertFalse(ChallengeOccurrence.objects.filter(first_details_opened_at__isnull=False).exists())


class ChallengeDiscoveryObservationTests(DiscoveryFixture):
    def enrollment(self, user=None, *, tracked=True):
        user = user or self.child
        return ChallengeEnrollment.objects.create(
            user=user, starts_at=self.now - timedelta(days=20),
            discovery_tracking_started_at=self.now - timedelta(days=10) if tracked else None,
        )

    def observations(self):
        self.client.force_authenticate(self.parent)
        return self.client.get("/api/challenges/discovery/")

    def test_full_materialized_cohort_and_overlap_counts_are_distinct_and_read_only(self):
        self.enrollment()
        self.enrollment(self.sibling, tracked=False)
        first = self.occurrence(first_details_opened_at=self.now - timedelta(hours=2),
                                status="completed", completed_at=self.now - timedelta(hours=1))
        self.occurrence(status="completed", completed_at=self.now - timedelta(hours=1))
        self.occurrence(first_details_opened_at=self.now, status="completed", completed_at=self.now - timedelta(hours=1))
        self.occurrence()
        # All old/parent/repeat/other-family rows stay outside this denominator.
        self.occurrence(user=self.sibling, first_details_opened_at=self.now)
        self.occurrence(user=self.other, first_details_opened_at=self.now)
        self.occurrence(catalog=False)
        self.occurrence(repeat_days=7)
        for _ in range(25):
            self.occurrence(status="expired", ends_at=self.now - timedelta(days=1))
        # Starts may predate materialization; the saved materialization is authoritative.
        ChallengeOccurrence.objects.filter(pk=first.pk).update(starts_at=self.now - timedelta(days=60))
        before = self.reward_state()
        with CaptureQueriesContext(connection) as queries:
            response = self.observations()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "observations_available")
        self.assertEqual(response.data["catalog_occurrences"], {
            "cohort_materialized": 29, "opened": 2, "completed": 3,
            "opened_and_completed": 2, "completed_without_recorded_opening": 1,
            "opening_recorded_after_completion": 1,
        })
        self.assertEqual(response.data["cohort"]["tracked_children"], 1)
        self.assertEqual(response.data["cohort"]["untracked_children"], 1)
        self.assertEqual(before, self.reward_state())
        self.assertFalse(any(q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for q in queries))
        self.assertNotIn("Public authored description", str(response.data))
        self.assertNotIn(self.child.username, str(response.data))

    def test_missing_or_old_enrollment_and_no_catalog_rows_are_insufficient(self):
        self.occurrence()
        result = self.observations().data
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["catalog_occurrences"]["cohort_materialized"], 0)
        self.assertEqual(result["cohort"]["untracked_children"], 2)

    def test_permissions_and_query_targeting(self):
        for actor in [self.child, self.other]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get("/api/challenges/discovery/").status_code, 403)
        self.parent.is_staff = False
        self.parent.save(update_fields=["is_staff"])
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get("/api/challenges/discovery/").status_code, 403)
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get("/api/challenges/discovery/?user_id=1").status_code, 400)
        self.assertEqual(self.client.get("/api/challenges/discovery/?_abby_session=transport&_abby_retry=1").status_code, 200)

    def test_capacity_failure_reports_unknown_counts_not_partial_zero(self):
        self.enrollment()
        self.occurrence()
        with patch("apps.quests.discovery.MAX_OCCURRENCES", 0):
            result = self.observations().data
        self.assertEqual(result["status"], "occurrence_limit_exceeded")
        self.assertTrue(result["cohort"]["truncated"])
        self.assertTrue(all(value is None for value in result["catalog_occurrences"].values()))
        with patch("apps.quests.discovery.MAX_COHORT_CHILDREN", 1):
            result = self.observations().data
        self.assertEqual(result["status"], "cohort_limit_exceeded")
        self.assertIsNone(result["cohort"]["eligible_children"])
        self.assertIsNone(result["cohort"]["tracked_children"])

    def test_reactivation_between_cohort_reads_cannot_expand_the_measured_cohort(self):
        self.enrollment()
        self.occurrence()
        self.enrollment(self.sibling)
        self.occurrence(user=self.sibling)
        inactive = get_user_model().objects.create_user(
            username="reactivated-discover-child", family=self.family, role="child", is_active=False,
        )
        self.enrollment(inactive)
        self.occurrence(user=inactive)
        original_count, original_fetch = QuerySet.count, QuerySet._fetch_all
        reactivated = False

        def after_cohort_read(queryset):
            nonlocal reactivated
            child_query = queryset.model is get_user_model() and any(
                getattr(condition, "rhs", None) == "child"
                and getattr(getattr(getattr(condition, "lhs", None), "target", None), "name", None) == "role"
                for condition in queryset.query.where.children
            )
            if child_query and not reactivated:
                reactivated = True
                get_user_model().objects.filter(pk=inactive.pk).update(is_active=True)

        def count_then_reactivate(queryset):
            value = original_count(queryset)
            after_cohort_read(queryset)
            return value

        def fetch_then_reactivate(queryset):
            original_fetch(queryset)
            after_cohort_read(queryset)

        # Intervene after either a count or materialized ID read. The measured
        # identities must stay bounded even when current membership changes.
        with patch("apps.quests.discovery.MAX_COHORT_CHILDREN", 2), \
                patch.object(QuerySet, "count", count_then_reactivate), \
                patch.object(QuerySet, "_fetch_all", fetch_then_reactivate):
            result = self.observations().data

        self.assertTrue(reactivated, "the membership change must happen during the observation")
        self.assertEqual(result["status"], "observations_available")
        self.assertEqual(result["cohort"]["eligible_children"], 2)
        self.assertEqual(result["cohort"]["tracked_children"], 2)
        self.assertEqual(result["cohort"]["untracked_children"], 0)
        self.assertEqual(result["catalog_occurrences"]["cohort_materialized"], 2)

    def test_provisioned_test_family_and_nonrecent_inactive_or_staff_children_are_excluded(self):
        self.enrollment()
        self.occurrence()
        LiveTestFamily.objects.create(namespace="discovery-tests", family=self.family,
                                      parent=self.parent, child=self.child)
        result = self.observations().data
        self.assertTrue(result["cohort"]["observer_family_excluded"])
        self.assertEqual(result["cohort"]["eligible_children"], 0)
        LiveTestFamily.objects.all().delete()
        type(self.child).objects.filter(pk=self.child.pk).update(date_joined=self.now - timedelta(days=100))
        type(self.child).objects.filter(pk=self.sibling.pk).update(is_staff=True)
        result = self.observations().data
        self.assertEqual(result["cohort"]["eligible_children"], 0)

    def test_family_local_midnight_dst_and_future_timestamps_are_bounded(self):
        self.family.timezone = "America/New_York"
        self.family.save(update_fields=["timezone"])
        now = datetime(2026, 11, 2, 12, tzinfo=dt_timezone.utc)
        type(self.child).objects.filter(pk=self.child.pk).update(date_joined=now - timedelta(days=3))
        self.enrollment()
        row = self.occurrence(first_details_opened_at=datetime(2026, 11, 3, 5, tzinfo=dt_timezone.utc))
        # 30 inclusive local days start Oct4 04:00Z, end Nov3 05:00Z after DST.
        start = datetime(2026, 10, 4, 4, tzinfo=dt_timezone.utc)
        ChallengeOccurrence.objects.filter(pk=row.pk).update(created_at=start)
        ChallengeEnrollment.objects.filter(user=self.child).update(discovery_tracking_started_at=start)
        outside = self.occurrence()
        ChallengeOccurrence.objects.filter(pk=outside.pk).update(created_at=start - timedelta(microseconds=1))
        with patch("django.utils.timezone.now", return_value=now):
            result = self.observations().data
        self.assertEqual(result["period"]["starts_at"], "2026-10-04T00:00:00-04:00")
        self.assertEqual(result["period"]["ends_before"], "2026-11-03T00:00:00-05:00")
        self.assertEqual(result["catalog_occurrences"]["cohort_materialized"], 1)
        self.assertEqual(result["catalog_occurrences"]["opened"], 0)

    def test_service_revalidates_observers_current_authority_and_family(self):
        from apps.quests.discovery import discovery_observations
        from rest_framework.exceptions import PermissionDenied
        for changes in [{"is_active": False}, {"is_staff": False}, {"role": "child"},
                        {"family_id": self.other.family_id}]:
            with self.subTest(changes=changes):
                type(self.parent).objects.filter(pk=self.parent.pk).update(**changes)
                with self.assertRaises(PermissionDenied):
                    discovery_observations(self.parent)
                type(self.parent).objects.filter(pk=self.parent.pk).update(
                    is_active=True, is_staff=True, role="parent", family=self.family,
                )


class DiscoveryMigrationTests(SimpleTestCase):
    def test_real_migration_preserves_old_enrollment_and_occurrence_as_unknown(self):
        # The ordinary test runner uses syncdb; a fresh process exercises the
        # actual before/after migration against only disposable SQLite data.
        script = textwrap.dedent('''
            import django
            django.setup()
            from django.conf import settings
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            from django.utils import timezone
            assert not getattr(settings, "MIGRATION_MODULES", {})
            executor = MigrationExecutor(connection)
            other_targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "quests"]
            before = other_targets + [("quests", "0008_quest_reward_items_snapshot")]
            after = other_targets + [("quests", "0009_challenge_discovery")]
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            Family = old.get_model("families", "Family")
            User = old.get_model(settings.AUTH_USER_MODEL)
            family = Family.objects.create(name="Migration discovery", slug="migration-discovery")
            user = User.objects.create(username="migration-discovery", family=family, role="child")
            at = timezone.now()
            enrollment = old.get_model("quests", "ChallengeEnrollment").objects.create(user=user, starts_at=at)
            goal = old.get_model("quests", "ChallengeGoal").objects.create(
                user=user, family=family, is_catalog=True, name="Old saved catalog", metric="count",
                target=3, unit="actions", timezone_name="UTC", starts_at=at, ends_at=at,
            )
            occurrence = old.get_model("quests", "ChallengeOccurrence").objects.create(
                goal=goal, starts_at=at, ends_at=at, status="completed", progress=3,
                snapshot={"name":"Saved promise"}, completed_at=at, awarded_at=at,
                reward_receipt={"coins":7,"xp":11},
            )
            saved = old.get_model("quests", "ChallengeOccurrence").objects.values().get(pk=occurrence.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            new = executor.loader.project_state(after).apps
            assert new.get_model("quests", "ChallengeEnrollment").objects.get(pk=enrollment.pk).discovery_tracking_started_at is None
            current = new.get_model("quests", "ChallengeOccurrence").objects.values().get(pk=occurrence.pk)
            assert current.pop("first_details_opened_at") is None
            assert current == saved, (current, saved)
            print("Migration preserves historical unknown openings and all saved occurrence fields")
        ''')
        env = {**os.environ, "DATABASE_URL": "sqlite:///:memory:",
               "DJANGO_SETTINGS_MODULE": "config.settings_test", "SECRET_KEY": "synthetic-migration-test"}
        result = subprocess.run([sys.executable, "-c", script], env=env, cwd=Path(__file__).resolve().parents[3],
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Migration preserves historical unknown openings", result.stdout)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL user-row serialization")
class DiscoveryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = make_family("Opening race", parents=[{"username": "opening-race-parent"}],
                             children=[{"username": "opening-race-child"}])
        self.child = family.children[0]
        QuestDefinition.objects.create(
            name="Opening race catalog", description="One saved chore", is_system=True,
            quest_type="collection", target_value=1, duration_days=7, coin_reward=5, xp_reward=0,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        list_goals(self.child)
        self.row = ChallengeOccurrence.objects.get(goal__user=self.child)

    def race(self, actions):
        barrier = Barrier(len(actions))

        def worker(action):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                child = get_user_model().objects.get(pk=self.child.pk)
                barrier.wait(timeout=5)
                return action(child)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(worker, action) for action in actions]
            return [future.result(timeout=15) for future in futures]

    def test_parallel_openings_keep_one_first_timestamp_and_award_nothing(self):
        from apps.quests.discovery import record_details_opened
        opening = lambda child: record_details_opened(child, f"goal:{self.row.pk}")
        first, second = self.race([opening, opening])
        self.assertEqual(first, second)
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(ChallengeActivity.objects.exists())
        self.row.refresh_from_db()
        self.assertEqual((self.row.progress, self.row.status), (0, "active"))

    def test_opening_and_final_activity_preserve_one_contribution_and_payout(self):
        from apps.quests.discovery import record_details_opened
        self.race([
            lambda child: record_details_opened(child, f"goal:{self.row.pk}"),
            lambda child: ingest_activity(child, "chore_complete", "opening-race-final", "chore_complete"),
        ])
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.first_details_opened_at)
        self.assertEqual((self.row.progress, self.row.status), (1, "completed"))
        self.assertEqual(ChallengeContribution.objects.filter(occurrence=self.row).count(), 1)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [5])
        self.assertEqual(ChallengeActivity.objects.filter(user=self.child).count(), 1)
