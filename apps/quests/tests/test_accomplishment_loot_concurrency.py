"""Accomplishment loot shares PostgreSQL's existing quest payout locks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.quests.goals import ingest_activity
from apps.quests.models import ChallengeOccurrence, Quest, QuestDefinition
from apps.quests.services import QuestService
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class QuestAccomplishmentLootConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.first, self.second = make_family(
            "Concurrent loot family",
            children=[{"username": "loot-race-one"}, {"username": "loot-race-two"}],
        ).children
        self.item = ItemDefinition.objects.create(
            slug="concurrent-quest-loot", name="Quest discovery", item_type="food",
        )
        DropTable.objects.create(trigger_type=TriggerType.QUEST_COMPLETE, item=self.item)
        self.definition = QuestDefinition.objects.create(
            name="Shared accomplishment", description="Two saved actions", is_system=True,
            quest_type="collection", target_value=2,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )

    def race(self, actions):
        barrier = Barrier(len(actions))

        def worker(action):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                return action()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(worker, action) for action in actions]
            return [future.result(timeout=20) for future in futures]

    def fact(self, identity):
        user = get_user_model().objects.get(pk=self.first.pk)
        return ingest_activity(user, "chore_complete", identity, "chore_complete")

    def assert_one_drop(self, user):
        self.assertEqual(DropLog.objects.filter(
            user=user, trigger_type=TriggerType.QUEST_COMPLETE,
        ).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=user, item=self.item).quantity, 1)

    def test_distinct_concurrent_final_facts_pay_one_automatic_completion_drop(self):
        self.fact("first")
        results = self.race([lambda: self.fact("second"), lambda: self.fact("third")])
        self.assertEqual(sum(len(result["goals"]) for result in results), 1)
        self.assertEqual(ChallengeOccurrence.objects.get().status, "completed")
        self.assert_one_drop(self.first)

    def test_duplicate_concurrent_final_fact_pays_one_automatic_completion_drop(self):
        self.fact("first")
        self.race([lambda: self.fact("second"), lambda: self.fact("second")])
        self.assert_one_drop(self.first)

    def test_concurrent_legacy_finishing_hits_pay_one_drop_to_each_participant(self):
        quest = QuestService.start_co_op_quest(self.definition.pk, [self.second, self.first])
        QuestService.record_progress(self.first, "chore_complete")

        def hit(user_id):
            user = get_user_model().objects.get(pk=user_id)
            return QuestService.record_progress(user, "chore_complete")

        results = self.race([lambda: hit(self.first.pk), lambda: hit(self.second.pk)])
        self.assertEqual(sum(bool(result and result["completed"]) for result in results), 1)
        quest.refresh_from_db()
        self.assertEqual(quest.status, Quest.Status.COMPLETED)
        for user in (self.first, self.second):
            self.assert_one_drop(user)
