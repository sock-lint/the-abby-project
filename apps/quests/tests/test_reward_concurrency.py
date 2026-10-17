"""Co-op payout serialization uses real users and independent PG connections."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.achievements.services import SkillService
from apps.notifications.models import Notification
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestRewardItem, QuestSkillTag
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import GameLoopService
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class QuestRewardConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.first, self.second = make_family(
            "Concurrent quest family", children=[{"username": "quest-one"}, {"username": "quest-two"}],
        ).children
        category = SkillCategory.objects.create(name="Co-op concurrency")
        self.skill = Skill.objects.create(name="Shared effort", category=category)
        self.definition = QuestDefinition.objects.create(
            name="Shared campaign", description="Saved co-op", quest_type="collection",
            target_value=2, coin_reward=13, xp_reward=24,
        )
        QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill)
        self.item = ItemDefinition.objects.create(slug="coop-food", name="Team snack", item_type="food")
        QuestRewardItem.objects.create(quest_definition=self.definition, item=self.item, quantity=2)
        self.quest = QuestService.start_co_op_quest(self.definition.pk, [self.second, self.first])

    @staticmethod
    def _worker(action, pids=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '12s'")
                cursor.execute("SELECT pg_backend_pid()")
                if pids is not None:
                    pids.append(cursor.fetchone()[0])
            return action()
        finally:
            connection.close()

    def _assert_paid_once(self, *, source_xp=0):
        self.quest.refresh_from_db()
        self.assertEqual((self.quest.status, self.quest.current_progress), (Quest.Status.COMPLETED, 2))
        for user in (self.first, self.second):
            self.assertEqual(list(CoinLedger.objects.filter(
                user=user, description="Quest complete: Shared campaign",
            ).values_list("amount", flat=True)), [13])
            self.assertEqual(SkillProgress.objects.get(user=user, skill=self.skill).xp_points, 24 + source_xp)
            self.assertEqual(UserInventory.objects.get(user=user, item=self.item).quantity, 2)
            self.assertEqual(Notification.objects.filter(user=user, title="Challenge complete: Shared campaign!").count(), 1)

    def test_overlapping_participant_hits_commit_one_full_payout_each(self):
        reached, release = Event(), Event()
        original_save = Quest.save
        second_pids = []

        def hold_first_progress(quest, *args, **kwargs):
            result = original_save(quest, *args, **kwargs)
            if quest.pk == self.quest.pk and quest.current_progress == 1 and not reached.is_set():
                reached.set()
                if not release.wait(10):
                    raise TimeoutError("First participant was not released")
            return result

        with patch.object(Quest, "save", hold_first_progress), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self._worker, lambda: QuestService.record_progress(self.first, "chore_complete"))
            second = None
            try:
                self.assertTrue(reached.wait(5))
                second = pool.submit(self._worker, lambda: QuestService.record_progress(self.second, "chore_complete"), second_pids)
                deadline, blocked = monotonic() + 4, False
                while monotonic() < deadline:
                    if second.done():
                        second.result()
                        break
                    if second_pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [second_pids[0]])
                            row = cursor.fetchone()
                        if row and row[0] == "Lock":
                            blocked = True
                            break
                    sleep(0.01)
                self.assertTrue(blocked, "Second participant did not serialize against in-flight progress")
            finally:
                release.set()
            results = [first.result(timeout=15), second.result(timeout=15)]
        self.assertEqual(sum(result["completed"] for result in results), 1)
        self._assert_paid_once()
        self.assertEqual(list(QuestParticipant.objects.filter(quest=self.quest).values_list("contribution", flat=True)), [1, 1])
        self.assertIsNone(QuestService.record_progress(self.first, "chore_complete"))
        self._assert_paid_once()

    def test_source_transactions_holding_opposite_users_complete_without_deadlock(self):
        ready = Barrier(2)
        Quest.objects.filter(pk=self.quest.pk).update(current_progress=1)
        QuestParticipant.objects.filter(quest=self.quest, user=self.first).update(contribution=1)

        def source(user):
            with transaction.atomic():
                # Match source services: their XP award already owns the
                # acting user's gate before they invoke the game loop.
                SkillService.award_xp(user, self.skill, 3)
                ready.wait(timeout=8)
                result = GameLoopService.on_task_completed(user, "chore_complete")
            return result

        with patch("apps.rpg.services.logger.exception") as errors, ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(self._worker, lambda user=user: source(user)) for user in (self.second, self.first)]
            results = [future.result(timeout=25) for future in results]
        errors.assert_not_called()
        self.assertEqual(sum(bool(result["quest"] and result["quest"]["completed"]) for result in results), 1)
        self._assert_paid_once(source_xp=3)

    def test_rolled_back_source_never_runs_deferred_coop_progress(self):
        with self.assertRaisesRegex(RuntimeError, "rollback source"):
            with transaction.atomic():
                SkillService.award_xp(self.second, self.skill, 3)
                result = GameLoopService.on_task_completed(self.second, "chore_complete")
                self.assertIsNone(result["quest"])
                self.quest.refresh_from_db()
                self.assertEqual(self.quest.current_progress, 0)
                raise RuntimeError("rollback source")
        self.quest.refresh_from_db()
        self.assertEqual(self.quest.current_progress, 0)
        self.assertFalse(SkillProgress.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_top_level_game_loop_progress_and_completion_remain_synchronous(self):
        first_result = GameLoopService.on_task_completed(self.first, "habit_log")
        self.assertEqual(first_result["quest"]["new_progress"], 1)
        self.assertFalse(first_result["quest"]["completed"])
        final_result = GameLoopService.on_task_completed(self.second, "habit_log")
        self.assertTrue(final_result["quest"]["completed"])
        self._assert_paid_once()

    def test_failed_deferred_payout_preserves_source_and_can_retry(self):
        QuestService.record_progress(self.first, "chore_complete")
        from apps.notifications.services import notify

        def fail_last_recipient(user, *args, **kwargs):
            if user.pk == self.second.pk:
                raise RuntimeError("late co-op notification")
            return notify(user, *args, **kwargs)

        with patch("apps.notifications.services.notify", side_effect=fail_last_recipient):
            with transaction.atomic():
                SkillService.award_xp(self.second, self.skill, 3)
                result = GameLoopService.on_task_completed(self.second, "chore_complete")
                self.assertIsNone(result["quest"])
        self.quest.refresh_from_db()
        self.assertEqual((self.quest.status, self.quest.current_progress), (Quest.Status.ACTIVE, 1))
        self.assertEqual(SkillProgress.objects.get(user=self.second, skill=self.skill).xp_points, 3)
        self.assertFalse(SkillProgress.objects.filter(user=self.first, skill=self.skill).exists())
        self.assertFalse(CoinLedger.objects.filter(description="Quest complete: Shared campaign").exists())
        self.assertFalse(UserInventory.objects.exists())
        self.assertTrue(QuestService.record_progress(self.second, "chore_complete")["completed"])
        for user, expected_xp in ((self.first, 24), (self.second, 27)):
            self.assertEqual(SkillProgress.objects.get(user=user, skill=self.skill).xp_points, expected_xp)
            self.assertEqual(UserInventory.objects.get(user=user, item=self.item).quantity, 2)

    def test_failed_final_completion_notice_does_not_report_rolled_back_reward(self):
        QuestService.record_progress(self.first, "chore_complete")
        from apps.notifications.services import notify

        def fail_pipeline_notice(user, *args, **kwargs):
            if kwargs.get("notification_type") == "quest_completed":
                raise RuntimeError("final completion notice failed")
            return notify(user, *args, **kwargs)

        with patch("apps.notifications.services.notify", side_effect=fail_pipeline_notice):
            with transaction.atomic():
                result = GameLoopService.on_task_completed(self.second, "chore_complete")
        self.quest.refresh_from_db()
        self.assertEqual((self.quest.status, self.quest.current_progress), (Quest.Status.ACTIVE, 1))
        self.assertFalse(CoinLedger.objects.filter(description="Quest complete: Shared campaign").exists())
        self.assertFalse(UserInventory.objects.exists())
        self.assertIsNone(result["quest"])
        self.assertNotIn("Challenge complete: Shared campaign", result["notifications"])

    def test_deferred_source_does_not_credit_a_replacement_campaign(self):
        callbacks = []
        QuestService.record_progress(self.first, "chore_complete")
        with patch("django.db.transaction.on_commit", side_effect=lambda callback, **kwargs: callbacks.append(callback)):
            with transaction.atomic():
                result = GameLoopService.on_task_completed(self.second, "chore_complete")
        self.assertIsNone(result["quest"])
        self.assertTrue(callbacks)

        # Another participant can finish before the callback takes the user
        # gates. A subsequent assignment must not inherit that old source.
        QuestService.record_progress(self.first, "chore_complete")
        replacement_definition = QuestDefinition.objects.create(
            name="Next campaign", description="Assigned after the source", quest_type="collection", target_value=2,
        )
        replacement = QuestService.start_co_op_quest(replacement_definition.pk, [self.first, self.second])
        for callback in callbacks:
            callback()
        replacement.refresh_from_db()
        self.assertEqual(replacement.current_progress, 0)
        self.assertIsNone(result["quest"])
