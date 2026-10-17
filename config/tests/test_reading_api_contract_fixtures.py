"""Synthetic reading responses produced by authenticated Django endpoints."""
from unittest.mock import patch

from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.reading.models import ReadingBook, ReadingSession
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class ReadingApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        family = make_family(
            "Reading Fixture Family", family_id=41,
            parents=[{"id": 6, "username": "reading-fixture-parent"}],
            children=[{"id": 7, "username": "reading-fixture-child"},
                      {"id": 8, "username": "reading-fixture-sibling"}],
        )
        family.family.timezone = "America/Phoenix"
        family.family.save(update_fields=["timezone"])
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        outsider = make_family(
            "Other Reading Fixture Family", family_id=42,
            children=[{"id": 99, "username": "reading-fixture-outsider"}],
        ).children[0]
        # Reset only these new tables' sequences; endpoint-created IDs remain
        # deterministic even in a full PostgreSQL test run.
        seed = ReadingBook.objects.create(
            id=100, user=outsider, title="Other family's book", create_payload={},
            client_request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
        ReadingSession.objects.create(id=200, user=outsider, book=seed, duration_minutes=5,
                                      occurred_on=shared.FIXED_NOW.date(), create_payload={},
                                      client_request_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [ReadingBook, ReadingSession]):
                cursor.execute(sql)
        self.client.force_authenticate(self.child)
        self.book_payload = {
            "title": "The Secret Treehouse", "author": "Example Author",
            "status": "reading", "interests": ["adventure", "friendship"],
            "client_request_id": "11111111-1111-4111-8111-111111111111",
        }

    def test_saved_book_log_correction_and_summary(self):
        book = self.assert_response_fixture(self.client.post(
            "/api/reading-books/", self.book_payload, format="json",
        ), "reading-book-created.json", status=201)
        self.assertEqual(book["user"], self.child.pk)
        self.assertEqual(book["interests"], ["adventure", "friendship"])
        session_payload = {
            "book": book["id"], "occurred_on": "2026-10-09", "duration_minutes": 20,
            "pages_read": 14, "section": "Chapters 2–3", "format": "print",
            "reflection": "The friends found a map. I wonder who drew it.", "reaction": "loved",
            "client_request_id": "22222222-2222-4222-8222-222222222222",
        }
        session = self.assert_response_fixture(self.client.post(
            "/api/reading-sessions/", session_payload, format="json",
        ), "reading-session-created.json", status=201)
        self.assertEqual(session["book"], book["id"])
        self.assertEqual(session["book_title"], book["title"])
        corrected = self.assert_response_fixture(self.client.patch(
            f"/api/reading-sessions/{session['id']}/",
            {"pages_read": 16, "reflection": "The map belonged to their neighbor."}, format="json",
        ), "reading-session-corrected.json")
        self.assertEqual(corrected["client_request_id"], session["client_request_id"])
        replay = self.client.post("/api/reading-sessions/", session_payload, format="json")
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json(), corrected)
        finished = self.assert_response_fixture(self.client.patch(
            f"/api/reading-books/{book['id']}/", {"status": "finished"}, format="json",
        ), "reading-book-finished.json")
        self.assertEqual(finished["status"], "finished")
        books = self.assert_response_fixture(self.client.get(
            "/api/reading-books/"), "reading-books-list.json")
        self.assertEqual(books["results"], [finished])
        sessions = self.assert_response_fixture(self.client.get(
            "/api/reading-sessions/"), "reading-sessions-list.json")
        self.assertEqual(sessions["results"], [corrected])
        summary = self.assert_response_fixture(self.client.get(
            "/api/reading/summary/"), "reading-summary.json")
        self.assertEqual(summary["books_finished"], 1)
        self.assertEqual(summary["sessions_total"], 1)
        self.assertEqual(summary["total_minutes"], 20)
        self.assertEqual(summary["total_pages"], 16)
        self.assertEqual(summary["today"], "2026-10-10")
        self.assertEqual(ReadingSession.objects.filter(user=self.child).count(), 1)

    def test_validation_and_ownership_errors_have_no_writes(self):
        book = self.client.post("/api/reading-books/", self.book_payload, format="json").json()
        invalid = self.assert_response_fixture(self.client.post(
            "/api/reading-sessions/", {
                "book": book["id"], "duration_minutes": -1,
                "client_request_id": "33333333-3333-4333-8333-333333333333",
            }, format="json",
        ), "reading-session-invalid.json", status=400)
        self.assertIn("duration_minutes", invalid)
        self.client.force_authenticate(self.sibling)
        self.assert_response_fixture(self.client.get(
            f"/api/reading-books/{book['id']}/"), "reading-book-not-owned.json", status=404)
        self.assertFalse(ReadingSession.objects.filter(user=self.child).exists())
