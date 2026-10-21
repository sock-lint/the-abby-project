"""Milestones share canonical history and explicit native attempt controls."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.quests.goals import _snapshot, ingest_activity, list_goals, occurrence_payload
from apps.quests.controls import control_context
from apps.quests.milestone_eligibility import gated_definitions, milestone_eligibility, prerequisite_completion, prerequisite_unavailable
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


READING = {"allowed_triggers": ["reading_logged"]}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MilestoneGoalControlTests(TestCase):
    def setUp(self):
        self.start = timezone.now()
        household = make_family("Combined milestones", parents=[{"username": "combined-parent"}],
                                children=[{"username": "combined-child"}])
        self.parent, self.child = household.parents[0], household.children[0]
        self.skill = Skill.objects.create(name="Combined reading", category=SkillCategory.objects.create(name="Combined"))
        self.progress = SkillProgress.objects.create(user=self.child, skill=self.skill, level=1, xp_points=100)
        self.prior = QuestDefinition.objects.create(name="Combined starter", quest_type="collection", target_value=3,
                                                  duration_days=2, is_system=True, trigger_filter=READING)
        self.voyager = QuestDefinition.objects.create(
            name="Combined voyager", quest_type="collection", target_value=20, duration_days=7, is_system=True,
            trigger_filter=READING, prerequisite_quest=self.prior, required_skill=self.skill, required_skill_level=1,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def at(self, days):
        return patch("django.utils.timezone.now", return_value=self.start + timedelta(days=days))

    def alias(self, definition):
        return QuestDefinition.objects.create(
            name=definition.name, quest_type="collection", target_value=definition.target_value,
            duration_days=definition.duration_days, is_system=True, trigger_filter=READING,
            prerequisite_quest=definition.prerequisite_quest, required_skill=definition.required_skill,
            required_skill_level=definition.required_skill_level, superseded_by=definition,
        )

    def completed_legacy(self, definition=None):
        row = Quest.objects.create(definition=definition or self.prior, status="completed", end_date=self.start)
        QuestParticipant.objects.create(quest=row, user=self.child)
        return row

    def accepted_goal(self, definition, *, completed=False):
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=definition, is_catalog=True,
            name=definition.name, description=definition.description, metric="count", target=definition.target_value,
            unit="actions", trigger_filter=READING, starts_at=self.start,
            ends_at=self.start + timedelta(days=definition.duration_days),
        )
        return ChallengeOccurrence.objects.create(
            goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at, snapshot=_snapshot(goal),
            status="completed" if completed else "active", completed_at=self.start if completed else None,
        )

    def accept_voyager(self):
        self.completed_legacy()
        with self.at(1):
            ingest_activity(self.child, "reading_logged", "opening", "reading_logged",
                            occurred_at=timezone.now(), fresh_milestone=True)
        return ChallengeOccurrence.objects.get(goal__catalog_definition=self.voyager)

    def retry(self, occurrence, *, day=10):
        with self.at(day):
            return self.client.post(f"/api/challenges/goal:{occurrence.pk}/retry/", {}, format="json")

    def test_completed_automatic_alias_unlocks_canonical_prerequisite_without_repaying(self):
        self.accepted_goal(self.alias(self.prior), completed=True)
        self.assertTrue(prerequisite_completion(self.child, self.prior.pk)[0])
        with self.at(1):
            ingest_activity(self.child, "reading_logged", "after-alias", "reading_logged",
                            occurred_at=timezone.now(), fresh_milestone=True)
        self.assertEqual(ChallengeOccurrence.objects.get(goal__catalog_definition=self.voyager).progress, 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_completed_legacy_alias_satisfies_canonical_milestone(self):
        self.completed_legacy(self.alias(self.prior))
        self.assertTrue(milestone_eligibility(self.child, self.voyager)["unlocked"])
        self.assertFalse(prerequisite_unavailable(self.child, self.prior.pk))
        self.assertFalse(CoinLedger.objects.exists())

    def test_accepted_alias_blocks_new_enrollment_and_is_omitted_from_coming_next(self):
        self.completed_legacy()
        self.accepted_goal(self.alias(self.voyager))
        self.assertIn("accepted", {row["kind"] for row in milestone_eligibility(self.child, self.voyager)["requirements"]})
        self.assertNotIn(self.voyager.pk, [row["id"] for row in list_goals(self.child)["locked_catalog"]])

    def test_gated_catalog_excludes_retired_cooperative_and_ambiguous_definitions(self):
        self.alias(self.voyager)
        QuestDefinition.objects.create(
            name="Family milestone", quest_type="collection", target_value=3, is_system=True, is_cooperative=True,
            trigger_filter=READING, required_skill=self.skill, required_skill_level=1,
        )
        self.assertEqual(set(gated_definitions().values_list("pk", flat=True)), {self.voyager.pk})
        QuestDefinition.objects.create(
            name=self.voyager.name, quest_type="collection", target_value=3, is_system=True,
            trigger_filter=READING, required_skill=self.skill, required_skill_level=1,
        )
        self.assertFalse(gated_definitions().exists())

    def test_expired_alias_prerequisite_remains_available_for_explicit_retry(self):
        self.accepted_goal(self.alias(self.prior))
        with self.at(10):
            self.assertFalse(prerequisite_unavailable(self.child, self.prior.pk))
            self.assertIn(self.voyager.pk, [row["id"] for row in list_goals(self.child)["locked_catalog"]])

    def test_expired_canonical_prerequisite_keeps_its_retryable_successor_visible(self):
        self.accepted_goal(self.prior)
        with self.at(10):
            self.assertFalse(prerequisite_unavailable(self.child, self.prior.pk))
            self.assertIn(self.voyager.pk, [row["id"] for row in list_goals(self.child)["locked_catalog"]])

    def test_new_gated_retry_checks_current_requirements_without_accepted_window_blocker(self):
        original = self.accept_voyager()
        self.assertEqual(self.retry(original).status_code, 201)
        fresh = ChallengeOccurrence.objects.get(retry_of=original)
        self.assertEqual(fresh.snapshot["catalog_gate"], original.snapshot["catalog_gate"])
        self.assertEqual(fresh.progress, 0)
        self.assertFalse(CoinLedger.objects.exists())

    def test_locked_requirements_refuse_a_new_gated_retry_but_preserve_old_promise(self):
        original = self.accept_voyager()
        self.progress.level = 0
        self.progress.save(update_fields=["level"])
        refused = self.retry(original)
        self.assertEqual(refused.status_code, 409)
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=original).exists())
        with self.at(2):
            ingest_activity(self.child, "reading_logged", "accepted-promise", "reading_logged",
                            occurred_at=timezone.now(), fresh_milestone=True)
        original.refresh_from_db()
        self.assertEqual(original.progress, 2)

    def test_exact_predecessor_replay_returns_saved_successor_after_requirements_change(self):
        original = self.accept_voyager()
        first = self.retry(original)
        self.assertEqual(first.status_code, 201)
        self.progress.level = 0
        self.progress.save(update_fields=["level"])
        replay = self.retry(original, day=11)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(ChallengeOccurrence.objects.filter(retry_of=original).count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_gate_requirements_are_batched_once_for_repeated_results_history_and_receipts(self):
        self.completed_legacy()
        self.accepted_goal(self.voyager)
        with self.at(10), CaptureQueriesContext(connection) as single:
            control_context(self.child)
        for index in range(7):
            definition = QuestDefinition.objects.create(
                name=f"Batched voyager {index}", quest_type="collection", target_value=20, duration_days=7,
                is_system=True, trigger_filter=READING, prerequisite_quest=self.prior,
                required_skill=self.skill, required_skill_level=1,
            )
            self.accepted_goal(definition)
        rows = list(ChallengeOccurrence.objects.select_related("goal__catalog_definition"))
        with self.at(10), CaptureQueriesContext(connection) as multiple:
            controls = control_context(self.child)
        self.assertLessEqual(len(multiple), len(single) + 1)
        with self.at(10), CaptureQueriesContext(connection) as projected:
            # The same accepted row can appear in results, history and reward
            # receipts. Those projections must reuse one eligibility snapshot.
            for _ in range(3):
                payloads = [occurrence_payload(row, item_catalog={}, controls=controls) for row in rows]
                self.assertTrue(all(row["retry"]["allowed"] for row in payloads))
        self.assertEqual(len(projected), 0)

    def test_batched_requirements_match_live_checks_and_refresh_for_the_next_context(self):
        self.accepted_goal(self.alias(self.prior), completed=True)
        badge = Badge.objects.create(name="Combined milestone badge", description="A saved milestone",
                                     criteria_type="first_project", award_coins=False)
        self.voyager.required_badge = badge
        self.voyager.save(update_fields=["required_badge"])
        self.accepted_goal(self.voyager)
        with self.at(10):
            before = control_context(self.child)
            self.assertEqual(before["milestone_retry"][self.voyager.pk],
                             milestone_eligibility(self.child, self.voyager, new_enrollment=False)["unlocked"])
            self.assertFalse(before["milestone_retry"][self.voyager.pk])
            UserBadge.objects.create(user=self.child, badge=badge)
            current = control_context(self.child)
            self.assertTrue(current["milestone_retry"][self.voyager.pk])
            self.assertFalse(before["milestone_retry"][self.voyager.pk])
            self.progress.unlocked = False
            self.progress.save(update_fields=["unlocked"])
            self.assertFalse(control_context(self.child)["milestone_retry"][self.voyager.pk])
