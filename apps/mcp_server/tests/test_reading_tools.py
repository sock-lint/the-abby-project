"""Operational reading tools retain REST ownership and once-only rewards."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError, MCPPermissionDenied, MCPValidationError
from apps.mcp_server.server import mcp
from apps.reading.models import ReadingBook, ReadingDailyReward, ReadingRewardCredit, ReadingSession
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class ReadingToolRegistryTests(SimpleTestCase):
    def test_operational_reading_tools_are_registered(self):
        names = {entry.name for entry in mcp._tool_manager.list_tools()}
        self.assertTrue({
            "list_reading_books", "get_reading_summary",
            "create_reading_book", "log_reading_session",
        }.issubset(names))

    def test_reading_tools_advertise_concrete_output_fields_and_retry_annotations(self):
        for name, field in (
            ("list_reading_books", "next_after"), ("get_reading_summary", "reading_adventure"),
            ("create_reading_book", "title"), ("log_reading_session", "reading_reward"),
        ):
            with self.subTest(name=name):
                entry = mcp._tool_manager.get_tool(name)
                self.assertIn(field, entry.fn_metadata.output_schema["properties"])
                self.assertTrue(entry.annotations.idempotentHint)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingToolsTests(TestCase):
    def setUp(self):
        # The family is still on October 19, despite the UTC date being the 20th.
        self.now = datetime(2026, 10, 20, 1, tzinfo=datetime_timezone.utc)
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "MCP readers", parents=[{"username": "mcp-reading-parent", "is_staff": True}],
            children=[{"username": "mcp-reader"}, {"username": "mcp-reader-sibling"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.parent.family.timezone = "America/Phoenix"
        self.parent.family.save(update_fields=["timezone"])
        foreign = make_family(
            "Foreign MCP readers", parents=[{"username": "foreign-reading-parent"}],
            children=[{"username": "foreign-reader"}],
        )
        self.other_parent = foreign.parents[0]
        self.other_child = foreign.children[0]
        category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(name="Reading Comprehension", category=category)
        self.book = self.make_book(self.child, "A child book")
        self.sibling_book = self.make_book(self.sibling, "Sibling book")
        self.other_book = self.make_book(self.other_child, "Foreign book")
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def make_book(self, child, title):
        return ReadingBook.objects.create(
            user=child, title=title, client_request_id=uuid4(), create_payload={},
        )

    def book_input(self, **overrides):
        from apps.mcp_server.reading_schemas import CreateReadingBookIn
        return CreateReadingBookIn(**{
            "title": "A new shelf book", "client_request_id": uuid4(), **overrides,
        })

    def session_input(self, **overrides):
        from apps.mcp_server.reading_schemas import LogReadingSessionIn
        return LogReadingSessionIn(**{
            "book": self.book.pk, "duration_minutes": 10,
            "client_request_id": uuid4(), **overrides,
        })

    def summary(self, **overrides):
        from apps.mcp_server.reading_schemas import GetReadingSummaryIn
        from apps.mcp_server.tools import reading
        return reading.get_reading_summary(GetReadingSummaryIn(**overrides))

    def test_shelf_paginates_in_stable_id_order_and_reads_do_not_write(self):
        from apps.mcp_server.reading_schemas import ListReadingBooksIn
        from apps.mcp_server.tools import reading
        second = self.make_book(self.child, "Second book")
        third = self.make_book(self.child, "Third book")
        with override_user(self.child), CaptureQueriesContext(connection) as queries:
            first = reading.list_reading_books(ListReadingBooksIn(limit=2))
            summary = self.summary()
        mutations = [query["sql"] for query in queries if query["sql"].lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"),
        )]
        self.assertEqual(mutations, [])
        self.assertEqual([book["id"] for book in first["books"]], [self.book.pk, second.pk])
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_after"], second.pk)
        self.book.title = "Corrected without changing shelf order"
        self.book.save()
        with override_user(self.parent):
            next_page = reading.list_reading_books(ListReadingBooksIn(
                user_id=self.child.pk, after=first["next_after"], limit=2,
            ))
        self.assertEqual([book["id"] for book in next_page["books"]], [third.pk])
        self.assertFalse(next_page["has_more"])
        self.assertIsNone(next_page["next_after"])
        self.assertEqual(summary["user_id"], self.child.pk)
        self.assertEqual(summary["books_total"], 3)
        self.assertEqual(summary["sessions_total"], 0)
        self.assertEqual(summary["today"], "2026-10-19")
        self.assertFalse(summary["reading_adventure"]["earned"])
        self.assertFalse(ReadingDailyReward.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_explicit_parent_selection_child_self_and_family_scoping(self):
        from apps.mcp_server.reading_schemas import ListReadingBooksIn
        from apps.mcp_server.tools import reading
        for actor, target, error in (
            (self.parent, None, MCPValidationError),
            (self.parent, self.parent.pk, MCPNotFoundError),
            (self.other_parent, self.child.pk, MCPNotFoundError),
            (self.child, self.sibling.pk, MCPPermissionDenied),
            (None, None, MCPPermissionDenied),
        ):
            with self.subTest(actor=actor, target=target), override_user(actor):
                for invoke in (
                    lambda: reading.list_reading_books(ListReadingBooksIn(user_id=target)),
                    lambda: self.summary(user_id=target),
                    lambda: reading.create_reading_book(self.book_input(user_id=target)),
                    lambda: reading.log_reading_session(self.session_input(user_id=target)),
                ):
                    with self.assertRaises(error):
                        invoke()
        with override_user(self.parent):
            self.assertEqual(self.summary(user_id=self.child.pk)["books_total"], 1)
        self.assertEqual(ReadingBook.objects.count(), 3)
        self.assertFalse(ReadingSession.objects.exists())

    def test_read_scope_discovers_only_reading_reads_and_cannot_execute_a_write(self):
        with override_user(self.parent, scopes=frozenset({"mcp:read"})):
            names = {entry.name for entry in async_to_sync(mcp.list_tools)()}
            result = async_to_sync(mcp.call_tool)("create_reading_book", {
                "params": self.book_input(user_id=self.child.pk).model_dump(mode="json", exclude_none=True),
            })
        self.assertTrue({"list_reading_books", "get_reading_summary"}.issubset(names))
        self.assertTrue({"create_reading_book", "log_reading_session"}.isdisjoint(names))
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")
        self.assertEqual(ReadingBook.objects.count(), 3)

    def test_book_create_and_retry_share_normalization_and_current_state_with_rest(self):
        from apps.mcp_server.tools import reading
        params = self.book_input(title="  New book  ", interests=["fantasy", "animals", "animals"])
        with override_user(self.child):
            first = reading.create_reading_book(params)
        self.assertEqual(first["title"], "New book")
        self.assertEqual(first["interests"], ["animals", "fantasy"])
        self.assertNotIn("create_payload", first)
        self.assertNotIn("catalog_entry", first)
        ReadingBook.objects.filter(pk=first["id"]).update(title="Corrected title", status="finished")
        rest_retry = self.client.post("/api/reading-books/", params.model_dump(mode="json", exclude_none=True), format="json")
        self.assertEqual(rest_retry.status_code, 200, rest_retry.data)
        with override_user(self.child):
            retry = reading.create_reading_book(params)
            with self.assertRaisesMessage(MCPValidationError, "different details"):
                reading.create_reading_book(params.model_copy(update={"title": "Different request"}))
        self.assertEqual(retry["id"], first["id"])
        self.assertEqual(retry["title"], "Corrected title")
        self.assertEqual(retry["status"], "finished")
        self.assertEqual(ReadingBook.objects.filter(user=self.child).count(), 2)
        self.assertFalse(ReadingDailyReward.objects.exists())

    def test_partial_minutes_combine_and_receipts_match_rest_without_duplicate_rewards(self):
        from apps.mcp_server.tools import reading
        with override_user(self.parent):
            first = reading.log_reading_session(self.session_input(user_id=self.child.pk, duration_minutes=4))
            self.assertIsNone(first["reading_reward"])
            self.assertEqual(self.summary(user_id=self.child.pk)["reading_adventure"]["remaining_minutes"], 6)
            params = self.session_input(user_id=self.child.pk, duration_minutes=6, format="audiobook")
            second = reading.log_reading_session(params)
            retry = reading.log_reading_session(params)
        self.assertEqual(second, retry)
        self.assertEqual(second["occurred_on"], "2026-10-19")
        self.assertEqual(second["reading_reward"], {"day": "2026-10-19", "xp_awarded": 15, "coins_awarded": 5})
        rest_retry = self.client.post("/api/reading-sessions/", params.model_dump(mode="json", exclude_none=True), format="json")
        self.assertEqual(rest_retry.status_code, 200, rest_retry.data)
        self.assertEqual(rest_retry.data, second)
        self.assertEqual(ReadingSession.objects.count(), 2)
        self.assertEqual(ReadingDailyReward.objects.count(), 1)
        self.assertEqual(list(CoinLedger.objects.filter(reason="reading").values_list("amount", flat=True)), [5])
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)
        with override_user(self.child), self.assertRaisesMessage(MCPValidationError, "different details"):
            reading.log_reading_session(params.model_copy(update={"user_id": None, "duration_minutes": 9}))

    def test_omitted_date_retry_across_midnight_keeps_original_day_and_receipt(self):
        from apps.mcp_server.tools import reading
        params = self.session_input()
        with override_user(self.child):
            first = reading.log_reading_session(params)
            with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
                retry = reading.log_reading_session(params)
                self.assertFalse(self.summary()["reading_adventure"]["earned"])
        self.assertEqual(first, retry)
        self.assertEqual(ReadingDailyReward.objects.count(), 1)
        self.assertEqual(ReadingSession.objects.count(), 1)

    def test_deleted_request_identity_cannot_earn_again_tomorrow(self):
        from apps.mcp_server.tools import reading
        params = self.session_input()
        with override_user(self.child):
            first = reading.log_reading_session(params)
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{first['id']}/").status_code, 204)
        with override_user(self.child), patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
            recreated = reading.log_reading_session(params)
            summary = self.summary()
        self.assertNotEqual(first["id"], recreated["id"])
        self.assertIsNone(recreated["reading_reward"])
        self.assertEqual(summary["reading_adventure"]["minutes_credited"], 0)
        self.assertEqual(ReadingRewardCredit.objects.count(), 1)
        self.assertEqual(ReadingDailyReward.objects.count(), 1)
        self.assertEqual(CoinLedger.objects.filter(reason="reading").count(), 1)

    def test_new_logs_start_wanted_or_paused_books_and_replays_preserve_later_choices(self):
        from apps.mcp_server.tools import reading

        for status in ReadingBook.Status.values:
            with self.subTest(status=status):
                book = self.make_book(self.child, f"Shelf status {status}")
                ReadingBook.objects.filter(pk=book.pk).update(status=status)
                params = self.session_input(book=book.pk, duration_minutes=0, section="Chapter 1")
                with override_user(self.child):
                    first = reading.log_reading_session(params)
                book.refresh_from_db()
                expected = status if status == ReadingBook.Status.FINISHED else ReadingBook.Status.READING
                self.assertEqual(book.status, expected)
                ReadingBook.objects.filter(pk=book.pk).update(status=ReadingBook.Status.PAUSED)
                credits = list(ReadingRewardCredit.objects.order_by("pk").values())
                with override_user(self.child):
                    retry = reading.log_reading_session(params)
                book.refresh_from_db()
                self.assertEqual(retry["id"], first["id"])
                self.assertEqual(book.status, ReadingBook.Status.PAUSED)
                self.assertEqual(list(ReadingRewardCredit.objects.order_by("pk").values()), credits)
        self.assertFalse(ReadingDailyReward.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_shared_validation_rejects_future_empty_foreign_book_and_bad_bounds(self):
        from apps.mcp_server.reading_schemas import CreateReadingBookIn, ListReadingBooksIn, LogReadingSessionIn
        from apps.mcp_server.tools import reading
        for extra in (
            {"occurred_on": "2026-10-20"}, {"duration_minutes": 0},
            {"book": self.sibling_book.pk}, {"book": self.other_book.pk},
        ):
            with self.subTest(extra=extra), override_user(self.child), self.assertRaises(MCPValidationError):
                reading.log_reading_session(self.session_input(**extra))
        with override_user(self.child), self.assertRaises(MCPValidationError):
            reading.create_reading_book(self.book_input(title="   "))
        for invalid in ({"duration_minutes": 601}, {"pages_read": 2001}, {"book": True}, {"user_id": True},
                        {"user_id": 10**30}, {"book": 10**30}, {"xp_awarded": 100}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                LogReadingSessionIn(**{"book": self.book.pk, "client_request_id": uuid4(), **invalid})
        for invalid in ({"limit": 101}, {"after": -1}, {"limit": True}):
            with self.assertRaises(ValidationError):
                ListReadingBooksIn(**invalid)
        with self.assertRaises(ValidationError):
            CreateReadingBookIn(title="Missing UUID")
        self.assertFalse(ReadingSession.objects.exists())
        self.assertFalse(ReadingDailyReward.objects.exists())

    def test_missing_skill_reports_actual_zero_xp_and_historical_logs_do_not_reward(self):
        from apps.mcp_server.tools import reading
        self.skill.delete()
        with override_user(self.child):
            historical = reading.log_reading_session(self.session_input(occurred_on="2026-10-18"))
            notes = reading.log_reading_session(self.session_input(duration_minutes=0, reflection="I liked the dragon."))
            self.assertIsNone(historical["reading_reward"])
            self.assertIsNone(notes["reading_reward"])
            self.assertEqual(self.summary()["reading_adventure"]["minutes_credited"], 0)
            current = reading.log_reading_session(self.session_input())
        self.assertEqual(current["reading_reward"], {"day": "2026-10-19", "xp_awarded": 0, "coins_awarded": 5})
        self.assertFalse(SkillProgress.objects.exists())

    def test_failed_reward_rolls_back_entry_identity_and_credit_for_retry(self):
        from apps.mcp_server.tools import reading
        params = self.session_input()
        with override_user(self.child):
            with patch("apps.reading.services.GameLoopService.on_task_completed", side_effect=RuntimeError("Synthetic reward failure")):
                with self.assertRaisesMessage(RuntimeError, "Synthetic reward failure"):
                    reading.log_reading_session(params)
            self.assertFalse(ReadingSession.objects.exists())
            self.assertFalse(ReadingRewardCredit.objects.exists())
            self.assertFalse(ReadingDailyReward.objects.exists())
            self.assertFalse(CoinLedger.objects.exists())
            self.assertFalse(SkillProgress.objects.exists())
            result = reading.log_reading_session(params)
        self.assertEqual(result["reading_reward"]["coins_awarded"], 5)

    def test_shared_write_rechecks_child_membership_after_target_resolution(self):
        from apps.mcp_server.tools import reading
        from apps.reading.services import create_reading_book

        def move_then_save(actor, target, data):
            type(target).objects.filter(pk=target.pk).update(family_id=self.other_child.family_id)
            return create_reading_book(actor, target, data)

        with override_user(self.parent), patch("apps.mcp_server.tools.reading.save_reading_book", side_effect=move_then_save):
            with self.assertRaises(MCPNotFoundError):
                reading.create_reading_book(self.book_input(user_id=self.child.pk))
        self.assertEqual(ReadingBook.objects.count(), 3)
