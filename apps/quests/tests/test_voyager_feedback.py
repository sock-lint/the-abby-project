"""Voyager feedback reads frozen evidence without changing accepted promises."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.families.models import LiveTestFamily
from apps.quests.goals import _snapshot
from apps.quests.milestone_eligibility import gate_snapshot
from apps.quests.models import (
    ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal,
    ChallengeOccurrence, ChallengePin, Quest, QuestDefinition, QuestParticipant,
)
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class VoyagerFeedbackTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 20, 12, tzinfo=dt_timezone.utc)
        self.household = make_family(
            "Voyager feedback", parents=[{"username": "voyager-parent", "is_staff": True}],
            children=[{"username": "voyager-child"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]
        get_user_model().objects.filter(pk=self.child.pk).update(date_joined=self.now - timedelta(days=120))
        self.category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(category=self.category, name="Reading Comprehension")
        self.companion = QuestDefinition.objects.create(
            name="Reading Companion", description="Public starter", quest_type="collection",
            target_value=3, duration_days=14, is_system=True,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        self.voyager = QuestDefinition.objects.create(
            name="Reading Voyager", description="Public voyage", quest_type="collection",
            target_value=20, duration_days=84, is_system=True,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
            prerequisite_quest=self.companion, required_skill=self.skill, required_skill_level=1,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def report(self, suffix=""):
        with patch("django.utils.timezone.now", return_value=self.now):
            return self.client.get("/api/challenges/voyager-feedback/" + suffix)

    def test_staff_parent_report_is_available_without_materializing_goals(self):
        response = self.report()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schema_version"], 1)
        self.assertEqual(response.data["current_states"], {
            "locked": 1, "ready": 0, "active": 0, "completed": 0, "expired": 0, "unknown": 0,
        })
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(ChallengeEnrollment.objects.exists())

    def child_user(self, suffix, **changes):
        return get_user_model().objects.create_user(
            username=f"voyager-{suffix}", password="pw", family=self.household.family,
            date_joined=self.now - timedelta(days=120), role="child", **changes,
        )

    def occurrence(self, *, user=None, days=56, gated=True, status="active", start=None, **changes):
        start = start or self.now - timedelta(days=70)
        goal = ChallengeGoal.objects.create(
            user=user or self.child, family=(user or self.child).family, is_catalog=True,
            catalog_definition=self.voyager, name="Reading Voyager", description="Public promise",
            metric="count", target=20, unit="actions", trigger_filter=self.voyager.trigger_filter,
            timezone_name="America/Phoenix", starts_at=start, ends_at=start + timedelta(days=days),
            catalog_gate_snapshot=gate_snapshot(self.voyager) if gated else {},
            catalog_gate_activity_id=17 if gated else None,
        )
        data = {"goal": goal, "starts_at": goal.starts_at, "ends_at": goal.ends_at,
                "snapshot": _snapshot(goal), "status": status,
                "progress": 20 if status == "completed" else 2,
                "completed_at": min(start + timedelta(days=30), self.now - timedelta(hours=1)) if status == "completed" else None}
        data.update(changes)
        row = ChallengeOccurrence.objects.create(**data)
        ChallengeOccurrence.objects.filter(pk=row.pk).update(created_at=start)
        row.refresh_from_db()
        return row

    def prior(self, user=None, *, foreign=False):
        start = self.now - timedelta(days=75)
        quest = Quest.objects.create(definition=self.companion, start_date=start,
                                     end_date=start + timedelta(days=14), status="completed")
        Quest.objects.filter(pk=quest.pk).update(created_at=start, updated_at=start + timedelta(days=2))
        QuestParticipant.objects.create(quest=quest, user=user or self.child)
        if foreign:
            other = make_family("Foreign campaign", children=[{"username": "voyager-foreign"}])
            QuestParticipant.objects.create(quest=quest, user=other.children[0])
        return quest

    def level(self, user=None, *, unlocked=True, level=1):
        SkillProgress.objects.update_or_create(user=user or self.child, skill=self.skill,
                                             defaults={"unlocked": unlocked, "level": level, "xp_points": 100})

    def groups(self, report=None):
        return {row["policy"]: row for row in (report or self.report().data)["policy_groups"]}

    def saved_state(self):
        return {model._meta.label: list(model.objects.order_by("pk").values()) for model in (
            ChallengeGoal, ChallengeOccurrence, ChallengeEnrollment, ChallengeActivity,
            ChallengeContribution, ChallengePin, Quest, QuestParticipant,
            CharacterProfile, CoinLedger, SkillProgress, UserInventory,
        )}

    def assert_partition(self, report):
        self.assertEqual(sum(report["current_states"].values()), report["cohort"]["eligible_children"])
        for group in report["policy_groups"]:
            self.assertEqual(group["accepted_windows"], sum(group[key] for key in (
                "pending_windows", "mature_completed", "mature_expired", "mature_unknown", "unknown_windows")))
            self.assertEqual(group["mature_denominator"], group["mature_completed"] + group["mature_expired"])

    def test_ready_uses_current_exact_prerequisite_and_unlocked_skill_and_no_clock(self):
        self.prior()
        self.level(unlocked=False)
        self.assertEqual(self.report().data["current_states"]["locked"], 1)
        self.level(level=0)
        self.assertEqual(self.report().data["current_states"]["locked"], 1)
        self.level()
        report = self.report().data
        self.assertEqual(report["current_states"]["ready"], 1)
        self.assertEqual(report["catalog"]["acceptance_mode"], "next_qualifying_reading")
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_baseline_readiness_never_claims_waiting_for_reading(self):
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(
            prerequisite_quest=None, required_skill=None, required_skill_level=0, duration_days=45)
        report = self.report().data
        self.assertEqual(report["catalog"]["acceptance_mode"], "automatic_tracking")
        self.assertEqual(report["current_states"]["ready"], 1)

    def test_readiness_never_uses_sibling_or_parent_same_name_completion(self):
        sibling = self.child_user("sibling")
        self.prior(sibling)
        self.level()
        private = QuestDefinition.objects.create(
            name="Reading Companion", description="private", quest_type="collection", target_value=3,
            created_by=self.parent)
        quest = Quest.objects.create(definition=private, status="completed", end_date=self.now)
        QuestParticipant.objects.create(quest=quest, user=self.child)
        self.assertEqual(self.report().data["current_states"]["ready"], 0)

    def test_foreign_only_prerequisite_is_unknown_and_valid_own_family_completion_can_satisfy(self):
        self.prior(foreign=True)
        self.level()
        report = self.report().data
        self.assertEqual(report["current_states"]["unknown"], 1)
        self.assertEqual(report["current_states"]["ready"], 0)
        self.prior()
        self.assertEqual(self.report().data["current_states"]["ready"], 1)

    def test_saved_45_and_historical_56_are_separate_and_include_older_than_30_days(self):
        self.occurrence(days=45, gated=False, status="completed")
        second = self.child_user("expired")
        self.occurrence(user=second)
        third = self.child_user("pending")
        self.occurrence(user=third, start=self.now - timedelta(days=10))
        fourth = self.child_user("early-completed")
        self.occurrence(user=fourth, start=self.now - timedelta(days=10), status="completed")
        fifth = self.child_user("unknown-completed")
        self.occurrence(user=fifth, status="completed", completed_at=None)
        report = self.report().data
        self.assertEqual(report["current_states"], {"locked": 0, "ready": 0, "active": 1,
            "completed": 2, "expired": 1, "unknown": 1})
        groups = self.groups(report)
        self.assertEqual(groups["saved_45_day"]["mature_completed"], 1)
        selected = groups["milestone_56_day"]
        self.assertEqual({key: selected[key] for key in ("accepted_windows", "pending_windows",
            "mature_completed", "mature_expired", "mature_unknown", "mature_denominator", "completion_rate")},
            {"accepted_windows": 4, "pending_windows": 2, "mature_completed": 0,
             "mature_expired": 1, "mature_unknown": 1, "mature_denominator": 1, "completion_rate": 0})
        self.assert_partition(report)

    def test_saved_45_56_and_selected_84_keep_distinct_promises_after_catalog_edit(self):
        self.occurrence(days=45, gated=False, status="completed")
        self.occurrence(user=self.child_user("historical56"), days=56)
        self.occurrence(user=self.child_user("selected84"), days=84, start=self.now - timedelta(days=90),
                        status="completed")
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(duration_days=98, target_value=7)
        before = self.saved_state()
        report = self.report().data
        groups = self.groups(report)
        self.assertEqual(groups["saved_45_day"]["mature_completed"], 1)
        self.assertEqual(groups["milestone_56_day"]["mature_expired"], 1)
        self.assertEqual(groups["milestone_56_day"]["label"], "56 days · milestones")
        self.assertEqual(groups["milestone_84_day"]["mature_completed"], 1)
        self.assertEqual(groups["milestone_84_day"]["label"], "84 days · selected milestones")
        self.assertEqual(groups["other_or_unknown"]["accepted_windows"], 0)
        self.assertEqual(before, self.saved_state())
        self.assert_partition(report)

    def test_selected_84_matures_only_at_its_full_saved_deadline(self):
        row = self.occurrence(days=84, start=self.now - timedelta(days=84), status="completed")
        before = self.saved_state()
        self.now -= timedelta(microseconds=1)
        pending = self.groups()["milestone_84_day"]
        self.assertEqual(pending["pending_windows"], 1)
        self.assertEqual(pending["mature_denominator"], 0)
        self.assertIsNone(pending["completion_rate"])
        self.now += timedelta(microseconds=1)
        mature = self.groups()["milestone_84_day"]
        self.assertEqual(mature["mature_completed"], 1)
        self.assertEqual(mature["mature_denominator"], 1)
        self.assertEqual(mature["completion_rate"], 1)
        self.assertEqual(row.ends_at, self.now)
        self.assertEqual(before, self.saved_state())

    def test_selected_84_requires_strict_matching_native_gate_snapshots(self):
        row = self.occurrence(days=84)
        original = row.snapshot
        gate = row.goal.catalog_gate_snapshot
        self.assertEqual(self.groups()["milestone_84_day"]["accepted_windows"], 1)
        invalid = [[], {}, {**gate, "version": True}, {**gate, "required_skill_level": True},
                   {**gate, "required_skill_id": 9999}, {**gate, "prerequisite_quest_id": 9999},
                   {**gate, "required_badge_id": 4}, {**gate, "extra": 1}]
        for changed in invalid:
            with self.subTest(gate=changed):
                ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_gate_snapshot=changed)
                saved = {**changed, "opening_activity_id": 17} if isinstance(changed, dict) else changed
                ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot={**original, "catalog_gate": saved})
                groups = self.groups()
                self.assertEqual(groups["other_or_unknown"]["accepted_windows"], 1)
                self.assertEqual(groups["milestone_84_day"]["accepted_windows"], 0)
        ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_gate_snapshot=gate)
        for saved in [None, [], {**gate, "opening_activity_id": 18},
                      {**gate, "opening_activity_id": True},
                      {**gate, "opening_activity_id": 17, "version": True},
                      {**gate, "opening_activity_id": 17, "extra": 1}]:
            with self.subTest(occurrence_gate=saved):
                ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot={**original, "catalog_gate": saved})
                self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)
        ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot=original)
        for opening_id in [None, 0]:
            with self.subTest(opening_id=opening_id):
                ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_gate_activity_id=opening_id)
                self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)

    def test_maturity_uses_exclusive_full_deadline_and_early_completion_stays_pending(self):
        row = self.occurrence(start=self.now - timedelta(days=56), status="completed")
        self.assertEqual(self.groups()["milestone_56_day"]["mature_denominator"], 1)
        ChallengeOccurrence.objects.filter(pk=row.pk).update(ends_at=self.now + timedelta(microseconds=1))
        ChallengeGoal.objects.filter(pk=row.goal_id).update(ends_at=self.now + timedelta(microseconds=1))
        group = self.groups()["other_or_unknown"]
        self.assertEqual(group["pending_windows"], 1)
        self.assertIsNone(group["completion_rate"])

    def test_completion_recorded_after_deadline_can_be_a_known_mature_success(self):
        self.occurrence(status="completed", completed_at=self.now - timedelta(hours=1))
        self.assertEqual(self.groups()["milestone_56_day"]["mature_completed"], 1)

    def test_ended_inconsistent_completion_and_unsettled_target_are_unknown_not_failed(self):
        row = self.occurrence(status="completed", completed_at=self.now + timedelta(hours=1))
        self.assertEqual(self.groups()["milestone_56_day"]["mature_unknown"], 1)
        for changes in [dict(status="active", progress=20, completed_at=None),
                        dict(status="completed", progress=2, completed_at=self.now),
                        dict(status="expired", progress=2, completed_at=self.now)]:
            with self.subTest(changes=changes):
                ChallengeOccurrence.objects.filter(pk=row.pk).update(**changes)
                group = self.groups()["milestone_56_day"]
                self.assertEqual(group["mature_unknown"], 1)
                self.assertEqual(group["mature_expired"], 0)
                self.assertIsNone(group["completion_rate"])

    def test_malformed_snapshot_progress_and_future_window_are_unknown(self):
        row = self.occurrence()
        original = row.snapshot
        for snapshot in [None, [], {}, {**original, "target": "NaN"}, {**original, "target": True}]:
            # JSON null is rejected by the DB; a list and malformed objects are valid stored JSON.
            if snapshot is None:
                continue
            with self.subTest(snapshot=snapshot):
                ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot=snapshot)
                result = self.report().data
                self.assertEqual(result["current_states"]["unknown"], 1)
                self.assertEqual(self.groups(result)["other_or_unknown"]["mature_unknown"], 1)
        ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot=original, starts_at=self.now + timedelta(days=1))
        group = self.groups()["other_or_unknown"]
        self.assertEqual(group["unknown_windows"], 1)
        self.assertEqual(group["mature_denominator"], 0)

    def test_null_deadline_in_retry_chain_is_unknown_without_writes_or_crashing(self):
        root = self.occurrence(days=45, gated=False, status="expired")
        successor = ChallengeOccurrence.objects.create(
            goal=root.goal, retry_of=root, starts_at=self.now - timedelta(days=10),
            ends_at=self.now + timedelta(days=35), progress=2,
            snapshot={**root.snapshot, "_retry_after_activity_id": 1},
        )
        ChallengeOccurrence.objects.filter(pk=successor.pk).update(created_at=successor.starts_at)
        for position in ("root", "successor"):
            with self.subTest(position=position):
                ChallengeGoal.objects.filter(pk=root.goal_id).update(
                    ends_at=None if position == "root" else root.ends_at,
                )
                ChallengeOccurrence.objects.filter(pk=root.pk).update(
                    ends_at=None if position == "root" else root.ends_at,
                )
                ChallengeOccurrence.objects.filter(pk=successor.pk).update(
                    ends_at=None if position == "successor" else successor.ends_at,
                )
                before = self.saved_state()
                response = self.report()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["current_states"]["unknown"], 1)
                self.assertEqual(sum(group["accepted_windows"] for group in response.data["policy_groups"]), 2)
                self.assertEqual(sum(group["mature_denominator"] for group in response.data["policy_groups"]), 0)
                self.assertEqual(before, self.saved_state())

    def test_changed_current_definition_never_relabels_saved_policy(self):
        self.occurrence(days=45, gated=False, status="completed")
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(target_value=7, duration_days=63)
        group = self.groups()["saved_45_day"]
        self.assertEqual(group["accepted_windows"], 1)
        self.assertEqual(group["mature_completed"], 1)

    def test_native_56_requires_exact_reviewed_gate_and_snapshot_agreement(self):
        row = self.occurrence()
        original = row.snapshot
        gate = row.goal.catalog_gate_snapshot
        for key, value in [("required_skill_level", 2), ("prerequisite_quest_id", 9999),
                           ("required_skill_id", 9999), ("version", True), ("required_badge_id", 4)]:
            with self.subTest(key=key):
                changed = {**gate, key: value}
                ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_gate_snapshot=changed)
                ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot={
                    **original, "catalog_gate": {**changed, "opening_activity_id": 17}})
                self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)
        ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_gate_snapshot=gate)
        ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot={
            **original, "catalog_gate": {**gate, "opening_activity_id": 18}})
        self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)

    def test_boolean_values_in_occurrence_gate_do_not_impersonate_integer_markers(self):
        row = self.occurrence()
        for key in ["version", "required_skill_level", "opening_activity_id"]:
            with self.subTest(key=key):
                changed = {**row.snapshot["catalog_gate"], key: True}
                ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot={**row.snapshot, "catalog_gate": changed})
                self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)

    def test_future_or_missing_current_prerequisite_completion_is_unknown_not_ready(self):
        row = self.occurrence(status="completed")
        ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_definition=self.companion)
        self.level()
        for completed_at in [None, self.now + timedelta(seconds=1)]:
            with self.subTest(completed_at=completed_at):
                ChallengeOccurrence.objects.filter(pk=row.pk).update(completed_at=completed_at)
                self.assertEqual(self.report().data["current_states"]["unknown"], 1)
        ChallengeOccurrence.objects.all().delete()
        ChallengeGoal.objects.all().delete()
        legacy = self.prior()
        Quest.objects.filter(pk=legacy.pk).update(updated_at=self.now + timedelta(seconds=1))
        self.assertEqual(self.report().data["current_states"]["unknown"], 1)

    def test_membership_move_between_saved_reads_never_exposes_foreign_policy_outcomes(self):
        row = self.occurrence(days=45, gated=False, status="completed")
        other = make_family("Racing report family")
        original = QuerySet.__iter__
        for point in ["goal", "occurrence"]:
            moved = []
            get_user_model().objects.filter(pk=self.child.pk).update(family=self.household.family)

            def iteration(query):
                iterator = original(query)
                fields = query._fields or ()
                matching = (query.model is ChallengeGoal and fields == ("pk", "user_id", "catalog_definition_id")) if point == "goal" else (
                    query.model is ChallengeOccurrence and "snapshot" in fields)
                if matching and not moved:
                    moved.append(True)
                    get_user_model().objects.filter(pk=self.child.pk).update(family=other.family)
                return iterator

            with self.subTest(point=point), patch.object(QuerySet, "__iter__", iteration):
                report = self.report().data
            self.assertTrue(moved)
            self.assertEqual(report["current_states"]["unknown"], 1)
            self.assertEqual(self.groups(report)["saved_45_day"]["accepted_windows"], 0)
        self.assertTrue(ChallengeOccurrence.objects.filter(pk=row.pk).exists())

    def test_current_prerequisite_identity_aggregation_clears_history_ordering(self):
        self.prior()
        self.level()
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.report().data["current_states"]["ready"], 1)
        distinct_reads = [row["sql"] for row in queries if "SELECT DISTINCT" in row["sql"]]
        self.assertGreaterEqual(len(distinct_reads), 3)
        for sql in distinct_reads:
            self.assertNotIn("ORDER BY", sql, "Model history ordering defeats identity DISTINCT bounds")

    def test_unreviewed_durations_and_missing_frozen_policy_are_other(self):
        row = self.occurrence(days=49)
        for duration in [timedelta(days=49), timedelta(days=70), timedelta(days=98),
                         timedelta(days=84, microseconds=1)]:
            with self.subTest(duration=duration):
                end = row.starts_at + duration
                ChallengeOccurrence.objects.filter(pk=row.pk).update(ends_at=end)
                ChallengeGoal.objects.filter(pk=row.goal_id).update(ends_at=end)
                self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)
        ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot={"metric": "count", "target": "20"})
        self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)

    def test_ambiguous_selected_companion_keeps_known_timing_but_unknown_policy(self):
        self.occurrence()
        QuestDefinition.objects.create(name="Reading Companion", description="duplicate", quest_type="collection",
                                       target_value=3, is_system=True)
        self.assertEqual(self.groups()["other_or_unknown"]["accepted_windows"], 1)

    def test_duplicate_or_conflicting_accepted_history_and_missing_occurrence_are_unknown(self):
        row = self.occurrence()
        duplicate = ChallengeOccurrence.objects.create(
            goal=row.goal, starts_at=row.starts_at + timedelta(hours=1), ends_at=row.ends_at,
            snapshot=row.snapshot, progress=1)
        ChallengeOccurrence.objects.filter(pk=duplicate.pk).update(created_at=row.starts_at)
        report = self.report().data
        self.assertEqual(report["current_states"]["unknown"], 1)
        self.assertEqual(sum(g["mature_denominator"] for g in report["policy_groups"]), 0)
        ChallengeOccurrence.objects.all().delete()
        report = self.report().data
        self.assertEqual(report["current_states"]["unknown"], 1)
        self.assertEqual(sum(g["accepted_windows"] for g in report["policy_groups"]), 0)

    def test_orphaned_same_name_catalog_history_is_unknown_without_claimed_identity(self):
        row = self.occurrence()
        ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_definition=None)
        report = self.report().data
        self.assertEqual(report["current_states"]["unknown"], 1)
        self.assertEqual(sum(g["accepted_windows"] for g in report["policy_groups"]), 0)

    def test_saved_legacy_states_never_infer_policy_or_mature_success_from_today(self):
        start = self.now - timedelta(days=60)
        quest = Quest.objects.create(definition=self.voyager, status="completed", start_date=start,
                                     end_date=start + timedelta(days=45), current_progress=20)
        Quest.objects.filter(pk=quest.pk).update(created_at=start, updated_at=start + timedelta(days=30))
        QuestParticipant.objects.create(quest=quest, user=self.child)
        report = self.report().data
        self.assertEqual(report["current_states"]["completed"], 1)
        group = self.groups(report)["other_or_unknown"]
        self.assertEqual(group["mature_unknown"], 1)
        self.assertIsNone(group["completion_rate"])
        self.assertEqual(self.groups(report)["saved_45_day"]["accepted_windows"], 0)

    def test_foreign_private_inconsistent_family_and_inactive_records_do_not_enter(self):
        other = make_family("Other report", children=[{"username": "other-voyager"}])
        self.occurrence(user=other.children[0])
        self.occurrence(user=self.parent)
        row = self.occurrence()
        ChallengeGoal.objects.filter(pk=row.goal_id).update(family=other.family)
        report = self.report().data
        self.assertEqual(report["cohort"]["eligible_children"], 1)
        self.assertEqual(sum(g["accepted_windows"] for g in report["policy_groups"]), 0)

    def test_missing_or_duplicate_global_target_withholds_counts_never_uses_private_name(self):
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(is_system=False, created_by=self.parent)
        result = self.report().data
        self.assertEqual(result["status"], "catalog_unavailable")
        self.assertTrue(all(value is None for value in result["current_states"].values()))
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(is_system=True, created_by=None)
        QuestDefinition.objects.create(name="Reading Voyager", description="duplicate", quest_type="collection",
                                       target_value=20, is_system=True)
        self.assertEqual(self.report().data["status"], "catalog_ambiguous")

    def test_capacity_failure_withholds_counts_and_does_not_return_partial_totals(self):
        self.occurrence()
        for constant, limit, status in [("MAX_COHORT_CHILDREN", 0, "cohort_limit_exceeded"),
                                        ("MAX_ACCEPTED_RECORDS", 1, "record_limit_exceeded")]:
            with self.subTest(constant=constant), patch(f"apps.quests.voyager_feedback.{constant}", limit):
                report = self.report().data
                self.assertEqual(report["status"], status)
                self.assertTrue(report["cohort"]["truncated"])
                self.assertTrue(all(value is None for value in report["current_states"].values()))
                self.assertTrue(all(group["accepted_windows"] is None for group in report["policy_groups"]))

    def test_report_is_read_only_and_contains_no_private_identity_or_content(self):
        self.occurrence(status="completed")
        before = self.saved_state()
        with CaptureQueriesContext(connection) as queries:
            report = self.report().data
        self.assertEqual(before, self.saved_state())
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for query in queries))
        for private in [self.child.username, self.parent.username, "Public promise", "source_id", "user_id", "goal_id"]:
            self.assertNotIn(private, str(report))
        self.assert_partition(report)

    def test_current_cohort_uses_full180_family_days_and_excludes_future_old_staff_inactive(self):
        since = datetime(2026, 4, 24, 7, tzinfo=dt_timezone.utc)
        # The local since boundary is authoritative rather than elapsed180days.
        since = datetime.fromisoformat(self.report().data["period"]["starts_at"])
        get_user_model().objects.filter(pk=self.child.pk).update(date_joined=since)
        self.child_user("staff", is_staff=True)
        self.child_user("inactive", is_active=False)
        future = self.child_user("future")
        old = self.child_user("old")
        get_user_model().objects.filter(pk=future.pk).update(date_joined=self.now + timedelta(seconds=1))
        get_user_model().objects.filter(pk=old.pk).update(date_joined=since - timedelta(microseconds=1))
        report = self.report().data
        self.assertEqual(report["cohort"]["eligible_children"], 1)
        self.assertEqual(report["cohort"]["registered_within_days"], 180)

    def test_trusted_observer_family_is_excluded_without_name_based_exclusion(self):
        LiveTestFamily.objects.create(namespace="fixture-report", family=self.household.family,
                                      parent=self.parent, child=self.child)
        report = self.report().data
        self.assertTrue(report["cohort"]["observer_family_excluded"])
        self.assertEqual(report["status"], "insufficient_evidence")
        self.assertEqual(report["cohort"]["eligible_children"], 0)
        self.assert_partition(report)

    def test_permissions_targeting_and_transport_keys(self):
        for actor in [self.child, None]:
            self.client.force_authenticate(actor)
            self.assertIn(self.report().status_code, [401, 403])
        self.parent.is_staff = False
        self.parent.save(update_fields=["is_staff"])
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.report().status_code, 403)
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        self.assertEqual(self.report("?user_id=1").status_code, 400)
        self.assertEqual(self.report("?family_id=1").status_code, 400)
        self.assertEqual(self.report("?_abby_session=transport&_abby_retry=1").status_code, 200)
        self.assertEqual(self.client.post("/api/challenges/voyager-feedback/", {}, format="json").status_code, 405)

    def test_service_revalidates_stale_authorization(self):
        from apps.quests.voyager_feedback import voyager_feedback
        from rest_framework.exceptions import PermissionDenied
        for changes in [{"is_active": False}, {"is_staff": False}, {"role": "child"}]:
            with self.subTest(changes=changes):
                get_user_model().objects.filter(pk=self.parent.pk).update(**changes)
                with self.assertRaises(PermissionDenied):
                    voyager_feedback(self.parent)
                get_user_model().objects.filter(pk=self.parent.pk).update(is_active=True, is_staff=True, role="parent")

    def test_query_budget_stays_bounded_for100_children_with_native_gates(self):
        for index in range(99):
            self.child_user(f"bounded-{index}")
        with CaptureQueriesContext(connection) as queries:
            report = self.report().data
        self.assertEqual(report["cohort"]["eligible_children"], 100)
        self.assertEqual(report["current_states"]["locked"], 100)
        self.assertLessEqual(len(queries), 20, f"Expected bulk bounded reads, got {len(queries)} queries")
