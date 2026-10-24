"""Future catalog pacing changes preserve every already accepted window."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import StringIO
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.quests.activity import backfill_goal_activity, resolve_activity
from apps.quests.goals import _occurrence, ingest_activity, list_goals, void_activity
from apps.quests.models import ChallengeActivity, ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestRewardItem
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FutureChallengeRewardPolicyTests(TestCase):
    def setUp(self):
        household = make_family("Future rewards", parents=[{"username": "future-parent"}],
                                children=[{"username": "future-child"}, {"username": "future-sibling"}])
        self.parent, self.child, self.sibling = household.parents[0], *household.children
        household.family.timezone = "Pacific/Honolulu"
        household.family.save(update_fields=["timezone"])
        self.now = datetime(2026, 10, 1, 23, 30, tzinfo=ZoneInfo("UTC"))
        self.clock = patch("django.utils.timezone.now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def definition(self, name="Future habit days", *, target=3, coins=10, repeat=False, distinct=True, **changes):
        filters = {"allowed_triggers": ["habit_log"], "reward_policy_version": 2}
        if distinct:
            filters["distinct_active_days"] = True
        return QuestDefinition.objects.create(name=name, description="Show up on separate days.",
            quest_type="collection", target_value=target, duration_days=7,
            is_system=True, is_repeatable=repeat, coin_reward=coins, trigger_filter=filters, **changes)

    def fact(self, key, *, at=None, trigger="habit_log", child=None, occurred_on=None):
        at = at or timezone.now()
        with patch("django.utils.timezone.now", return_value=at):
            return ingest_activity(child or self.child, "future-policy-test", key, trigger,
                                   occurred_at=at, occurred_on=occurred_on)

    def test_same_day_actions_count_once_and_three_local_days_pay_once(self):
        definition = self.definition()
        for index in range(5):
            self.fact(str(index))
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((occurrence.progress, occurrence.status), (1, "active"))
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.fact("second-day", at=self.now + timedelta(days=1))
        self.fact("third-day", at=self.now + timedelta(days=2))
        self.fact("third-day", at=self.now + timedelta(days=2))
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status, occurrence.reward_receipt["coins"]),
                         (3, "completed", 10))
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [10])
        payload = next(row for row in list_goals(self.child)["results"] if row["id"] == f"goal:{occurrence.pk}")
        self.assertEqual(payload["unit"], "active days")
        self.assertIn("once per", payload["what_counts"])

    def test_distinct_days_use_frozen_household_timezone_and_recompute_after_void(self):
        definition = self.definition(target=3)
        first = self.fact("before-utc-midnight", occurred_on=self.now.date() - timedelta(days=20))
        second = self.fact("after-utc-midnight", at=self.now + timedelta(hours=2))
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.progress, 1)
        self.fact("next-local-day", at=self.now + timedelta(hours=12))
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 2)
        void_activity(self.child, "future-policy-test", "before-utc-midnight")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 2, "The second same-day fact retains that day's credit")
        void_activity(self.child, "future-policy-test", "after-utc-midnight")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 1)
        self.assertNotEqual(first["activity"].pk, second["activity"].pk)

    def test_reading_days_cannot_be_completed_by_arbitrary_habit_actions(self):
        definition = self.definition("Seven Nights of Stories", target=5, coins=20)
        definition.trigger_filter["allowed_triggers"] = ["reading_logged"]
        definition.save(update_fields=["trigger_filter"])
        for day in range(5):
            self.fact(f"habit-{day}", at=self.now + timedelta(days=day))
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((occurrence.progress, occurrence.status), (0, "active"))
        for day in range(5):
            self.fact(f"earned-reading-{day}", trigger="reading_logged", at=self.now + timedelta(days=day))
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status, occurrence.reward_receipt["coins"]),
                         (5, "completed", 20))

    def test_saved_window_keeps_full_old_reward_then_next_window_uses_v2_rules(self):
        original = QuestDefinition.objects.create(name="Saved weekly promise", description="Old accepted rule",
            quest_type="collection", target_value=3, duration_days=7, is_system=True, is_repeatable=True,
            coin_reward=40, trigger_filter={"allowed_triggers": ["habit_log"]})
        pouch = ItemDefinition.objects.create(slug="promised-policy-pouch", name="Promised pouch",
            item_type="coin_pouch", coin_value=15, metadata={"coins": 15})
        link = QuestRewardItem.objects.create(quest_definition=original, item=pouch)
        self.fact("old-first")
        accepted = ChallengeOccurrence.objects.get(goal__catalog_definition=original)
        saved = (accepted.starts_at, accepted.ends_at, deepcopy(accepted.snapshot))
        original.coin_reward = 10
        original.trigger_filter = {"allowed_triggers": ["habit_log"], "reward_policy_version": 2,
                                   "distinct_active_days": True}
        original.save(update_fields=["coin_reward", "trigger_filter"])
        link.delete()
        self.fact("old-second")
        self.fact("old-third")
        accepted.refresh_from_db()
        self.assertEqual((accepted.starts_at, accepted.ends_at, accepted.snapshot), saved)
        self.assertEqual((accepted.progress, accepted.reward_receipt["coins"]), (3, 40))
        self.assertEqual(UserInventory.objects.get(user=self.child, item=pouch).quantity, 1)

        next_start = accepted.ends_at
        for index in range(3):
            self.fact(f"future-same-day-{index}", at=next_start)
        later = ChallengeOccurrence.objects.get(goal=accepted.goal, starts_at=next_start)
        self.assertEqual((later.progress, later.status, later.snapshot["coins"], later.snapshot["items"]),
                         (1, "active", 10, []))
        self.assertEqual(later.ends_at, next_start + timedelta(days=7))
        self.fact("future-day-two", at=next_start + timedelta(days=1))
        self.fact("future-day-three", at=next_start + timedelta(days=2))
        later.refresh_from_db()
        self.assertEqual((later.progress, later.reward_receipt["coins"]), (3, 10))
        self.assertEqual(UserInventory.objects.get(user=self.child, item=pouch).quantity, 1)

    def test_duplicate_identity_keeps_accepted_window_but_cannot_create_another_cycle(self):
        definition = self.definition("Ambiguous repeat", target=2, repeat=True, distinct=False)
        self.fact("accepted-first")
        accepted = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.definition("Ambiguous repeat", target=2, repeat=True, distinct=False)
        self.fact("accepted-second")
        accepted.refresh_from_db()
        self.assertEqual(accepted.reward_receipt["coins"], 10)
        self.fact("unaccepted-next-window", at=accepted.ends_at)
        self.assertEqual(ChallengeOccurrence.objects.filter(goal=accepted.goal).count(), 1)
        self.fact("other-child-new", child=self.sibling, at=accepted.ends_at)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.sibling).exists())

    def test_legacy_campaign_start_cannot_bypass_distinct_day_rules(self):
        definition = self.definition()
        with self.assertRaisesMessage(ValueError, "automatically"):
            QuestService.start_quest(self.child, definition.pk)
        with self.assertRaisesMessage(ValueError, "automatically"):
            QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])
        self.assertFalse(Quest.objects.exists())

    def test_future_window_rereads_explicit_policy_after_goal_definition_was_cached(self):
        definition = self.definition(repeat=True)
        self.fact("initial")
        accepted = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        cached = ChallengeGoal.objects.select_related("catalog_definition").get(pk=accepted.goal_id)
        self.assertEqual(cached.catalog_definition.coin_reward, 10)
        QuestDefinition.objects.filter(pk=definition.pk).update(coin_reward=7)
        later = _occurrence(cached, accepted.ends_at)
        self.assertEqual(later.snapshot["coins"], 7)
        accepted.refresh_from_db()
        self.assertEqual(accepted.snapshot["coins"], 10)

    def test_changed_cadence_holds_future_window_without_canceling_the_accepted_one(self):
        definition = self.definition(repeat=True)
        self.fact("cadence-first")
        accepted = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        saved = deepcopy(accepted.snapshot)
        QuestDefinition.objects.filter(pk=definition.pk).update(duration_days=14)
        self.fact("old-window-second")
        accepted.refresh_from_db()
        self.assertEqual(accepted.snapshot, saved)
        self.assertEqual(accepted.progress, 1)
        self.fact("new-cadence-needs-acceptance", at=accepted.ends_at)
        self.assertEqual(ChallengeOccurrence.objects.filter(goal=accepted.goal).count(), 1)

    def test_stories_progress_requires_the_real_ten_minute_daily_reading_receipt(self):
        from apps.reading.models import ReadingBook

        definition = self.definition("Reading receipt days", target=2, coins=20)
        definition.trigger_filter["allowed_triggers"] = ["reading_logged"]
        definition.save(update_fields=["trigger_filter"])
        book = ReadingBook.objects.create(user=self.child, title="Synthetic story", client_request_id=uuid4(),
                                          create_payload={})
        client = APIClient()
        client.force_authenticate(self.child)
        list_goals(self.child)

        def read(minutes):
            response = client.post("/api/reading-sessions/", {
                "book": book.pk, "duration_minutes": minutes, "client_request_id": str(uuid4()),
            }, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            return response

        read(4)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual(occurrence.progress, 0)
        read(6)
        read(10)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 1)
        with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
            read(10)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.reward_receipt["coins"]), (2, 20))

    def test_nonqualifying_savings_completion_cannot_enter_live_or_backfilled_challenge_facts(self):
        from apps.projects.models import SavingsGoal

        rejected = SavingsGoal.objects.create(user=self.child, title="Already funded", target_amount=1,
            completed_at=self.now, reward_qualifies=False)
        accepted = SavingsGoal.objects.create(user=self.child, title="Verified saving", target_amount=10,
            completed_at=self.now, reward_qualifies=True)
        self.assertIsNone(resolve_activity(self.child, "savings_goal_complete", {"savings_goal_id": rejected.pk}))
        self.assertEqual(resolve_activity(self.child, "savings_goal_complete", {
            "savings_goal_id": accepted.pk,
        })["source_id"], str(accepted.pk))
        goal = ChallengeGoal.objects.create(user=self.child, family=self.child.family, created_by=self.parent,
            name="Saving facts", metric="count", target=2, unit="actions", timezone_name="Pacific/Honolulu",
            trigger_filter={"allowed_triggers": ["savings_goal_complete"]},
            starts_at=self.now - timedelta(hours=1), ends_at=self.now + timedelta(days=1))
        backfill_goal_activity(goal)
        self.assertEqual(list(ChallengeActivity.objects.filter(trigger_type="savings_goal_complete")
                              .values_list("source_id", flat=True)), [str(accepted.pk)])

    def test_policy_fields_are_validated_and_do_not_apply_to_private_or_boss_definitions(self):
        definition = self.definition()
        definition.clean()
        for fields in ({"distinct_active_days": 1}, {"reward_policy_version": True},
                       {"reward_policy_version": 3}, {"distinct_active_days": "yes"}):
            with self.subTest(fields=fields):
                definition.trigger_filter = {"allowed_triggers": ["habit_log"], **fields}
                with self.assertRaises(ValidationError):
                    definition.clean()
        definition.trigger_filter = {"allowed_triggers": ["habit_log"], "reward_policy_version": 2,
                                     "distinct_active_days": True}
        for changes in ({"quest_type": "boss"}, {"created_by": self.parent}, {"is_cooperative": True}):
            with self.subTest(changes=changes):
                for key, value in changes.items():
                    setattr(definition, key, value)
                with self.assertRaises(ValidationError):
                    definition.clean()
                definition.quest_type, definition.created_by, definition.is_cooperative = "collection", None, False

    def test_global_editor_and_catalog_audit_recognize_the_versioned_rules(self):
        from apps.mcp_server.catalog import audit_catalog_rows
        from apps.rpg.content.workbench_validation import _validate_values

        definition = self.definition()
        _validate_values("quests", {"trigger_filter": definition.trigger_filter}, new=False)
        findings, _ = audit_catalog_rows("quests", [definition])
        self.assertNotIn("invalid_trigger_filter", {row["code"] for row in findings})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BundledFutureChallengeRewardTests(TestCase):
    def test_default_loader_publishes_smaller_v2_offers_and_removes_future_pouch_links(self):
        call_command("loadrpgcontent", stdout=StringIO())
        expected = {"First Week of Freshman Year": (20, 5, "habit_log"),
                    "Seven Nights of Stories": (20, 5, "reading_logged"),
                    "Weekly Reset": (10, 5, "habit_log"),
                    "Pantry Patroller": (10, 5, "chore_complete"),
                    "Comeback Kid": (10, 3, "habit_log"),
                    "Comeback Kid II": (15, 5, None),
                    "Daily Rituals": (2, 3, "habit_log")}
        for name, (coins, target, trigger) in expected.items():
            with self.subTest(name=name):
                definition = QuestDefinition.objects.get(name=name)
                self.assertEqual((definition.coin_reward, definition.target_value), (coins, target))
                self.assertEqual(definition.trigger_filter.get("reward_policy_version"), 2)
                self.assertEqual(definition.trigger_filter.get("distinct_active_days", False), name != "Daily Rituals")
                if trigger:
                    self.assertEqual(definition.trigger_filter["allowed_triggers"], [trigger])
                if name in {"Weekly Reset", "Pantry Patroller", "Daily Rituals"}:
                    self.assertFalse(definition.reward_items.exists())

        # Upgrades must remove the old future links, while an already frozen
        # modern occurrence's promise remains in its independent snapshot.
        weekly = QuestDefinition.objects.get(name="Weekly Reset")
        pouch = ItemDefinition.objects.get(slug="pouch-small")
        QuestRewardItem.objects.create(quest_definition=weekly, item=pouch)
        stories = QuestDefinition.objects.get(name="Seven Nights of Stories")
        cosmetic = ItemDefinition.objects.create(slug="retained-story-frame", name="Earlier story frame",
                                                 item_type="cosmetic_frame")
        QuestRewardItem.objects.create(quest_definition=stories, item=cosmetic)
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertFalse(weekly.reward_items.exists())
        self.assertTrue(stories.reward_items.filter(item=cosmetic).exists(),
                        "A Coin rebalance must not prune an earlier pack's unrelated cosmetic reward")

    def test_loader_preserves_parent_authored_definitions_and_active_legacy_promises(self):
        call_command("loadrpgcontent", stdout=StringIO())
        household = make_family("Policy preservation", parents=[{"username": "policy-parent"}],
                                children=[{"username": "policy-child"}])
        parent, child = household.parents[0], household.children[0]
        custom = QuestDefinition.objects.create(name="Weekly Reset", description="Parent's private plan",
            created_by=parent, is_system=False, quest_type="collection", target_value=2, duration_days=9,
            coin_reward=713, xp_reward=37, trigger_filter={"allowed_triggers": ["chore_complete"]})
        definition = QuestDefinition.objects.get(name="Weekly Reset", is_system=True)
        definition.coin_reward = 20
        definition.trigger_filter = {"allowed_triggers": ["habit_log"]}
        definition.save(update_fields=["coin_reward", "trigger_filter"])
        pouch = ItemDefinition.objects.get(slug="pouch-small")
        QuestRewardItem.objects.create(quest_definition=definition, item=pouch)
        quest = Quest.objects.create(definition=definition, start_date=timezone.now(),
                                     end_date=timezone.now() + timedelta(days=7), reward_items_snapshot=None)
        from apps.quests.models import QuestParticipant
        QuestParticipant.objects.create(quest=quest, user=child)
        output = StringIO()
        call_command("loadrpgcontent", stdout=output)
        definition.refresh_from_db()
        self.assertEqual((definition.coin_reward, definition.trigger_filter),
                         (20, {"allowed_triggers": ["habit_log"]}))
        self.assertIn("active legacy quest", output.getvalue())
        quest.refresh_from_db()
        self.assertEqual(quest.reward_items_snapshot[0]["item_id"], pouch.pk)
        custom.refresh_from_db()
        self.assertEqual((custom.coin_reward, custom.xp_reward, custom.target_value, custom.duration_days),
                         (713, 37, 2, 9))
        self.assertEqual(custom.trigger_filter, {"allowed_triggers": ["chore_complete"]})


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL user-row serialization")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FutureChallengeRewardConcurrencyTests(TransactionTestCase):
    def test_parallel_same_day_facts_do_not_complete_a_two_day_goal(self):
        child = make_family("Concurrent active days", children=[{"username": "parallel-days-child"}]).children[0]
        definition = QuestDefinition.objects.create(name="Two real active days", description="Separate days",
            quest_type="collection", target_value=2, duration_days=7, is_system=True, coin_reward=10,
            trigger_filter={"allowed_triggers": ["habit_log"], "reward_policy_version": 2,
                            "distinct_active_days": True})
        at = timezone.now()
        barrier = Barrier(2)

        def contribute(identity):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                return ingest_activity(child, "parallel-policy", identity, "habit_log", occurred_at=at)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(contribute, identity) for identity in ("one", "two")]
            for future in futures:
                future.result(timeout=15)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((occurrence.progress, occurrence.status), (1, "active"))
        self.assertFalse(CoinLedger.objects.filter(user=child).exists())
        with patch("django.utils.timezone.now", return_value=at + timedelta(days=1)):
            ingest_activity(child, "parallel-policy", "next-day", "habit_log", occurred_at=at + timedelta(days=1))
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.reward_receipt["coins"]), (2, 10))
        self.assertEqual(list(CoinLedger.objects.filter(user=child).values_list("amount", flat=True)), [10])
