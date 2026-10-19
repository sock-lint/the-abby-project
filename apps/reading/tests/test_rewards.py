"""Reading rewards use saved, once-daily credit rather than mutable history."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as datetime_timezone
from importlib import import_module
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection, connections
from django.apps import apps
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.reading.models import ReadingBook, ReadingSession
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


NOW = datetime(2026, 10, 18, 1, tzinfo=datetime_timezone.utc)


class ReadingRewardSetup:
    def setUp(self):
        super().setUp()
        clock = patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        family = make_family(
            "Reading adventurers", parents=[{"username": "reading-parent"}],
            children=[{"username": "reading-child"}, {"username": "reading-sibling"}],
        )
        self.family = family.family
        self.family.timezone = "America/Los_Angeles"
        self.family.save(update_fields=["timezone"])
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        self.book = ReadingBook.objects.create(
            user=self.child, title="A dragon story", client_request_id=uuid4(), create_payload={},
        )
        category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(name="Reading Comprehension", category=category)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def create_session(self, minutes=10, **extra):
        return self.client.post("/api/reading-sessions/", {
            "book": self.book.pk, "duration_minutes": minutes, "client_request_id": str(uuid4()), **extra,
        }, format="json")

    def adventure(self, **params):
        response = self.client.get("/api/reading/summary/", params)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("reading_adventure", response.data)
        return response.data["reading_adventure"]

    def reading_coins(self, user=None):
        return CoinLedger.objects.filter(user=user or self.child, reason="reading")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], TIME_ZONE="America/Phoenix")
class ReadingRewardTests(ReadingRewardSetup, TestCase):
    def test_reading_summary_is_read_only_and_starts_with_ten_minute_goal(self):
        self.assertEqual(self.adventure(), {
            "day": "2026-10-17", "target_minutes": 10, "minutes_credited": 0,
            "remaining_minutes": 10, "earned": False, "base_xp": 15,
            "base_coins": 5, "xp_awarded": 0, "coins_awarded": 0,
            "skill_name": "Reading Comprehension",
        })
        self.adventure()
        from apps.reading.models import ReadingDailyReward
        self.assertFalse(ReadingDailyReward.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())

    def test_partial_sessions_combine_and_only_crossing_session_has_reward(self):
        first = self.create_session(4)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertIn("reading_reward", first.data)
        self.assertIsNone(first.data["reading_reward"])
        self.assertEqual(self.adventure()["remaining_minutes"], 6)
        second = self.create_session(6, format="audiobook")
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(second.data["reading_reward"], {
            "day": "2026-10-17", "xp_awarded": 15, "coins_awarded": 5,
        })
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)
        self.assertEqual(list(self.reading_coins().values_list("amount", flat=True)), [5])
        self.child.character_profile.refresh_from_db()
        self.assertEqual(self.child.character_profile.login_streak, 1)
        adventure = self.adventure()
        self.assertEqual((adventure["minutes_credited"], adventure["remaining_minutes"], adventure["earned"]), (10, 0, True))
        third = self.create_session(600)
        self.assertIsNone(third.data["reading_reward"])
        self.assertEqual(self.reading_coins().count(), 1)
        self.assertEqual(self.adventure()["minutes_credited"], 10)

    def test_print_ebook_and_audiobook_are_equally_rewarded_without_reflections(self):
        for index, reading_format in enumerate(("print", "ebook", "audiobook")):
            with self.subTest(reading_format=reading_format), patch("django.utils.timezone.now", return_value=NOW + timedelta(days=index)):
                response = self.create_session(format=reading_format)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["reading_reward"]["xp_awarded"], 15)
        self.assertEqual(self.reading_coins().count(), 3)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 45)

    def test_backdated_pages_and_notes_only_entries_do_not_advance_reward(self):
        for details in (
            {"duration_minutes": 600, "occurred_on": "2026-10-16"},
            {"duration_minutes": 0, "pages_read": 2000},
            {"duration_minutes": 0, "section": "Chapter 4"},
            {"duration_minutes": 0, "reflection": "The dragon found a friend."},
        ):
            response = self.create_session(**details)
            self.assertEqual(response.status_code, 201, response.data)
            self.assertIn("reading_reward", response.data)
            self.assertIsNone(response.data["reading_reward"])
        self.assertEqual(self.adventure()["minutes_credited"], 0)
        self.assertFalse(self.reading_coins().exists())

    def test_correction_and_book_status_never_add_or_revoke_credit(self):
        first = self.create_session(4)
        url = f"/api/reading-sessions/{first.data['id']}/"
        corrected = self.client.patch(url, {"duration_minutes": 600}, format="json")
        self.assertEqual(corrected.status_code, 200, corrected.data)
        self.assertEqual(self.adventure()["minutes_credited"], 4)
        self.client.patch(f"/api/reading-books/{self.book.pk}/", {"status": "finished"}, format="json")
        self.assertFalse(self.reading_coins().exists())
        awarded = self.create_session(6)
        receipt = awarded.data["reading_reward"]
        corrected = self.client.patch(f"/api/reading-sessions/{awarded.data['id']}/", {
            "duration_minutes": 0, "section": "Correction", "occurred_on": "2026-10-16",
        }, format="json")
        self.assertEqual(corrected.data["reading_reward"], receipt)
        self.assertTrue(self.adventure()["earned"])
        self.assertEqual(self.reading_coins().count(), 1)

    def test_old_or_existing_entries_never_gain_reward_when_corrected_to_today(self):
        old = self.create_session(600, occurred_on="2026-10-16")
        self.client.patch(f"/api/reading-sessions/{old.data['id']}/", {"occurred_on": "2026-10-17"}, format="json")
        ReadingSession.objects.create(
            user=self.child, book=self.book, occurred_on="2026-10-17", duration_minutes=500,
            client_request_id=uuid4(), create_payload={},
        )
        self.assertEqual(self.adventure()["minutes_credited"], 0)
        self.assertFalse(self.reading_coins().exists())

    def test_uuid_retry_and_conflict_never_add_credit_after_correction_or_midnight(self):
        request_id = str(uuid4())
        original = self.create_session(4, client_request_id=request_id)
        url = f"/api/reading-sessions/{original.data['id']}/"
        self.client.patch(url, {"duration_minutes": 8}, format="json")
        retry = self.create_session(4, client_request_id=request_id)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(self.adventure()["minutes_credited"], 4)
        self.assertEqual(self.create_session(10, client_request_id=request_id).status_code, 400)
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)):
            retry = self.create_session(4, client_request_id=request_id)
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(self.adventure()["minutes_credited"], 0)
        self.assertFalse(self.reading_coins().exists())

    def test_deletion_preserves_partial_credit_and_earned_guard(self):
        first = self.create_session(4)
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{first.data['id']}/").status_code, 204)
        self.assertEqual(self.adventure()["minutes_credited"], 4)
        second = self.create_session(6)
        self.assertIsNotNone(second.data["reading_reward"])
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{second.data['id']}/").status_code, 204)
        replacement = self.create_session(600)
        self.assertIsNone(replacement.data["reading_reward"])
        from apps.reading.models import ReadingDailyReward
        receipt = ReadingDailyReward.objects.get(user=self.child)
        self.assertIsNone(receipt.source_session_id)
        self.assertTrue(self.adventure()["earned"])
        self.assertEqual(self.reading_coins().count(), 1)

    def test_retry_of_deleted_partial_or_rewarding_request_never_adds_credit(self):
        partial_id = str(uuid4())
        first = self.create_session(4, client_request_id=partial_id)
        self.client.delete(f"/api/reading-sessions/{first.data['id']}/")
        replay = self.create_session(4, client_request_id=partial_id)
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(self.adventure()["minutes_credited"], 4)
        award_id = str(uuid4())
        awarded = self.create_session(6, client_request_id=award_id)
        self.client.delete(f"/api/reading-sessions/{awarded.data['id']}/")
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)):
            replay = self.create_session(6, client_request_id=award_id)
            self.assertIsNone(replay.data["reading_reward"])
            self.assertEqual(self.adventure()["minutes_credited"], 0)
        self.assertEqual(self.reading_coins().count(), 1)

    def test_deleted_historical_zero_minute_and_over_cap_requests_stay_ineligible_tomorrow(self):
        historical_id, zero_id, capped_id = (str(uuid4()) for _ in range(3))
        historical = self.create_session(600, occurred_on="2026-10-16", client_request_id=historical_id)
        zero = self.create_session(0, section="Chapter 1", client_request_id=zero_id)
        self.create_session()
        capped = self.create_session(600, client_request_id=capped_id)
        for saved in (historical, zero, capped):
            self.assertEqual(self.client.delete(f"/api/reading-sessions/{saved.data['id']}/").status_code, 204)
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)):
            for request_id in (historical_id, zero_id, capped_id):
                replay = self.create_session(600, client_request_id=request_id)
                self.assertEqual(replay.status_code, 201, replay.data)
                self.assertIsNone(replay.data["reading_reward"])
                self.assertEqual(self.adventure()["minutes_credited"], 0)
        from apps.reading.models import ReadingRewardCredit
        self.assertEqual(list(ReadingRewardCredit.objects.filter(
            client_request_id__in=[historical_id, zero_id, capped_id],
        ).values_list("minutes", flat=True)), [0, 0, 0])
        self.assertEqual(self.reading_coins().count(), 1)

    def test_reward_receipt_is_read_only_and_scoped_to_reader(self):
        for field, value in (("reading_reward", {"xp_awarded": 500}), ("xp_awarded", 500), ("coins_awarded", 500)):
            response = self.create_session(**{field: value})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.adventure()["minutes_credited"], 0)
        saved = self.create_session()
        self.assertIsNotNone(saved.data["reading_reward"])
        self.assertEqual(self.client.patch(f"/api/reading-sessions/{saved.data['id']}/", {"reading_reward": None}, format="json").status_code, 400)
        self.client.force_authenticate(self.sibling)
        self.assertEqual(self.adventure()["minutes_credited"], 0)
        self.assertEqual(self.client.get(f"/api/reading-sessions/{saved.data['id']}/").status_code, 404)
        self.client.force_authenticate(self.parent)
        self.assertTrue(self.adventure(user_id=self.child.pk)["earned"])
        self.assertFalse(self.adventure(user_id=self.sibling.pk)["earned"])

    def test_paginated_history_fetches_reward_receipts_with_one_join(self):
        awarded = self.create_session()
        ReadingSession.objects.bulk_create([
            ReadingSession(
                user=self.child, book=self.book, occurred_on="2026-10-16", duration_minutes=4,
                client_request_id=uuid4(), create_payload={},
            ) for _ in range(20)
        ])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/reading-sessions/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 21)
        self.assertEqual(response.data["results"][0]["reading_reward"], awarded.data["reading_reward"])
        reward_queries = [query for query in queries if "reading_readingdailyreward" in query["sql"].lower()]
        self.assertEqual(len(reward_queries), 1)

    def test_game_loop_runs_once_only_when_saved_minutes_cross_threshold(self):
        from apps.reading.models import ReadingDailyReward
        from apps.rpg.services import GameLoopService
        with patch.object(GameLoopService, "on_task_completed", wraps=GameLoopService.on_task_completed) as game_loop:
            self.create_session(4)
            self.assertEqual(game_loop.call_count, 0)
            crossing = self.create_session(6)
            self.create_session(600)
            self.assertEqual(game_loop.call_count, 1)
        self.assertEqual(game_loop.call_args.args[1], "reading_logged")
        self.assertEqual(game_loop.call_args.args[2], {
            "session_id": crossing.data["id"],
            "reading_reward_id": ReadingDailyReward.objects.get(user=self.child).pk,
        })
        self.assertTrue(game_loop.call_args.kwargs["strict"])

    def test_same_family_parent_logging_uses_child_wallet_and_next_local_day_resets(self):
        self.client.force_authenticate(self.parent)
        response = self.create_session(user_id=self.child.pk)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNotNone(response.data["reading_reward"])
        self.assertFalse(CoinLedger.objects.filter(user=self.parent).exists())
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)):
            self.assertFalse(self.adventure(user_id=self.child.pk)["earned"])
            second = self.create_session(user_id=self.child.pk)
            self.assertEqual(second.data["reading_reward"]["day"], "2026-10-18")
        self.assertEqual(self.reading_coins().count(), 2)

    def test_rewards_use_family_date_even_when_server_day_has_advanced(self):
        self.family.timezone = "Pacific/Honolulu"
        self.family.save(update_fields=["timezone"])
        self.child.family.refresh_from_db()
        # At 07:30 UTC, Phoenix is Oct 18 and Honolulu is still Oct 17.
        midnight = datetime(2026, 10, 18, 7, 30, tzinfo=datetime_timezone.utc)
        with patch("django.utils.timezone.now", return_value=midnight):
            response = self.create_session(4, occurred_on="2026-10-17")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(self.adventure()["minutes_credited"], 4)
            self.assertEqual(self.create_session(6).data["reading_reward"]["day"], "2026-10-17")
        self.assertEqual(self.reading_coins().count(), 1)

    def test_boosted_receipt_reports_actual_xp_and_coin_payout(self):
        character = self.child.character_profile
        character.xp_boost_expires_at = NOW + timedelta(hours=2)
        character.coin_boost_expires_at = NOW + timedelta(hours=2)
        character.save(update_fields=["xp_boost_expires_at", "coin_boost_expires_at"])
        response = self.create_session()
        self.assertIn("reading_reward", response.data)
        self.assertEqual(response.data["reading_reward"], {
            "day": "2026-10-17", "xp_awarded": 30, "coins_awarded": 10,
        })
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 30)
        self.assertEqual(self.reading_coins().get().amount, 10)
        self.assertEqual(self.adventure()["xp_awarded"], 30)

    def test_missing_or_locked_reading_skill_does_not_invent_xp(self):
        SkillProgress.objects.create(user=self.child, skill=self.skill, unlocked=False)
        response = self.create_session()
        self.assertIn("reading_reward", response.data)
        self.assertEqual(response.data["reading_reward"]["xp_awarded"], 0)
        self.assertEqual(response.data["reading_reward"]["coins_awarded"], 5)
        self.skill.delete()
        with patch("django.utils.timezone.now", return_value=NOW + timedelta(days=1)):
            response = self.create_session()
            self.assertEqual(response.data["reading_reward"]["xp_awarded"], 0)
            self.assertEqual(response.data["reading_reward"]["coins_awarded"], 5)

    def test_award_failure_rolls_back_crossing_session_progress_and_wallet(self):
        self.create_session(4)
        request_id = str(uuid4())
        with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("award unavailable")):
            with self.assertRaisesRegex(RuntimeError, "award unavailable"):
                self.create_session(6, client_request_id=request_id)
        self.assertEqual(self.adventure()["minutes_credited"], 4)
        self.assertEqual(ReadingSession.objects.filter(user=self.child).count(), 1)
        self.assertFalse(self.reading_coins().exists())
        self.assertEqual(self.create_session(6, client_request_id=request_id).data["reading_reward"]["coins_awarded"], 5)

    def test_game_loop_failure_rolls_back_xp_coins_receipt_and_source(self):
        self.create_session(4)
        request_id = str(uuid4())
        with patch("apps.rpg.services.DropService.process_drops", side_effect=RuntimeError("drop unavailable")):
            with self.assertRaisesRegex(RuntimeError, "drop unavailable"):
                self.create_session(6, client_request_id=request_id)
        self.assertEqual(self.adventure()["minutes_credited"], 4)
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.child.character_profile.refresh_from_db()
        self.assertIsNone(self.child.character_profile.last_active_date)
        self.assertEqual(self.create_session(6, client_request_id=request_id).data["reading_reward"]["xp_awarded"], 15)

    def test_account_deletion_cascades_rewarded_reading_and_its_credit(self):
        from apps.reading.models import ReadingDailyReward, ReadingRewardCredit

        saved = self.create_session()
        self.assertEqual(saved.status_code, 201, saved.data)
        self.assertIsNotNone(saved.data["reading_reward"])
        child_id = self.child.pk
        self.assertTrue(ReadingDailyReward.objects.filter(user_id=child_id, awarded_at__isnull=False).exists())
        self.assertTrue(ReadingRewardCredit.objects.filter(user_id=child_id).exists())
        self.child.delete()
        for model in (ReadingBook, ReadingSession, ReadingDailyReward, ReadingRewardCredit):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.filter(user_id=child_id).exists())

    def test_reflection_prose_never_enters_reward_activity(self):
        from apps.activity.models import ActivityEvent

        reflection = "The violet dragon's secret promise should stay in my reading reflection."
        saved = self.create_session(reflection=reflection)
        self.assertEqual(saved.status_code, 201, saved.data)
        self.assertIsNotNone(saved.data["reading_reward"])
        self.assertEqual(ReadingSession.objects.get(pk=saved.data["id"]).reflection, reflection)
        events = list(ActivityEvent.objects.filter(subject=self.child).values("summary", "context"))
        self.assertTrue(events)
        self.assertNotIn(reflection, str(events))

    def test_reading_reward_push_waits_for_transaction_commit(self):
        from apps.notifications.models import Notification
        from apps.rpg.models import CharacterProfile

        CharacterProfile.objects.filter(user=self.child).update(login_streak=2, last_active_date="2026-10-16")
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as delay:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                saved = self.create_session()
                self.assertEqual(saved.status_code, 201, saved.data)
                self.assertIsNotNone(saved.data["reading_reward"])
                self.assertTrue(Notification.objects.filter(user=self.child, notification_type="streak_milestone").exists())
                delay.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            delay.assert_called_once()
            self.assertEqual(delay.call_args.args[4], "streak_milestone")

    def test_failed_reading_reward_discards_pushes_from_earlier_steps(self):
        from apps.notifications.models import Notification
        from apps.rpg.models import CharacterProfile

        CharacterProfile.objects.filter(user=self.child).update(login_streak=2, last_active_date="2026-10-16")
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as delay:
            with self.captureOnCommitCallbacks(execute=True) as callbacks, patch(
                "apps.rpg.services.DropService.process_drops", side_effect=RuntimeError("drop unavailable"),
            ):
                with self.assertRaisesRegex(RuntimeError, "drop unavailable"):
                    self.create_session()
            self.assertEqual(callbacks, [])
            delay.assert_not_called()
        self.assertFalse(Notification.objects.filter(user=self.child).exists())
        self.assertFalse(ReadingSession.objects.filter(user=self.child).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingRewardConcurrencyTests(ReadingRewardSetup, TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Reward row-lock concurrency requires PostgreSQL.")
        super().setUp()

    def concurrent_posts(self, payloads):
        barrier = Barrier(2)

        def post(payload):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.child)
                barrier.wait(timeout=10)
                response = client.post("/api/reading-sessions/", payload, format="json")
                return response.status_code, response.data
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(post, payloads, timeout=30))

    def payload(self, minutes=10, **extra):
        return {"book": self.book.pk, "duration_minutes": minutes, "client_request_id": str(uuid4()), **extra}

    def assert_awarded_once(self):
        from apps.reading.models import ReadingDailyReward
        self.assertEqual(ReadingDailyReward.objects.filter(user=self.child, awarded_at__isnull=False).count(), 1)
        self.assertEqual(self.reading_coins().count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)
        self.assertEqual(self.adventure()["minutes_credited"], 10)

    def test_two_distinct_qualifying_sessions_award_once(self):
        results = self.concurrent_posts([self.payload(), self.payload()])
        self.assertEqual(sorted(code for code, _ in results), [201, 201])
        self.assertEqual(sum(row.get("reading_reward") is not None for _, row in results), 1)
        self.assert_awarded_once()

    def test_concurrent_partial_sessions_combine_without_lost_credit(self):
        results = self.concurrent_posts([self.payload(4), self.payload(6)])
        self.assertEqual(sorted(code for code, _ in results), [201, 201])
        self.assert_awarded_once()

    def test_concurrent_identical_retry_returns_same_reward_without_paying_twice(self):
        payload = self.payload()
        results = self.concurrent_posts([payload, payload])
        self.assertEqual(sorted(code for code, _ in results), [200, 201])
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        self.assertEqual(results[0][1]["reading_reward"], results[1][1]["reading_reward"])
        self.assert_awarded_once()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingRewardIdentityMigrationTests(ReadingRewardSetup, TestCase):
    def preserve_legacy_identities(self):
        migration = import_module("apps.reading.migrations.0003_readingrewardcredit")
        migration.preserve_existing_request_identities(apps, SimpleNamespace(connection=connection))

    def test_legacy_identity_backfill_reads_no_prose_and_creates_no_rewards(self):
        from apps.reading.models import ReadingDailyReward, ReadingRewardCredit
        legacy = ReadingSession.objects.create(
            user=self.child, book=self.book, occurred_on="2026-10-17", duration_minutes=600,
            reflection="Keep this prose out of reward processing.", client_request_id=uuid4(), create_payload={},
        )
        with CaptureQueriesContext(connection) as queries:
            self.preserve_legacy_identities()
        self.preserve_legacy_identities()
        credit = ReadingRewardCredit.objects.get(user=self.child, client_request_id=legacy.client_request_id)
        self.assertEqual((credit.day.isoformat(), credit.minutes), ("2026-10-17", 0))
        self.assertEqual(ReadingRewardCredit.objects.count(), 1)
        source_queries = [query["sql"].lower() for query in queries if "reading_readingsession" in query["sql"].lower()]
        self.assertTrue(source_queries)
        self.assertFalse(any("reflection" in query for query in source_queries))
        self.assertFalse(ReadingDailyReward.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())
        self.child.character_profile.refresh_from_db()
        self.assertIsNone(self.child.character_profile.last_active_date)

    def test_legacy_current_day_entry_delete_and_retry_cannot_earn(self):
        request_id = str(uuid4())
        legacy = ReadingSession.objects.create(
            user=self.child, book=self.book, occurred_on="2026-10-17", duration_minutes=10,
            client_request_id=request_id, create_payload={},
        )
        self.preserve_legacy_identities()
        self.client.delete(f"/api/reading-sessions/{legacy.pk}/")
        replay = self.create_session(10, client_request_id=request_id)
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertIsNone(replay.data["reading_reward"])
        self.assertEqual(self.adventure()["minutes_credited"], 0)
        self.assertFalse(self.reading_coins().exists())

    def test_identity_seed_does_not_rewrite_an_existing_real_contribution(self):
        request_id = str(uuid4())
        self.create_session(4, client_request_id=request_id)
        self.preserve_legacy_identities()
        from apps.reading.models import ReadingRewardCredit
        self.assertEqual(ReadingRewardCredit.objects.get(user=self.child, client_request_id=request_id).minutes, 4)
        self.assertEqual(self.adventure()["minutes_credited"], 4)
        self.assertFalse(self.reading_coins().exists())
