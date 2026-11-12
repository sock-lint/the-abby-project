"""Saved Lab evidence binds both taxonomy labels and retained source identities."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.achievements.models import Skill, SkillCategory
from apps.achievements.services import SkillService
from apps.families.models import Family
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.tests import test_decision_catalog_freshness as decision_tests
from apps.mcp_server.tools import progression_experiments
from apps.rpg.models import ProgressionDecision, RPGContentOverride
from apps.rpg.progression import experiments


class IdentityFixture(decision_tests.DecisionFixture):
    def setUp(self):
        super().setUp()
        self.category = SkillCategory.objects.create(name="Language Arts")
        self.reading = Skill.objects.create(name="Renamed reading destination", category=self.category)
        self.identity = RPGContentOverride.objects.create(
            model_label="achievements.skill", object_id=self.reading.pk,
            source_lookup={"name": "Reading Comprehension", "category_id": self.category.pk},
            values={"_authoring": {"version": 1, "source": "mcp"}},
        )
        self.experiment = self.ok("create_progression_experiment", {
            "request_id": str(uuid4()), "name": "Retained Reading evidence",
            "hypothesis": "Reading follows its installed identity.",
            "config": {"horizon_days": 30, "trials": 1, "seed": 99,
                       "active_days_per_week": 7, "reading_minutes": 10,
                       "chores_per_day": 0, "habits_per_day": 0,
                       "journal_per_day": False, "expeditions_per_day": 0},
            "candidate_daily_coins": 100,
            "targets": [{"metric": "closing_coins_p50", "min": 0}],
        })
        self.comparison = self.ok("compare_progression_experiment", {
            "experiment_id": self.experiment["id"], "revision": 1, "request_id": str(uuid4()),
        })
        self.decision.update(experiment_id=self.experiment["id"], comparison_id=self.comparison["id"])

    def change_identity(self):
        RPGContentOverride.objects.filter(pk=self.identity.pk).update(
            source_lookup={"name": "Different original source", "category_id": self.category.pk},
        )

    def comparison_detail(self):
        return self.ok("get_progression_comparison", {
            "experiment_id": self.experiment["id"], "comparison_id": self.comparison["id"],
        })


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LabIdentityFreshnessTests(IdentityFixture, TestCase):
    def test_registered_category_rename_invalidates_saved_evidence_without_rewriting_it(self):
        self.ok("update_category", {"category_id": self.category.pk, "name": "Literacy"}, actor=self.other)
        current = self.comparison_detail()
        self.assertEqual(current["control"], self.comparison["control"])
        self.assertEqual(current["freshness"], "stale")
        self.assert_conflict_without_decision(self.wire("record_progression_decision", self.decision))

    def test_metadata_only_identity_change_invalidates_registered_and_native_evidence(self):
        self.change_identity()
        current = self.comparison_detail()
        self.assertEqual(current["control"], self.comparison["control"])
        self.assertEqual(current["freshness"], "stale")
        native = experiments.get_comparison(self.actor, self.experiment["id"], self.comparison["id"])
        self.assertEqual(native["freshness"], "stale")
        self.assert_conflict_without_decision(self.wire("record_progression_decision", self.decision))

    def test_metadata_only_update_enters_the_bounded_decision_source_token(self):
        token = experiments._catalog_source_token()
        self.change_identity()
        self.assertNotEqual(experiments._catalog_source_token(), token)

    def test_metadata_change_after_detached_snapshot_rejects_decision(self):
        original = progression_experiments._freshness_snapshot

        @contextmanager
        def changed_after_snapshot(*args, **kwargs):
            with original(*args, **kwargs):
                self.change_identity()
                yield

        with patch.object(progression_experiments, "_freshness_snapshot", changed_after_snapshot):
            self.assert_conflict_without_decision(self.wire("record_progression_decision", self.decision))

    def test_unrelated_or_unverified_authoring_metadata_does_not_enter_global_source_token(self):
        token = experiments._catalog_source_token()
        for label, authoring in (
            ("quests.questdefinition", {"version": 1, "source": "mcp"}),
            ("achievements.skill", {"version": 2, "source": "mcp"}),
            ("achievements.skillcategory", {"version": 1, "source": "other"}),
        ):
            with self.subTest(label=label, authoring=authoring):
                record = RPGContentOverride.objects.create(
                    model_label=label, object_id=999999, family=self.other.family,
                    source_lookup={"name": "Unrelated source"},
                    values={"_authoring": authoring, "private_notes": "Synthetic unrelated prose"},
                )
                self.assertEqual(experiments._catalog_source_token(), token)
                record.delete()
        self.ok("record_progression_decision", self.decision)

    def test_identity_token_query_omits_family_publication_and_private_values(self):
        with CaptureQueriesContext(connection) as queries:
            experiments._catalog_source_token()
        table = connection.ops.quote_name(RPGContentOverride._meta.db_table)
        reads = [query["sql"] for query in queries if f"FROM {table}" in query["sql"]]
        self.assertEqual(len(reads), 1)
        projection = reads[0].split(" FROM ", 1)[0]
        for field in ("family_id", "publication_id", "values", "created_at", "updated_at"):
            self.assertNotIn(connection.ops.quote_name(field), projection)

    def test_exact_decision_retry_preserves_immutable_decision_after_identity_change(self):
        saved = self.ok("record_progression_decision", self.decision)
        self.change_identity()
        replay = self.ok("record_progression_decision", self.decision)
        self.assertEqual(replay["decisions"], saved["decisions"])
        self.assertEqual(replay["comparisons"][0]["freshness"], "stale")
        self.assertEqual(ProgressionDecision.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL metadata and household locks required")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LabIdentityFreshnessConcurrencyTests(IdentityFixture, TransactionTestCase):
    submit = decision_tests.DecisionCatalogConcurrencyTests.submit
    pause = decision_tests.DecisionCatalogConcurrencyTests.pause

    def assert_raw_identity_write_blocked(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '300ms'")
                self.change_identity()

    def test_cross_connection_identity_edit_between_snapshot_and_commit_rejects_decision(self):
        original = progression_experiments._freshness_snapshot
        entered, release = Event(), Event()

        @contextmanager
        def paused_snapshot(*args, **kwargs):
            with original(*args, **kwargs):
                self.pause(entered, release)
                yield

        with patch.object(progression_experiments, "_freshness_snapshot", paused_snapshot), ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor)
            try:
                self.assertTrue(entered.wait(timeout=30))
                self.change_identity()
            finally:
                release.set()
            with self.assertRaises(MCPValidationError) as failure:
                future.result(timeout=60)
        self.assertEqual(failure.exception.code, "progression_experiment_conflict")
        self.assertEqual(ProgressionDecision.objects.count(), 0)

    def test_snapshot_fence_blocks_identity_changes_but_allows_household_progress(self):
        original = experiments.load_catalog
        entered, release = Event(), Event()

        def paused_catalog():
            catalog = original()
            self.pause(entered, release)
            return catalog

        with patch.object(experiments, "load_catalog", paused_catalog), ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor)
            try:
                self.assertTrue(entered.wait(timeout=30))
                with transaction.atomic():
                    Family.objects.select_for_update(no_key=True, nowait=True).get(pk=self.actor.family_id)
                    # A real award in the same family can advance while the
                    # global snapshot is detached, without waiting on its author.
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '1s'")
                    progress = SkillService.award_xp(self.actor, self.skill, 10)
                    self.assertEqual(progress.xp_points, 10)
                self.assert_raw_identity_write_blocked()
            finally:
                release.set()
            saved = future.result(timeout=60)
        self.assertEqual(saved["decisions"][0]["outcome"], "ready_for_design")

    def test_final_metadata_fence_stays_held_through_decision_append(self):
        original = ProgressionDecision.objects.create
        entered, release = Event(), Event()

        def paused_create(*args, **kwargs):
            self.pause(entered, release)
            return original(*args, **kwargs)

        with patch.object(ProgressionDecision.objects, "create", side_effect=paused_create), ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor)
            try:
                self.assertTrue(entered.wait(timeout=30))
                self.assert_raw_identity_write_blocked()
            finally:
                release.set()
            saved = future.result(timeout=60)
        self.assertEqual(saved["decisions"][0]["outcome"], "ready_for_design")
