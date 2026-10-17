"""Synthetic reading responses produced by authenticated Django endpoints."""
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.reading.models import ReadingBook, ReadingSession
from apps.rewards.models import CoinLedger
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

    def test_daily_reading_reward_reports_actual_boosted_award_and_survives_replay(self):
        category = SkillCategory.objects.create(name="Language Arts")
        skill = Skill.objects.create(category=category, name="Reading Comprehension")
        profile = self.child.character_profile
        profile.xp_boost_expires_at = shared.FIXED_NOW + timedelta(hours=1)
        profile.coin_boost_expires_at = shared.FIXED_NOW + timedelta(hours=1)
        profile.save(update_fields=["xp_boost_expires_at", "coin_boost_expires_at"])
        book = self.client.post("/api/reading-books/", self.book_payload, format="json").json()
        partial = self.client.post("/api/reading-sessions/", {
            "book": book["id"], "occurred_on": "2026-10-10", "duration_minutes": 4,
            "pages_read": 4, "format": "print",
            "client_request_id": "44444444-4444-4444-8444-444444444444",
        }, format="json")
        self.assertEqual(partial.status_code, 201, partial.content)
        self.assertIsNone(partial.json()["reading_reward"])
        self.assert_response_fixture(self.client.get(
            "/api/reading/summary/"), "reading-adventure-progress.json")
        payload = {
            "book": book["id"], "occurred_on": "2026-10-10", "duration_minutes": 6,
            "pages_read": 8, "section": "Chapter 2", "format": "audiobook", "reaction": "liked",
            "client_request_id": "55555555-5555-4555-8555-555555555555",
        }
        session = self.assert_response_fixture(self.client.post(
            "/api/reading-sessions/", payload, format="json",
        ), "reading-session-rewarded.json", status=201)
        expected_reward = {"day": "2026-10-10", "xp_awarded": 30, "coins_awarded": 10}
        self.assertEqual(session["reading_reward"], expected_reward)
        summary = self.assert_response_fixture(self.client.get(
            "/api/reading/summary/"), "reading-summary-rewarded.json")
        self.assertTrue(summary["reading_adventure"]["earned"])
        self.assertEqual(summary["reading_adventure"]["xp_awarded"], 30)
        self.assertEqual(summary["reading_adventure"]["coins_awarded"], 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=skill).xp_points, 30)
        reading_coins = CoinLedger.objects.filter(user=self.child, reason="reading")
        self.assertEqual(list(reading_coins.values_list("amount", flat=True)), [10])
        replay = self.client.post("/api/reading-sessions/", payload, format="json")
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json(), session)
        corrected = self.client.patch(f"/api/reading-sessions/{session['id']}/", {
            "duration_minutes": 600,
        }, format="json")
        self.assertEqual(corrected.status_code, 200, corrected.content)
        self.assertEqual(corrected.json()["reading_reward"], expected_reward)
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{session['id']}/").status_code, 204)
        replacement = self.client.post("/api/reading-sessions/", {
            **payload, "client_request_id": "66666666-6666-4666-8666-666666666666",
        }, format="json")
        self.assertEqual(replacement.status_code, 201, replacement.content)
        self.assertIsNone(replacement.json()["reading_reward"])
        after = self.client.get("/api/reading/summary/").json()["reading_adventure"]
        self.assertTrue(after["earned"])
        self.assertEqual(after["minutes_credited"], 10)
        self.assertEqual(after["coins_awarded"], 10)
        self.assertEqual(reading_coins.count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=skill).xp_points, 30)

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
