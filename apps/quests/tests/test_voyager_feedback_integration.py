"""Canonical saved identities and explicit retry attempts remain observable."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from apps.quests.controls import retry_challenge
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition
from . import test_voyager_feedback as fixtures


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class VoyagerFeedbackIntegrationTests(TestCase):
    setUp = fixtures.VoyagerFeedbackTests.setUp
    report = fixtures.VoyagerFeedbackTests.report
    occurrence = fixtures.VoyagerFeedbackTests.occurrence
    prior = fixtures.VoyagerFeedbackTests.prior
    level = fixtures.VoyagerFeedbackTests.level
    groups = fixtures.VoyagerFeedbackTests.groups
    assert_partition = fixtures.VoyagerFeedbackTests.assert_partition

    def alias(self, definition):
        fields = {field.attname: getattr(definition, field.attname) for field in definition._meta.concrete_fields
                  if field.name not in {"id", "created_at", "updated_at", "superseded_by"}}
        return QuestDefinition.objects.create(**fields, superseded_by=definition)

    def chain(self):
        self.prior()
        self.level()
        root = self.occurrence(start=self.now - timedelta(days=100))
        with patch("django.utils.timezone.now", return_value=self.now - timedelta(days=30)):
            successor, created = retry_challenge(self.parent, root.pk)
        self.assertTrue(created)
        return root, successor

    def test_retained_voyager_alias_selects_canonical_offer_and_accepted_history(self):
        alias = self.alias(self.voyager)
        row = self.occurrence(days=45, gated=False, status="completed")
        ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_definition=alias)
        result = self.report().data
        self.assertEqual(result["status"], "observations_available")
        self.assertEqual(result["current_states"]["completed"], 1)
        self.assertEqual(self.groups(result)["saved_45_day"]["mature_completed"], 1)
        self.assert_partition(result)

    def test_retained_companion_completion_satisfies_the_exact_canonical_gate(self):
        alias = self.alias(self.companion)
        prior = self.prior()
        Quest.objects.filter(pk=prior.pk).update(definition=alias)
        self.level()
        self.assertEqual(self.report().data["current_states"]["ready"], 1)

    def test_frozen_selected_policy_accepts_its_exact_retained_companion_identity(self):
        alias = self.alias(self.companion)
        row = self.occurrence(status="completed")
        gate = {**row.goal.catalog_gate_snapshot, "prerequisite_quest_id": alias.pk}
        ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_gate_snapshot=gate)
        snapshot = {**row.snapshot, "catalog_gate": {**gate, "opening_activity_id": row.goal.catalog_gate_activity_id}}
        ChallengeOccurrence.objects.filter(pk=row.pk).update(snapshot=snapshot)
        self.assertEqual(self.groups()["milestone_56_day"]["mature_completed"], 1)

    def test_native_retry_chain_keeps_attempt_policy_and_latest_child_state(self):
        _, successor = self.chain()
        for status in ("active", "completed"):
            with self.subTest(status=status):
                ChallengeOccurrence.objects.filter(pk=successor.pk).update(
                    status=status, progress=20 if status == "completed" else 0,
                    completed_at=self.now - timedelta(days=1) if status == "completed" else None,
                )
                result = self.report().data
                self.assertEqual(result["current_states"][status], 1)
                self.assertEqual(result["current_states"]["unknown"], 0)
                group = self.groups(result)["milestone_56_day"]
                self.assertEqual((group["accepted_windows"], group["mature_expired"], group["pending_windows"]), (2, 1, 1))
                self.assert_partition(result)

    def test_late_ancestor_completion_closes_current_attempt_without_another_failure(self):
        root, successor = self.chain()
        ChallengeOccurrence.objects.filter(pk=root.pk).update(
            status="completed", progress=20, completed_at=self.now - timedelta(days=10),
        )
        ChallengeOccurrence.objects.filter(pk=successor.pk).update(
            status="closed", closed_reason="reward_already_awarded",
        )
        result = self.report().data
        self.assertEqual(result["current_states"]["completed"], 1)
        group = self.groups(result)["milestone_56_day"]
        self.assertEqual((group["accepted_windows"], group["mature_completed"], group["unknown_windows"]), (2, 1, 1))
        self.assert_partition(result)

    def test_broken_links_changed_promises_and_overlapping_retries_remain_unknown(self):
        root, successor = self.chain()
        original = deepcopy(successor.snapshot)
        invalid = [
            {"retry_of_id": None},
            {"snapshot": {**original, "target": "21"}},
            {"snapshot": {**original, "_retry_after_activity_id": True}},
            {"starts_at": root.ends_at - timedelta(minutes=1)},
            {"ends_at": successor.ends_at + timedelta(days=1)},
        ]
        for values in invalid:
            with self.subTest(values=values):
                ChallengeOccurrence.objects.filter(pk=successor.pk).update(**values)
                result = self.report().data
                self.assertEqual(result["current_states"]["unknown"], 1)
                self.assertEqual(sum(group["mature_denominator"] for group in result["policy_groups"]), 0)
                self.assert_partition(result)
                ChallengeOccurrence.objects.filter(pk=successor.pk).update(
                    retry_of_id=root.pk, snapshot=original, starts_at=successor.starts_at, ends_at=successor.ends_at,
                )

    def test_retired_or_ambiguous_current_offer_is_not_revived_by_saved_alias_history(self):
        alias = self.alias(self.voyager)
        row = self.occurrence(status="completed")
        ChallengeGoal.objects.filter(pk=row.goal_id).update(catalog_definition=alias)
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(is_system=False)
        retired = self.report().data
        self.assertEqual(retired["status"], "catalog_unavailable")
        self.assertTrue(all(value is None for value in retired["current_states"].values()))
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(is_system=True)
        fields = {field.attname: getattr(self.voyager, field.attname) for field in self.voyager._meta.concrete_fields
                  if field.name not in {"id", "created_at", "updated_at", "superseded_by"}}
        QuestDefinition.objects.create(**fields)
        ambiguous = self.report().data
        self.assertEqual(ambiguous["status"], "catalog_ambiguous")
        self.assertTrue(all(value is None for value in ambiguous["current_states"].values()))

    def test_unrelated_alias_and_canonical_goals_remain_conflicting_evidence(self):
        alias = self.alias(self.voyager)
        first = self.occurrence(status="completed")
        ChallengeGoal.objects.filter(pk=first.goal_id).update(catalog_definition=alias)
        self.occurrence(status="completed")
        result = self.report().data
        self.assertEqual(result["current_states"]["unknown"], 1)
        self.assertEqual(sum(group["mature_denominator"] for group in result["policy_groups"]), 0)
        self.assert_partition(result)

    def test_dst_crossing_original_policy_survives_a_native_retry_in_a_stable_offset(self):
        self.now = datetime(2027, 6, 20, 12, tzinfo=timezone.utc)
        self.household.family.timezone = "America/New_York"
        self.household.family.save(update_fields=["timezone"])
        get_user_model().objects.filter(pk=self.child.pk).update(
            date_joined=datetime(2027, 2, 1, 12, tzinfo=timezone.utc),
        )
        prior = self.prior()
        Quest.objects.filter(pk=prior.pk).update(
            start_date=datetime(2027, 1, 20, 12, tzinfo=timezone.utc),
            end_date=datetime(2027, 2, 3, 12, tzinfo=timezone.utc),
            created_at=datetime(2027, 1, 20, 12, tzinfo=timezone.utc),
            updated_at=datetime(2027, 2, 1, 12, tzinfo=timezone.utc),
        )
        self.level()
        root = self.occurrence(start=datetime(2027, 2, 10, 12, tzinfo=timezone.utc))
        ChallengeGoal.objects.filter(pk=root.goal_id).update(timezone_name="America/New_York")
        with patch("django.utils.timezone.now", return_value=datetime(2027, 4, 8, 12, tzinfo=timezone.utc)):
            successor, created = retry_challenge(self.parent, root.pk)
        self.assertTrue(created)
        successor.refresh_from_db()
        self.assertEqual(root.ends_at - root.starts_at, timedelta(days=56))
        self.assertNotEqual(successor.ends_at - successor.starts_at, timedelta(days=56))
        ChallengeOccurrence.objects.filter(pk=successor.pk).update(
            status="completed", progress=20, completed_at=successor.ends_at - timedelta(days=1),
        )
        result = self.report().data
        group = self.groups(result)["milestone_56_day"]
        self.assertEqual((group["accepted_windows"], group["mature_expired"], group["mature_completed"]), (2, 1, 1))
        self.assertEqual(result["current_states"]["completed"], 1)
        self.assert_partition(result)
