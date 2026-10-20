"""Native milestone offers retain prospective source boundaries and promises."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import (
    ChallengeActivity, ChallengeGoal, ChallengeOccurrence, Quest,
    QuestDefinition, QuestParticipant,
)
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MilestoneGateTests(TestCase):
    def setUp(self):
        family = make_family("Milestone family", parents=[{"username": "gate-parent"}],
                             children=[{"username": "gate-child"}, {"username": "gate-sibling"}])
        self.child, self.sibling = family.children
        self.parent = family.parents[0]
        category = SkillCategory.objects.create(name="Gate reading")
        self.skill = Skill.objects.create(name="Reading Comprehension", category=category)
        self.other = Skill.objects.create(name="Other skill", category=category)
        self.prior = QuestDefinition.objects.create(
            name="Reading Companion", description="Starter", quest_type="collection",
            target_value=3, duration_days=14, is_system=True,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        self.voyager = QuestDefinition.objects.create(
            name="Reading Voyager", description="Twenty daily adventures in 56 days",
            quest_type="collection", target_value=20, duration_days=56, is_system=True,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        # Attribute assignment also runs on the unmodified base: its missing
        # persistence/eligibility causes behavioral failures, not import errors.
        self.set_gate()

    def set_gate(self):
        self.voyager.prerequisite_quest = self.prior
        self.voyager.required_skill = self.skill
        self.voyager.required_skill_level = 1
        self.voyager.save()

    def level(self, user=None, skill=None, level=1):
        return SkillProgress.objects.update_or_create(
            user=user or self.child, skill=skill or self.skill,
            defaults={"xp_points": 100 * level, "level": level},
        )[0]

    def complete_prior(self, user=None):
        quest = Quest.objects.create(definition=self.prior, status="completed", end_date=timezone.now())
        QuestParticipant.objects.create(quest=quest, user=user or self.child)
        return quest

    def fact(self, key, *, trigger="reading_logged", at=None):
        return ingest_activity(self.child, trigger, key, trigger, occurred_at=at or timezone.now(), fresh_milestone=True)

    def accepted(self):
        return ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.voyager)

    def test_locked_reading_does_not_accept_voyager(self):
        self.fact("locked")
        self.assertFalse(self.accepted().exists())

    def test_get_does_not_start_even_an_unlocked_milestone_window(self):
        self.complete_prior()
        self.level()
        payload = list_goals(self.child)
        self.assertFalse(self.accepted().exists())
        row = next(row for row in payload["locked_catalog"] if row["id"] == self.voyager.pk)
        self.assertTrue(row["milestone_eligibility"]["unlocked"])
        self.assertNotIn("starts_at", row)

    def test_unrelated_saved_fact_does_not_start_reading_window(self):
        self.complete_prior()
        self.level()
        self.fact("chore", trigger="chore_complete")
        self.assertFalse(self.accepted().exists())

    def test_other_skill_and_sibling_completion_cannot_unlock(self):
        self.complete_prior(self.sibling)
        self.level(skill=self.other, level=6)
        self.fact("not-mine")
        self.assertFalse(self.accepted().exists())

    def test_predecessor_finishing_fact_is_not_replayed_into_successor(self):
        self.level()
        for index in range(3):
            self.fact(f"starter-{index}")
        self.assertEqual(ChallengeOccurrence.objects.get(goal__catalog_definition=self.prior).status, "completed")
        self.assertFalse(self.accepted().exists())
        result = self.fact("next")
        goal = self.accepted().get()
        occurrence = goal.occurrences.get()
        self.assertEqual(occurrence.progress, 1)
        self.assertEqual(goal.catalog_gate_activity_id, result["activity"].pk)
        self.assertEqual(occurrence.snapshot["catalog_gate"]["prerequisite_quest_id"], self.prior.pk)

    def test_named_skill_awarded_before_fresh_fact_allows_that_fact(self):
        self.complete_prior()
        self.fact("before-level")
        self.assertFalse(self.accepted().exists())
        self.level()
        at = timezone.now()
        result = self.fact("first-unlocked", at=at)
        goal = self.accepted().get()
        self.assertEqual((goal.starts_at, goal.ends_at), (at, at + timedelta(days=56)))
        self.assertEqual(goal.occurrences.get().progress, 1)
        self.assertEqual(goal.catalog_gate_activity_id, result["activity"].pk)

    def test_old_pending_id_cannot_credit_after_unlock_even_with_later_timestamp(self):
        old = ChallengeActivity.objects.create(
            user=self.child, source_type="reading_logged", source_id="old-pending",
            trigger_type="reading_logged", occurred_at=timezone.now() + timedelta(days=1),
            occurred_on=timezone.localdate() + timedelta(days=1),
        )
        self.complete_prior()
        self.level()
        self.fact("opening")
        self.fact("old-pending", at=old.occurred_at)
        occurrence = self.accepted().get().occurrences.get()
        self.assertEqual(occurrence.progress, 1)
        self.assertFalse(occurrence.contributions.filter(activity=old).exists())

    def test_old_retry_and_read_cannot_create_a_new_gate_receipt(self):
        self.fact("before")
        old = ChallengeActivity.objects.get(source_id="before")
        old.processed_at = None
        old.save(update_fields=["processed_at"])
        self.complete_prior()
        self.level()
        self.fact("before", at=old.occurred_at)
        list_goals(self.child)
        self.assertFalse(self.accepted().exists())

    def test_solo_start_requires_both_conditions(self):
        self.level()
        with self.assertRaisesMessage(ValueError, "Reading Companion"):
            QuestService.start_quest(self.child, self.voyager.pk)
        self.assertFalse(Quest.objects.filter(definition=self.voyager).exists())

    def test_coop_requires_each_participants_named_skill(self):
        for child in [self.child, self.sibling]:
            self.complete_prior(child)
        self.level()
        with self.assertRaisesMessage(ValueError, "Reading Comprehension"):
            QuestService.start_co_op_quest(self.voyager.pk, [self.child, self.sibling])
        self.assertFalse(Quest.objects.filter(definition=self.voyager).exists())

    def test_authoring_rejects_private_repeatable_and_cyclic_paths(self):
        self.voyager.is_repeatable = True
        with self.assertRaises(ValidationError):
            self.voyager.clean()
        self.voyager.is_repeatable = False
        self.prior.is_system = False
        self.prior.save()
        with self.assertRaises(ValidationError):
            self.voyager.clean()
        self.prior.is_system = True
        self.prior.prerequisite_quest = self.voyager
        self.prior.save()
        with self.assertRaises(ValidationError):
            self.voyager.clean()

    def test_paused_named_skill_and_missing_native_badge_remain_locked(self):
        self.complete_prior()
        progress = self.level()
        progress.unlocked = False
        progress.save(update_fields=["unlocked"])
        self.fact("paused-skill")
        self.assertFalse(self.accepted().exists())
        progress.unlocked = True
        progress.save(update_fields=["unlocked"])
        badge = Badge.objects.create(name="Gate badge", criteria_type="skill_level_reached", criteria_value={"level": 6})
        self.voyager.required_badge = badge
        self.voyager.save()
        self.fact("missing-badge")
        self.assertFalse(self.accepted().exists())
        UserBadge.objects.create(user=self.child, badge=badge)
        self.fact("with-badge")
        self.assertEqual(self.accepted().get().occurrences.get().progress, 1)

    def test_old_accepted_goal_without_occurrence_keeps_its_45_day_promise(self):
        self.voyager.prerequisite_quest = self.voyager.required_skill = None
        self.voyager.required_skill_level = 0
        self.voyager.duration_days = 45
        self.voyager.save()
        list_goals(self.child)
        goal = self.accepted().get()
        goal.occurrences.all().delete()
        before = (goal.starts_at, goal.ends_at, goal.target, goal.description, goal.coin_reward, goal.xp_reward)
        self.voyager.duration_days = 56
        self.set_gate()
        self.fact("grandfathered")
        goal.refresh_from_db()
        self.assertEqual((goal.starts_at, goal.ends_at, goal.target, goal.description, goal.coin_reward, goal.xp_reward), before)
        self.assertEqual(goal.catalog_gate_snapshot, {})
        self.assertIsNone(goal.catalog_gate_activity_id)
        self.assertEqual(goal.occurrences.get().progress, 1)

    def test_two_weekly_readings_are_accepted_and_expire_without_rearming(self):
        self.complete_prior()
        self.level()
        start = timezone.now()
        for day in range(56):
            if day % 7 < 2:
                at = start + timedelta(days=day)
                with patch("django.utils.timezone.now", return_value=at):
                    self.fact(f"two-weekly-{day}", at=at)
        goal = self.accepted().get()
        occurrence = goal.occurrences.get()
        self.assertEqual((occurrence.progress, occurrence.ends_at), (16, start + timedelta(days=56)))
        with patch("django.utils.timezone.now", return_value=goal.ends_at):
            self.fact("exclusive-end", at=goal.ends_at)
            result = list_goals(self.child)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 16)
        self.assertEqual(next(row for row in result["results"] if row["id"] == f"goal:{occurrence.pk}")["status"], "expired")
        self.assertEqual(self.accepted().count(), 1)
        self.assertEqual(goal.occurrences.count(), 1)
        self.assertIsNone(occurrence.awarded_at)

    def test_new_backdated_source_before_prerequisite_does_not_open_window(self):
        before = timezone.now()
        self.complete_prior()
        self.level()
        self.fact("backdated", at=before)
        self.assertFalse(self.accepted().exists())

    def test_failed_first_processing_keeps_gate_receipt_for_one_exact_retry(self):
        self.complete_prior()
        self.level()
        with patch("apps.quests.goals._process", side_effect=RuntimeError("processing failed")):
            with self.assertRaisesMessage(RuntimeError, "processing failed"):
                self.fact("retryable")
        goal = self.accepted().get()
        boundary = (goal.starts_at, goal.ends_at, goal.catalog_gate_activity_id, goal.catalog_gate_snapshot)
        self.assertEqual(goal.occurrences.get().progress, 0)
        list_goals(self.child)
        self.fact("retryable")
        self.fact("retryable")
        goal.refresh_from_db()
        self.assertEqual((goal.starts_at, goal.ends_at, goal.catalog_gate_activity_id, goal.catalog_gate_snapshot), boundary)
        self.assertEqual(goal.occurrences.get().progress, 1)
        self.assertEqual(goal.occurrences.get().contributions.count(), 1)

    def test_existing_expired_legacy_window_cannot_rearm_or_appear_as_new(self):
        self.complete_prior()
        self.level()
        old = Quest.objects.create(definition=self.voyager, status="expired", end_date=timezone.now())
        QuestParticipant.objects.create(quest=old, user=self.child)
        self.fact("after-legacy-expiry")
        self.assertFalse(self.accepted().exists())
        self.assertNotIn(self.voyager.pk, [row["id"] for row in list_goals(self.child)["locked_catalog"]])
        with self.assertRaisesMessage(ValueError, "accepted window"):
            QuestService.start_quest(self.child, self.voyager.pk)

    def test_real_daily_reading_xp_unlocks_and_replayed_sessions_cannot_credit_twice(self):
        from apps.reading.models import ReadingBook
        self.skill.category.name = "Language Arts"
        self.skill.category.save(update_fields=["name"])
        self.complete_prior()
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=90, level=0)
        book = ReadingBook.objects.create(user=self.child, title="Reading source", client_request_id=uuid4(), create_payload={})
        client = APIClient()
        client.force_authenticate(self.child)
        payload = {"book": book.pk, "duration_minutes": 10, "client_request_id": str(uuid4())}
        with patch("apps.rpg.services.DropService.process_drops", return_value=[]):
            first = client.post("/api/reading-sessions/", payload, format="json")
            self.assertEqual(first.status_code, 201, first.data)
            self.assertEqual(client.post("/api/reading-sessions/", payload, format="json").status_code, 200)
            another = client.post("/api/reading-sessions/", {**payload, "client_request_id": str(uuid4())}, format="json")
            self.assertEqual(another.status_code, 201, another.data)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).level, 1)
        occurrence = self.accepted().get().occurrences.get()
        self.assertEqual((occurrence.progress, occurrence.contributions.count()), (1, 1))
        self.assertEqual(ChallengeActivity.objects.filter(user=self.child, trigger_type="reading_logged").count(), 1)

    def test_payout_failure_rolls_back_award_but_retry_keeps_original_gate_window(self):
        self.complete_prior()
        self.level()
        self.voyager.target_value = 1
        self.voyager.coin_reward = 7
        self.voyager.save()
        with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("payout unavailable")):
            with self.assertRaisesMessage(RuntimeError, "payout unavailable"):
                self.fact("payout-retry")
        goal = self.accepted().get()
        boundary = (goal.starts_at, goal.ends_at, goal.catalog_gate_activity_id)
        self.assertEqual(goal.occurrences.get().progress, 0)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.fact("payout-retry")
        paid = goal.occurrences.get()
        saved = (paid.snapshot, paid.completed_at, paid.awarded_at, paid.reward_receipt)
        self.fact("payout-retry")
        list_goals(self.child)
        paid.refresh_from_db()
        goal.refresh_from_db()
        self.assertEqual((goal.starts_at, goal.ends_at, goal.catalog_gate_activity_id), boundary)
        self.assertEqual((paid.snapshot, paid.completed_at, paid.awarded_at, paid.reward_receipt), saved)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=7).count(), 1)

    def test_exact_subday_deadline_survives_household_dst_and_later_zone_edit(self):
        self.complete_prior()
        self.level()
        self.child.family.timezone = "America/New_York"
        self.child.family.save(update_fields=["timezone"])
        start = datetime(timezone.now().year + 1, 10, 20, 16, 17, tzinfo=UTC)
        with patch("django.utils.timezone.now", return_value=start):
            self.fact("dst-opening", at=start)
        goal = self.accepted().get()
        end = goal.ends_at
        self.assertEqual(end, start + timedelta(days=56))
        self.assertNotEqual(start.astimezone(ZoneInfo("America/New_York")).utcoffset(),
                            end.astimezone(ZoneInfo("America/New_York")).utcoffset())
        self.assertEqual(goal.timezone_name, "America/New_York")
        self.child.family.timezone = "Pacific/Auckland"
        self.child.family.save(update_fields=["timezone"])
        with patch("django.utils.timezone.now", return_value=end - timedelta(microseconds=1)):
            self.fact("last-microsecond", at=end - timedelta(microseconds=1))
        with patch("django.utils.timezone.now", return_value=end):
            self.fact("deadline", at=end)
        goal.refresh_from_db()
        self.assertEqual((goal.ends_at, goal.timezone_name), (end, "America/New_York"))
        self.assertEqual(goal.occurrences.get().progress, 2)

    def test_selected_child_locked_catalog_is_private_and_reading_it_does_not_award(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        self.complete_prior()
        self.level()
        ready = client.get(f"/api/challenges/?user_id={self.child.pk}")
        sibling = client.get(f"/api/challenges/?user_id={self.sibling.pk}")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(sibling.status_code, 200)
        self.assertTrue(ready.json()["locked_catalog"][0]["milestone_eligibility"]["unlocked"])
        self.assertFalse(sibling.json()["locked_catalog"][0]["milestone_eligibility"]["unlocked"])
        self.assertFalse(self.accepted().exists())
        self.assertFalse(CoinLedger.objects.exists())
        other = make_family("Other milestone family", children=[{"username": "other-gate-child"}]).children[0]
        self.assertEqual(client.get(f"/api/challenges/?user_id={other.pk}").status_code, 404)

    def test_first_observation_of_an_old_reading_reward_cannot_accept_a_gate(self):
        from apps.quests.activity import record_activity
        from apps.reading.models import ReadingDailyReward
        old = ReadingDailyReward.objects.create(
            user=self.child, day=timezone.localdate() - timedelta(days=7),
            awarded_at=timezone.now() - timedelta(days=7), minutes_credited=10,
            xp_awarded=15, coins_awarded=5,
        )
        self.complete_prior()
        self.level()
        record_activity(self.child, "reading_logged", {
            "reading_reward_id": old.pk, "fresh_milestone": True, "catalog_eligible": True,
        })
        self.assertFalse(self.accepted().exists())
        self.assertTrue(ChallengeActivity.objects.filter(user=self.child, source_id=str(old.pk)).exists())

    def test_inactive_policy_does_not_capture_a_source_before_native_game_loop(self):
        from apps.reading.models import ReadingBook
        from apps.quests.models import ChallengeEnrollment, ChallengePin
        self.voyager.prerequisite_quest = self.voyager.required_skill = None
        self.voyager.required_skill_level = 0
        self.voyager.save()
        book = ReadingBook.objects.create(user=self.child, title="Inactive support", client_request_id=uuid4(), create_payload={})
        client = APIClient()
        client.force_authenticate(self.child)
        with patch("apps.reading.services.GameLoopService.on_task_completed", return_value={}):
            response = client.post("/api/reading-sessions/", {
                "book": book.pk, "duration_minutes": 10, "client_request_id": str(uuid4()),
            }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(ChallengeActivity.objects.exists())
        self.assertFalse(ChallengeEnrollment.objects.exists())
        self.assertFalse(ChallengePin.objects.exists())
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_completed_parent_goal_with_same_name_is_not_the_catalog_prerequisite(self):
        from apps.quests.goals import create_goal
        self.level()
        create_goal(self.parent, self.child, {
            "name": self.prior.name, "metric": "count", "target": 1, "unit": "actions",
            "trigger_type": "reading_logged", "period": "from_today", "coin_reward": 0, "xp_reward": 0,
        })
        self.fact("parent-finish")
        self.fact("after-parent-finish")
        self.assertEqual(ChallengeOccurrence.objects.get(goal__is_catalog=False).status, "completed")
        self.assertFalse(self.accepted().exists())

    def test_paid_gate_receipt_and_rewards_survive_later_policy_edits(self):
        self.complete_prior()
        self.level()
        self.voyager.target_value = 1
        self.voyager.coin_reward = 7
        self.voyager.save()
        self.fact("paid")
        goal = self.accepted().get()
        paid = goal.occurrences.get()
        saved_goal = ChallengeGoal.objects.filter(pk=goal.pk).values().get()
        saved_occurrence = ChallengeOccurrence.objects.filter(pk=paid.pk).values().get()
        self.voyager.required_skill_level = 6
        self.voyager.duration_days = 2
        self.voyager.coin_reward = 99
        self.voyager.description = "A later offer"
        self.voyager.save()
        self.fact("after-edit")
        list_goals(self.child)
        self.assertEqual(ChallengeGoal.objects.filter(pk=goal.pk).values().get(), saved_goal)
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=paid.pk).values().get(), saved_occurrence)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=7).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row serialization")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MilestoneGateConcurrencyTests(TransactionTestCase):
    setUp = MilestoneGateTests.setUp
    set_gate = MilestoneGateTests.set_gate
    complete_prior = MilestoneGateTests.complete_prior
    level = MilestoneGateTests.level

    def race(self, identities):
        self.complete_prior()
        self.level()
        at = timezone.now()
        barrier = Barrier(2)

        def worker(identity):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                return ingest_activity(self.child, "reading_logged", identity, "reading_logged", occurred_at=at,
                                       fresh_milestone=True)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, identity) for identity in identities]
            for future in futures:
                future.result(timeout=15)
        goal = ChallengeGoal.objects.get(user=self.child, catalog_definition=self.voyager)
        self.assertEqual(goal.occurrences.count(), 1)
        occurrence = goal.occurrences.get()
        self.assertEqual(occurrence.progress, len(set(identities)))
        self.assertEqual(occurrence.contributions.count(), len(set(identities)))
        self.assertEqual(goal.catalog_gate_activity_id,
                         ChallengeActivity.objects.filter(user=self.child, trigger_type="reading_logged").order_by("pk").first().pk)
        self.assertFalse(CoinLedger.objects.exists())

    def test_concurrent_first_sources_accept_one_frozen_window(self):
        self.race(["first", "second"])

    def test_concurrent_duplicate_first_source_has_one_receipt_and_contribution(self):
        self.race(["same", "same"])
