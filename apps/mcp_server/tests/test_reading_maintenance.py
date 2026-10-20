"""Reading maintenance keeps saved history separate from daily reward credit."""
from datetime import datetime, timedelta, timezone as datetime_timezone
import time
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


READ_TOOLS = {"get_reading_book", "get_reading_session", "list_reading_sessions"}
WRITE_TOOLS = {
    "update_reading_book", "update_reading_session",
    "delete_reading_book", "delete_reading_session",
}


class ReadingMaintenanceRegistryTests(SimpleTestCase):
    def test_maintenance_tools_are_registered_with_confirmation_and_concrete_outputs(self):
        names = {entry.name for entry in mcp._tool_manager.list_tools()}
        self.assertTrue(READ_TOOLS | WRITE_TOOLS <= names)
        for name in READ_TOOLS | WRITE_TOOLS:
            with self.subTest(name=name):
                entry = mcp._tool_manager.get_tool(name)
                self.assertEqual(entry.annotations.readOnlyHint, name in READ_TOOLS)
                self.assertEqual(entry.annotations.destructiveHint, name in WRITE_TOOLS)
                self.assertTrue(entry.annotations.idempotentHint)
                self.assertEqual("confirmation" in entry.parameters["properties"], name in WRITE_TOOLS)
                expected = "sessions" if name == "list_reading_sessions" else (
                    "deleted" if name.startswith("delete_") else "title" if name.endswith("book") else "reading_reward"
                )
                self.assertIn(expected, entry.fn_metadata.output_schema["properties"])


class ReadingMaintenanceSchemaTests(SimpleTestCase):
    def test_patches_reject_null_empty_and_immutable_fields(self):
        from apps.mcp_server.reading_maintenance_schemas import UpdateReadingBookIn, UpdateReadingSessionIn
        for schema, identity in ((UpdateReadingBookIn, {"book_id": 1}), (UpdateReadingSessionIn, {"session_id": 1})):
            for field in schema.patch_fields:
                with self.subTest(schema=schema.__name__, field=field), self.assertRaises(ValidationError):
                    schema(**identity, **{field: None})
            with self.assertRaisesMessage(ValidationError, "at least one"):
                schema(**identity)
            for field, value in {"user": 2, "book": 2, "client_request_id": str(uuid4()), "xp_awarded": 99}.items():
                with self.subTest(field=field), self.assertRaises(ValidationError):
                    schema(**identity, **{field: value, "title" if schema is UpdateReadingBookIn else "section": "Changed"})

    def test_schema_bounds_and_partial_dump_keep_only_explicit_changes(self):
        from apps.mcp_server.reading_maintenance_schemas import (
            GetReadingBookIn, GetReadingSessionIn, ListReadingSessionsIn,
            UpdateReadingBookIn, UpdateReadingSessionIn,
        )
        for schema, data in (
            (GetReadingBookIn, {"book_id": True}), (GetReadingSessionIn, {"session_id": 10**30}),
            (ListReadingSessionsIn, {"book_id": 0}), (ListReadingSessionsIn, {"limit": True}),
            (ListReadingSessionsIn, {"limit": 101}), (ListReadingSessionsIn, {"cursor": "x" * 4097}),
            (ListReadingSessionsIn, {"since": "2026-10-20", "until": "2026-10-19"}),
            (UpdateReadingBookIn, {"book_id": 1, "title": ""}),
            (UpdateReadingBookIn, {"book_id": 1, "interests": ["unknown"]}),
            (UpdateReadingBookIn, {"book_id": 1, "interests": ["humor"] * 7}),
            (UpdateReadingSessionIn, {"session_id": 1, "duration_minutes": True}),
            (UpdateReadingSessionIn, {"session_id": 1, "duration_minutes": 601}),
            (UpdateReadingSessionIn, {"session_id": 1, "pages_read": 2001}),
            (UpdateReadingSessionIn, {"session_id": 1, "reflection": "x" * 3001}),
        ):
            with self.subTest(schema=schema.__name__, data=data), self.assertRaises(ValidationError):
                schema(**data)
        book = UpdateReadingBookIn(book_id=1, status="paused", author="", interests=[])
        self.assertEqual(book.model_dump(exclude_unset=True, include=book.patch_fields), {
            "status": "paused", "author": "", "interests": [],
        })
        session = UpdateReadingSessionIn(session_id=1, duration_minutes=0, reaction="")
        self.assertEqual(session.model_dump(exclude_unset=True, include=session.patch_fields), {
            "duration_minutes": 0, "reaction": "",
        })


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingMaintenanceTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 20, 1, tzinfo=datetime_timezone.utc)
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Maintenance readers", parents=[{"username": "maint-parent", "is_staff": True}, {"username": "maint-coparent", "is_staff": True}],
            children=[{"username": "maint-child"}, {"username": "maint-sibling"}],
        )
        self.parent, self.coparent = household.parents
        self.child, self.sibling = household.children
        self.parent.family.timezone = "America/Phoenix"
        self.parent.family.save(update_fields=["timezone"])
        other = make_family(
            "Other maintenance readers", parents=[{"username": "maint-other-parent", "is_staff": True}],
            children=[{"username": "maint-other-child"}],
        )
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(name="Reading Comprehension", category=category)
        self.book = self.make_book(self.child, "Saved book")
        self.sibling_book = self.make_book(self.sibling, "Sibling book")
        self.other_book = self.make_book(self.other_child, "Other book")
        self.session = self.make_session(self.book, reflection="A private reading reflection", pages_read=12)
        self.sibling_session = self.make_session(self.sibling_book, reflection="Sibling reflection")
        self.other_session = self.make_session(self.other_book, reflection="Foreign reflection")
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def make_book(self, child, title):
        return ReadingBook.objects.create(user=child, title=title, client_request_id=uuid4(), create_payload={})

    def make_session(self, book=None, **extra):
        book = book or self.book
        return ReadingSession.objects.create(
            user=book.user, book=book, occurred_on="2026-10-19", section="Chapter one",
            client_request_id=uuid4(), create_payload={}, **extra,
        )

    def invoke(self, name, **values):
        from apps.mcp_server import reading_maintenance_schemas as schemas
        from apps.mcp_server.tools import reading_maintenance
        schema_name = "".join(part.title() for part in name.split("_")) + "In"
        return getattr(reading_maintenance, name)(getattr(schemas, schema_name)(**values))

    def transport(self, name, params, *, actor=None, scopes=None, **extra):
        with override_user(actor or self.parent, scopes=scopes):
            return async_to_sync(mcp.call_tool)(name, {"params": params, **extra})

    def log(self, **overrides):
        from apps.mcp_server.reading_schemas import LogReadingSessionIn
        from apps.mcp_server.tools.reading import log_reading_session
        params = LogReadingSessionIn(**{
            "book": self.book.pk, "duration_minutes": 10, "client_request_id": uuid4(), **overrides,
        })
        return params, log_reading_session(params)

    def summary(self):
        from apps.mcp_server.reading_schemas import GetReadingSummaryIn
        from apps.mcp_server.tools.reading import get_reading_summary
        return get_reading_summary(GetReadingSummaryIn())

    def test_detail_and_history_reads_are_scoped_and_never_write(self):
        with override_user(self.child), CaptureQueriesContext(connection) as queries:
            book = self.invoke("get_reading_book", book_id=self.book.pk)
            session = self.invoke("get_reading_session", session_id=self.session.pk)
            history = self.invoke("list_reading_sessions", book_id=self.book.pk)
        self.assertEqual(book["title"], "Saved book")
        self.assertNotIn("catalog_entry", book)
        self.assertNotIn("create_payload", book)
        self.assertEqual(session["reflection"], "A private reading reflection")
        self.assertIsNone(session["reading_reward"])
        self.assertEqual(history["sessions"], [session])
        self.assertEqual(history["total"], 1)
        self.assertIsNone(history["next_cursor"])
        self.assertFalse(history["has_more"])
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries))
        self.assertFalse(ReadingDailyReward.objects.exists())
        self.assertFalse(ReadingRewardCredit.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        with override_user(self.parent):
            self.assertEqual(self.invoke("get_reading_session", user_id=self.child.pk, session_id=self.session.pk), session)

    def test_every_tool_requires_explicit_parent_target_and_children_cannot_select_siblings(self):
        operations = {
            "get_reading_book": {"book_id": self.book.pk},
            "get_reading_session": {"session_id": self.session.pk},
            "list_reading_sessions": {},
            "update_reading_book": {"book_id": self.book.pk, "title": "Changed"},
            "update_reading_session": {"session_id": self.session.pk, "section": "Changed"},
            "delete_reading_book": {"book_id": self.book.pk},
            "delete_reading_session": {"session_id": self.session.pk},
        }
        for actor, target, error in (
            (self.parent, None, MCPValidationError), (self.parent, self.parent.pk, MCPNotFoundError),
            (self.other_parent, self.child.pk, MCPNotFoundError),
            (self.child, self.sibling.pk, MCPPermissionDenied), (None, None, MCPPermissionDenied),
        ):
            with override_user(actor):
                for name, params in operations.items():
                    with self.subTest(actor=actor, name=name), self.assertRaises(error):
                        self.invoke(name, user_id=target, **params)
        self.assertEqual(ReadingBook.objects.count(), 3)
        self.assertEqual(ReadingSession.objects.count(), 3)
        self.session.refresh_from_db()
        self.assertEqual(self.session.section, "Chapter one")

    def test_foreign_and_sibling_record_ids_are_not_found_for_all_record_operations(self):
        for actor in (self.child, self.parent):
            with override_user(actor):
                target = {"user_id": self.child.pk} if actor == self.parent else {}
                for book in (self.sibling_book, self.other_book):
                    for name, extra in (("get_reading_book", {}), ("update_reading_book", {"status": "finished"}),
                                        ("delete_reading_book", {}), ("list_reading_sessions", {})):
                        with self.subTest(actor=actor.pk, name=name, book=book.pk), self.assertRaises(MCPNotFoundError):
                            self.invoke(name, book_id=book.pk, **target, **extra)
                for session in (self.sibling_session, self.other_session):
                    for name, extra in (("get_reading_session", {}), ("update_reading_session", {"section": "Changed"}),
                                        ("delete_reading_session", {})):
                        with self.subTest(actor=actor.pk, name=name, session=session.pk), self.assertRaises(MCPNotFoundError):
                            self.invoke(name, session_id=session.pk, **target, **extra)

    def test_book_patch_keeps_omitted_fields_and_original_uuid_replay_returns_current_book(self):
        from apps.mcp_server.reading_schemas import CreateReadingBookIn
        from apps.mcp_server.tools.reading import create_reading_book
        params = CreateReadingBookIn(
            title="Original title", author="Original author", status="reading", interests=["fantasy"], client_request_id=uuid4(),
        )
        with override_user(self.child):
            original = create_reading_book(params)
            changed = self.invoke("update_reading_book", book_id=original["id"], status="paused")
            self.assertEqual(self.invoke("update_reading_book", book_id=original["id"], status="paused"), changed)
            normalized = self.invoke("update_reading_book", book_id=original["id"], interests=["humor", "animals", "humor"])
            replay = create_reading_book(params)
        self.assertEqual(changed["author"], "Original author")
        self.assertEqual(changed["title"], "Original title")
        self.assertEqual(changed["interests"], ["fantasy"])
        self.assertEqual(normalized["interests"], ["animals", "humor"])
        self.assertEqual(replay, normalized)
        saved = ReadingBook.objects.get(pk=original["id"])
        self.assertEqual(saved.create_payload["status"], "reading")
        self.assertEqual(str(saved.client_request_id), str(params.client_request_id))
        self.assertFalse(ReadingDailyReward.objects.exists())

    def test_session_correction_matches_rest_and_preserves_original_award_and_uuid(self):
        from apps.mcp_server.tools.reading import log_reading_session
        with override_user(self.child):
            params, original = self.log(pages_read=25, reflection="Original reflection", format="audiobook")
            saved_payload = ReadingSession.objects.get(pk=original["id"]).create_payload
            changed = self.invoke(
                "update_reading_session", session_id=original["id"], duration_minutes=2,
                occurred_on="2026-10-18", reaction="liked",
            )
            replay = log_reading_session(params)
            summary = self.summary()
        rest = self.client.get(f"/api/reading-sessions/{original['id']}/")
        self.assertEqual(rest.status_code, 200)
        self.assertEqual(rest.data, changed)
        self.assertEqual(replay, changed)
        self.assertEqual(changed["pages_read"], 25)
        self.assertEqual(changed["format"], "audiobook")
        self.assertEqual(changed["reflection"], "Original reflection")
        self.assertEqual(changed["reading_reward"], {"day": "2026-10-19", "xp_awarded": 15, "coins_awarded": 5})
        self.assertEqual(summary["total_minutes"], 2)
        self.assertEqual(summary["reading_adventure"]["minutes_credited"], 10)
        self.assertTrue(summary["reading_adventure"]["earned"])
        self.assertEqual(ReadingSession.objects.get(pk=original["id"]).create_payload, saved_payload)
        self.assertEqual(ReadingRewardCredit.objects.get(client_request_id=params.client_request_id).minutes, 10)
        self.assertEqual(CoinLedger.objects.filter(reason="reading").count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)

    def test_increased_or_deleted_partial_session_does_not_change_original_daily_credit(self):
        with override_user(self.child):
            _, original = self.log(duration_minutes=4)
            changed = self.invoke("update_reading_session", session_id=original["id"], duration_minutes=600)
            self.assertIsNone(changed["reading_reward"])
            self.assertEqual(self.summary()["reading_adventure"]["minutes_credited"], 4)
            self.invoke("delete_reading_session", session_id=original["id"])
            self.assertEqual(self.summary()["reading_adventure"]["minutes_credited"], 4)
            _, second = self.log(duration_minutes=6)
        self.assertEqual(second["reading_reward"]["xp_awarded"], 15)
        self.assertEqual(ReadingDailyReward.objects.get(user=self.child).minutes_credited, 10)
        self.assertEqual(CoinLedger.objects.filter(reason="reading").count(), 1)

    def test_invalid_merged_patch_and_future_local_date_leave_saved_record_unchanged(self):
        with override_user(self.child):
            for changes in (
                {"section": "", "reflection": "", "pages_read": 0, "duration_minutes": 0},
                {"occurred_on": "2026-10-20"},
            ):
                with self.subTest(changes=changes), self.assertRaises(MCPValidationError):
                    self.invoke("update_reading_session", session_id=self.session.pk, **changes)
            with self.assertRaises(MCPValidationError):
                self.invoke("update_reading_book", book_id=self.book.pk, title="   ")
        self.session.refresh_from_db()
        self.book.refresh_from_db()
        self.assertEqual(self.session.section, "Chapter one")
        self.assertEqual(self.session.pages_read, 12)
        self.assertEqual(self.session.reflection, "A private reading reflection")
        self.assertEqual(self.book.title, "Saved book")
        self.assertFalse(ReadingDailyReward.objects.exists())

    def test_book_delete_is_guarded_until_history_is_explicitly_removed(self):
        with override_user(self.child):
            with self.assertRaises(MCPValidationError) as blocked:
                self.invoke("delete_reading_book", book_id=self.book.pk)
            self.assertEqual(blocked.exception.code, "history_conflict")
            self.assertIn("reading entries", str(blocked.exception))
            self.assertTrue(ReadingBook.objects.filter(pk=self.book.pk).exists())
            self.assertEqual(self.invoke("delete_reading_session", session_id=self.session.pk), {
                "deleted": True, "session_id": self.session.pk,
            })
            self.assertEqual(self.invoke("delete_reading_book", book_id=self.book.pk), {"deleted": True, "book_id": self.book.pk})
            with self.assertRaises(MCPNotFoundError):
                self.invoke("delete_reading_session", session_id=self.session.pk)
            with self.assertRaises(MCPNotFoundError):
                self.invoke("delete_reading_book", book_id=self.book.pk)

    def test_delete_awarded_session_preserves_receipt_and_original_uuid_cannot_reaward(self):
        from apps.mcp_server.tools.reading import log_reading_session
        with override_user(self.child):
            params, original = self.log()
            self.invoke("delete_reading_session", session_id=original["id"])
            after = self.summary()
            with patch("django.utils.timezone.now", return_value=self.now + timedelta(days=1)):
                recreated = log_reading_session(params)
                next_day = self.summary()
        self.assertTrue(after["reading_adventure"]["earned"])
        self.assertEqual(after["total_minutes"], 0)
        daily = ReadingDailyReward.objects.get(user=self.child)
        self.assertIsNone(daily.source_session_id)
        self.assertEqual((daily.xp_awarded, daily.coins_awarded, daily.minutes_credited), (15, 5, 10))
        self.assertNotEqual(recreated["id"], original["id"])
        self.assertIsNone(recreated["reading_reward"])
        self.assertEqual(next_day["reading_adventure"]["minutes_credited"], 0)
        self.assertEqual(ReadingRewardCredit.objects.count(), 1)
        self.assertEqual(ReadingDailyReward.objects.count(), 1)
        self.assertEqual(CoinLedger.objects.filter(reason="reading").count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 15)

    def test_membership_is_rechecked_after_resolving_target_before_every_write(self):
        from apps.mcp_server.tools.reading import _reading_target
        operations = {
            "update_reading_book": {"book_id": self.book.pk, "status": "finished"},
            "update_reading_session": {"session_id": self.session.pk, "section": "Changed"},
            "delete_reading_book": {"book_id": self.book.pk},
            "delete_reading_session": {"session_id": self.session.pk},
        }

        def move_after_resolution(user_id):
            actor, target = _reading_target(user_id)
            type(self.child).objects.filter(pk=self.child.pk).update(family=self.other_child.family)
            return actor, target

        for name, params in operations.items():
            type(self.child).objects.filter(pk=self.child.pk).update(family=self.parent.family)
            with self.subTest(name=name), override_user(self.parent), patch(
                "apps.mcp_server.tools.reading_maintenance._reading_target", side_effect=move_after_resolution,
            ), self.assertRaises(MCPNotFoundError):
                self.invoke(name, user_id=self.child.pk, **params)
        self.book.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.book.status, "reading")
        self.assertEqual(self.session.section, "Chapter one")

    def test_read_scope_discovers_only_reads_and_cannot_execute_writes(self):
        with override_user(self.parent, scopes=frozenset({"mcp:read"})):
            names = {entry.name for entry in async_to_sync(mcp.list_tools)()}
        self.assertTrue(READ_TOOLS <= names)
        self.assertTrue(WRITE_TOOLS.isdisjoint(names))
        for name, params in (
            ("update_reading_book", {"book_id": self.book.pk, "title": "Changed"}),
            ("update_reading_session", {"session_id": self.session.pk, "section": "Changed"}),
            ("delete_reading_book", {"book_id": self.book.pk}),
            ("delete_reading_session", {"session_id": self.session.pk}),
        ):
            result = self.transport(name, {"user_id": self.child.pk, **params}, scopes=frozenset({"mcp:read"}), confirmation=True)
            with self.subTest(name=name):
                self.assertTrue(result.isError)
                self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")
        self.assertEqual(ReadingBook.objects.count(), 3)
        self.assertEqual(ReadingSession.objects.count(), 3)

    def test_all_writes_require_literal_transport_confirmation_before_mutation(self):
        empty_book = self.make_book(self.child, "Safe to remove")
        for name, params in (
            ("update_reading_book", {"book_id": self.book.pk, "title": "Changed"}),
            ("update_reading_session", {"session_id": self.session.pk, "section": "Changed"}),
            ("delete_reading_book", {"book_id": empty_book.pk}),
            ("delete_reading_session", {"session_id": self.session.pk}),
        ):
            for extra in ({}, {"confirmation": False}, {"confirmation": "true"}, {"confirmation": 1}):
                result = self.transport(name, {"user_id": self.child.pk, **params}, **extra)
                with self.subTest(name=name, extra=extra):
                    self.assertTrue(result.isError)
            self.assertTrue(ReadingBook.objects.filter(pk=empty_book.pk).exists())
            self.assertTrue(ReadingSession.objects.filter(pk=self.session.pk).exists())
        self.book.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.book.title, "Saved book")
        self.assertEqual(self.session.section, "Chapter one")
        result = self.transport("update_reading_book", {
            "user_id": self.child.pk, "book_id": self.book.pk, "status": "finished",
        }, confirmation=True)
        self.assertIsInstance(result, tuple)
        self.assertEqual(result[1]["status"], "finished")

    def test_current_actor_family_role_and_active_state_are_rechecked_for_all_reading_writes(self):
        from apps.mcp_server.reading_schemas import CreateReadingBookIn
        from apps.mcp_server.tools.reading import _reading_target, create_reading_book

        actions = {
            "update_reading_book": lambda: self.invoke(
                "update_reading_book", user_id=self.child.pk, book_id=self.book.pk, status="finished",
            ),
            "update_reading_session": lambda: self.invoke(
                "update_reading_session", user_id=self.child.pk, session_id=self.session.pk, section="Changed",
            ),
            "delete_reading_book": lambda: self.invoke("delete_reading_book", user_id=self.child.pk, book_id=self.book.pk),
            "delete_reading_session": lambda: self.invoke("delete_reading_session", user_id=self.child.pk, session_id=self.session.pk),
            "create_reading_book": lambda: create_reading_book(CreateReadingBookIn(
                user_id=self.child.pk, title="Should never be created", client_request_id=uuid4(),
            )),
            "log_reading_session": lambda: self.log(user_id=self.child.pk),
        }
        for state in ({"family_id": self.other_parent.family_id}, {"role": "child"}, {"is_active": False}):
            for name, action in actions.items():
                def revoke_after_resolution(user_id):
                    actor, target = _reading_target(user_id)
                    type(self.parent).objects.filter(pk=self.parent.pk).update(**state)
                    return actor, target

                module = "reading" if name in {"create_reading_book", "log_reading_session"} else "reading_maintenance"
                try:
                    with self.subTest(name=name, state=state), override_user(self.parent), patch(
                        f"apps.mcp_server.tools.{module}._reading_target", side_effect=revoke_after_resolution,
                    ), self.assertRaises(MCPNotFoundError):
                        action()
                finally:
                    type(self.parent).objects.filter(pk=self.parent.pk).update(
                        family_id=self.parent.family_id, role="parent", is_active=True,
                    )
        self.book.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.book.status, "reading")
        self.assertEqual(self.session.section, "Chapter one")
        self.assertEqual(ReadingBook.objects.count(), 3)
        self.assertEqual(ReadingSession.objects.count(), 3)
        self.assertFalse(ReadingRewardCredit.objects.exists())
        self.assertFalse(ReadingDailyReward.objects.exists())

    def test_history_traverses_over_page_limit_and_tied_creation_times_without_new_inserts(self):
        book = self.make_book(self.child, "Large synthetic history")
        rows = ReadingSession.objects.bulk_create([
            ReadingSession(
                user=self.child, book=book, occurred_on="2026-10-19", duration_minutes=1,
                client_request_id=uuid4(), create_payload={},
            ) for _ in range(205)
        ])
        expected = sorted((row.pk for row in rows), reverse=True)
        with override_user(self.child):
            first = self.invoke("list_reading_sessions", book_id=book.pk, limit=100)
            inserted = self.make_session(book)
            ReadingSession.objects.filter(pk=inserted.pk).update(created_at=self.now - timedelta(days=100))
            # A correction to an unseen row cannot move it ahead of the cursor.
            self.invoke("update_reading_session", session_id=expected[150], occurred_on="2026-01-01")
            second = self.invoke("list_reading_sessions", book_id=book.pk, limit=100, cursor=first["next_cursor"])
            third = self.invoke("list_reading_sessions", book_id=book.pk, limit=100, cursor=second["next_cursor"])
        actual = [row["id"] for page in (first, second, third) for row in page["sessions"]]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual([len(page["sessions"]) for page in (first, second, third)], [100, 100, 5])
        for page in (first, second, third):
            self.assertEqual(page["total"], 205)
            self.assertEqual(page["has_more"], page["next_cursor"] is not None)
        self.assertIsNone(third["next_cursor"])
        self.assertFalse(ReadingDailyReward.objects.exists())

    def test_history_book_and_date_filters_are_inclusive_and_have_no_per_row_queries(self):
        old = self.make_session()
        ReadingSession.objects.filter(pk=old.pk).update(occurred_on="2026-10-17")
        boundary = self.make_session()
        ReadingSession.objects.filter(pk=boundary.pk).update(occurred_on="2026-10-18")
        second_book = self.make_book(self.child, "Another saved book")
        self.make_session(second_book)
        for _ in range(10):
            self.make_session()
        with override_user(self.child), CaptureQueriesContext(connection) as queries:
            result = self.invoke("list_reading_sessions", book_id=self.book.pk, since="2026-10-18", until="2026-10-19")
        self.assertEqual(result["total"], 12)
        self.assertIn(boundary.pk, [row["id"] for row in result["sessions"]])
        self.assertNotIn(old.pk, [row["id"] for row in result["sessions"]])
        self.assertTrue(all(row["book"] == self.book.pk for row in result["sessions"]))
        self.assertLessEqual(len(queries), 4)
        with override_user(self.child):
            empty = self.invoke("list_reading_sessions", since="2020-01-01", until="2020-01-01")
        self.assertEqual(empty, {"user_id": self.child.pk, "sessions": [], "total": 0, "has_more": False, "next_cursor": None})

    def test_history_cursor_rejects_tampering_expiry_actor_target_and_filter_changes(self):
        self.make_session()
        self.make_session()
        with override_user(self.parent):
            first = self.invoke("list_reading_sessions", user_id=self.child.pk, limit=1)
        cursor = first["next_cursor"]
        for actor, changes in (
            (self.parent, {"cursor": "bad-cursor"}),
            (self.parent, {"cursor": cursor + "tampered"}),
            (self.coparent, {}), (self.child, {}),
            (self.parent, {"user_id": self.sibling.pk}),
            (self.parent, {"book_id": self.book.pk}),
            (self.parent, {"since": "2026-10-01"}),
            (self.parent, {"until": "2026-10-19"}),
        ):
            with self.subTest(actor=actor.pk, changes=changes), override_user(actor), self.assertRaisesMessage(MCPValidationError, "cursor"):
                self.invoke("list_reading_sessions", **{"user_id": self.child.pk, "cursor": cursor, **changes})
        with override_user(self.parent), patch("django.core.signing.time.time", return_value=time.time() + 86402):
            with self.assertRaisesMessage(MCPValidationError, "cursor"):
                self.invoke("list_reading_sessions", user_id=self.child.pk, cursor=cursor)

    def test_history_cursor_is_not_authority_after_target_leaves_family(self):
        self.make_session()
        with override_user(self.parent):
            first = self.invoke("list_reading_sessions", user_id=self.child.pk, limit=1)
            type(self.child).objects.filter(pk=self.child.pk).update(family=self.other_child.family)
            with self.assertRaises(MCPNotFoundError):
                self.invoke("list_reading_sessions", user_id=self.child.pk, cursor=first["next_cursor"])
