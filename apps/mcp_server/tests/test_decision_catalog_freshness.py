"""A decision may use detached evidence only while its source remains current."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from typing import get_type_hints
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory
from apps.families.models import Family
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import progression_experiments
from apps.rpg.models import ProgressionDecision
from apps.rpg.progression import experiments
from config.tests.factories import make_family


class DecisionFixture:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.actor = make_family("Decision author", parents=[{
            "username": "fresh-decision-author", "is_staff": True,
        }]).parents[0]
        self.other = make_family("Catalog editor", parents=[{
            "username": "fresh-catalog-editor", "is_staff": True,
        }]).parents[0]
        category = SkillCategory.objects.create(name="Decision source")
        self.skill = Skill.objects.create(name="Original destination", category=category)
        self.experiment = self.ok("create_progression_experiment", {
            "request_id": str(uuid4()), "name": "Current design evidence",
            "hypothesis": "Synthetic passing control.",
            "config": {"horizon_days": 30, "trials": 1, "seed": 99},
            "candidate_daily_coins": 100,
            "targets": [{"metric": "closing_coins_p50", "min": 0}],
        })
        self.comparison = self.ok("compare_progression_experiment", {
            "experiment_id": self.experiment["id"], "revision": 1, "request_id": str(uuid4()),
        })
        self.assertEqual(self.comparison["evaluation"]["status"], "pass")
        self.decision = {
            "experiment_id": self.experiment["id"], "revision": 1,
            "comparison_id": self.comparison["id"], "request_id": str(uuid4()),
            "outcome": "ready_for_design", "rationale": "Synthetic passing report.",
            "next_action": "Review design.", "review_on": "2099-01-01",
        }

    def wire(self, name, params, *, actor=None):
        with override_user(actor or self.actor, scopes=frozenset({"mcp:author", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        if isinstance(result, tuple):
            return SimpleNamespace(isError=False, structuredContent=result[1])
        return result

    def ok(self, name, params, **kwargs):
        result = self.wire(name, params, **kwargs)
        self.assertFalse(result.isError, result.structuredContent)
        return result.structuredContent

    def rename(self):
        return self.ok("update_skill", {"skill_id": self.skill.pk, "name": "Changed destination"}, actor=self.other)

    def assert_conflict_without_decision(self, result):
        self.assertTrue(result.isError, result.structuredContent)
        self.assertEqual(result.structuredContent["error"]["code"], "progression_experiment_conflict")
        self.assertEqual(ProgressionDecision.objects.count(), 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DecisionCatalogFreshnessTests(DecisionFixture, TestCase):
    def test_supported_cross_family_edit_after_snapshot_rejects_decision(self):
        original = progression_experiments._freshness_snapshot

        @contextmanager
        def changed_after_snapshot(*args, **kwargs):
            with original(*args, **kwargs):
                self.rename()
                yield

        with patch.object(progression_experiments, "_freshness_snapshot", changed_after_snapshot):
            self.assert_conflict_without_decision(self.wire("record_progression_decision", self.decision))
        current = self.ok("get_progression_comparison", {
            "experiment_id": self.experiment["id"], "comparison_id": self.comparison["id"],
        })
        self.assertTrue(current["stale"])
        self.assertEqual(current["control"], self.comparison["control"])

    def test_native_decision_does_not_trust_an_earlier_request_binding(self):
        data = {key: value for key, value in self.decision.items() if key not in {"experiment_id", "request_id"}}
        with experiments.request_catalog_binding():
            self.rename()
            with self.assertRaises(experiments.ExperimentConflict):
                experiments.record_decision(self.actor, self.experiment["id"], data)
        self.assertEqual(ProgressionDecision.objects.count(), 0)

    def test_edit_before_snapshot_rejects_decision(self):
        self.rename()
        self.assert_conflict_without_decision(self.wire("record_progression_decision", self.decision))

    def test_unchanged_catalog_accepts_current_decision(self):
        saved = self.ok("record_progression_decision", self.decision)
        self.assertEqual(saved["decisions"][0]["outcome"], "ready_for_design")
        self.assertEqual(ProgressionDecision.objects.count(), 1)

    def test_replay_after_catalog_change_keeps_saved_decision_and_receipt(self):
        saved = self.ok("record_progression_decision", self.decision)
        original = ProgressionDecision.objects.values().get()
        self.rename()
        replay = self.ok("record_progression_decision", self.decision)
        self.assertEqual(replay["decisions"], saved["decisions"])
        self.assertEqual(ProgressionDecision.objects.values().get(), original)
        self.assertTrue(replay["comparisons"][0]["stale"])

    def test_catalog_becoming_unavailable_after_snapshot_never_appends(self):
        original = progression_experiments._freshness_snapshot

        @contextmanager
        def unavailable_after_snapshot(*args, **kwargs):
            with original(*args, **kwargs), patch.dict(experiments._CATALOG_SOURCE_LIMITS, {"achievements.Skill": 0}):
                yield

        with patch.object(progression_experiments, "_freshness_snapshot", unavailable_after_snapshot):
            result = self.wire("record_progression_decision", self.decision)
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["error"]["code"], "progression_catalog_unavailable")
        self.assertEqual(ProgressionDecision.objects.count(), 0)

    def test_policy_change_after_snapshot_rejects_decision(self):
        original = progression_experiments._freshness_snapshot

        @contextmanager
        def changed_after_snapshot(*args, **kwargs):
            with original(*args, **kwargs), override_settings(PET_INCUBATION_DURATION_SECONDS=123):
                yield

        with patch.object(progression_experiments, "_freshness_snapshot", changed_after_snapshot):
            self.assert_conflict_without_decision(self.wire("record_progression_decision", self.decision))

    def test_private_goal_edits_do_not_enter_global_freshness_token(self):
        from apps.quests.models import QuestDefinition, QuestSkillTag

        original = experiments._catalog_source_token()
        private = QuestDefinition.objects.create(
            name="Private family promise", description="Private prose", quest_type="collection",
            target_value=1, created_by=self.other, is_system=False,
        )
        QuestSkillTag.objects.create(quest_definition=private, skill=self.skill, xp_weight=1)
        self.assertEqual(experiments._catalog_source_token(), original)
        self.ok("record_progression_decision", self.decision)

    def test_final_save_does_not_reload_catalog_or_inspect_rules(self):
        from apps.rpg.content import publication

        locked = []
        real_lock = publication._catalog_lock
        real_catalog = experiments.load_catalog
        real_rules = experiments.rules_fingerprint

        def catalog_lock():
            real_lock()
            locked.append(True)

        def detached(function):
            def check(*args, **kwargs):
                self.assertFalse(locked, "Expensive catalog/rules work ran after household/catalog locking.")
                return function(*args, **kwargs)
            return check

        with (patch.object(publication, "_catalog_lock", catalog_lock),
              patch.object(experiments, "load_catalog", side_effect=detached(real_catalog)) as catalogs,
              patch.object(experiments, "rules_fingerprint", side_effect=detached(real_rules))):
            self.ok("record_progression_decision", self.decision)
        self.assertEqual(catalogs.call_count, 1)
        self.assertEqual(locked, [True])


@skipUnless(connection.vendor == "postgresql", "PostgreSQL catalog and household locks required")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DecisionCatalogConcurrencyTests(DecisionFixture, TransactionTestCase):
    def submit(self, executor):
        def run():
            close_old_connections()
            try:
                handler = progression_experiments.record_progression_decision
                with override_user(User.objects.get(pk=self.actor.pk), scopes=frozenset({"mcp:author"})):
                    return handler(get_type_hints(handler)["params"](**self.decision))
            finally:
                connections.close_all()
        return executor.submit(run)

    def pause(self, entered, release):
        entered.set()
        self.assertTrue(release.wait(timeout=30), "The test did not release its paused decision.")

    def assert_raw_catalog_write_blocked(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '300ms'")
                Skill.objects.filter(pk=self.skill.pk).update(description="Blocked concurrent edit")

    def test_separate_family_supported_edit_wins_snapshot_gap_and_blocks_decision(self):
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
                self.rename()
            finally:
                release.set()
            with self.assertRaises(MCPValidationError) as failure:
                future.result(timeout=60)
        self.assertEqual(failure.exception.code, "progression_experiment_conflict")
        self.assertEqual(ProgressionDecision.objects.count(), 0)

    def test_snapshot_fence_blocks_transient_catalog_writes_without_holding_family(self):
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
                self.assert_raw_catalog_write_blocked()
            finally:
                release.set()
            saved = future.result(timeout=60)
        self.assertEqual(saved["decisions"][0]["outcome"], "ready_for_design")

    def test_final_catalog_fence_remains_held_through_decision_append(self):
        original = ProgressionDecision.objects.create
        entered, release = Event(), Event()

        def paused_create(*args, **kwargs):
            self.pause(entered, release)
            return original(*args, **kwargs)

        with patch.object(ProgressionDecision.objects, "create", side_effect=paused_create), ThreadPoolExecutor(max_workers=1) as executor:
            future = self.submit(executor)
            try:
                self.assertTrue(entered.wait(timeout=30))
                self.assert_raw_catalog_write_blocked()
            finally:
                release.set()
            saved = future.result(timeout=60)
        self.assertEqual(saved["decisions"][0]["outcome"], "ready_for_design")
        self.rename()
        self.assertEqual(ProgressionDecision.objects.count(), 1)
